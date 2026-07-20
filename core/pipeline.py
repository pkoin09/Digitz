# core/pipeline.py
import os
import pandas as pd
import duckdb

def run_context_sidecar_pipeline(conn: duckdb.DuckDBPyConnection):
    print("--- Running Context Sidecar Pipeline ---")
    
    # Files paths for your manual logs
    trips_path = "data/trips.csv"
    cash_path = "data/cash_overrides.csv"
    
    # 1. Self-seeding empty template if they do not exist, so the pipeline never breaks
    if not os.path.exists(trips_path):
        pd.DataFrame(columns=["trip_id", "start_date", "end_date", "trip_type", "destination"]).to_csv(trips_path, index=False)
        print(f"Created template at {trips_path}")
        
    if not os.path.exists(cash_path):
        pd.DataFrame(columns=["tx_date", "amount", "override_category", "is_loan", "notes"]).to_csv(cash_path, index=False)
        print(f"Created template at {cash_path}")

    # 2. Register/Update structural tables within DuckDB
    conn.execute("CREATE OR REPLACE TABLE trip_log AS SELECT * FROM read_csv_auto('data/trips.csv');")
    conn.execute("CREATE OR REPLACE TABLE cash_log AS SELECT * FROM read_csv_auto('data/cash_overrides.csv');")
    
    # 3. Compile the Enriched Master View
    # Combines structural classifications from raw ingested sources (Amex, Chase, BofA) with your overrides
    master_view_sql = """
    CREATE OR REPLACE VIEW master_ledger AS 
    SELECT 
        raw.tx_date,
        raw.desc AS merchant_string,
        raw.amount,
        -- Fallback sequence for structural classification overrides
        COALESCE(cash.override_category, raw.default_category, 'Unclassified') AS final_category,
        -- Conditional chronological boundary assignment
        COALESCE(trip.trip_type, 'Personal/Local') AS travel_context,
        trip.destination AS trip_location,
        -- Evaluating accounts receivable tracking state
        COALESCE(cash.is_loan, FALSE) AS is_account_receivable
    FROM raw_transactions raw
    LEFT JOIN trip_log trip
        ON CAST(raw.tx_date AS DATE) BETWEEN CAST(trip.start_date AS DATE) AND CAST(trip.end_date AS DATE)
    LEFT JOIN cash_log cash
        ON CAST(raw.tx_date AS DATE) = CAST(cash.tx_date AS DATE) 
        AND CAST(raw.amount AS DECIMAL(18,2)) = CAST(cash.amount AS DECIMAL(18,2));
    """
    conn.execute(master_view_sql)
    print("Intelligent view 'master_ledger' successfully registered inside finance.db.")
    
