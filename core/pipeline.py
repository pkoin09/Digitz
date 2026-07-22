import os
import duckdb
import pandas as pd
from core.trip_manager import TripManager


def parse_human_dates(series: pd.Series) -> pd.Series:
    """Converts mixed human date formats (MM/DD/YYYY, MM-DD-YYYY, YYYY-MM-DD) to ISO string YYYY-MM-DD."""
    return pd.to_datetime(series, format="mixed").dt.strftime("%Y-%m-%d")


def run_pipeline(db_path: str = "data/finance.db"):
    print(f"Executing standalone pipeline sweep against local target: {db_path}")
    print("--- Running Context Sidecar Pipeline ---")

    tm = TripManager(db_path=db_path)

    with tm.get_connection() as conn:
        # 1. Load trip.csv into trips table with flexible date parsing
        trip_csv_path = "data/trip.csv"
        if os.path.exists(trip_csv_path):
            trips_df = pd.read_csv(trip_csv_path)

            # Normalize dates to YYYY-MM-DD
            trips_df["start_date"] = parse_human_dates(trips_df["start_date"])
            trips_df["end_date"] = parse_human_dates(trips_df["end_date"])

            for _, row in trips_df.iterrows():
                tm.add_trip(
                    trip_id=str(row["trip_id"]),
                    start_date_str=str(row["start_date"]),
                    end_date_str=str(row["end_date"]),
                    trip_type=str(row["trip_type"]),
                    destination=str(row["destination"]),
                    notes=str(row.get("notes", "")) if pd.notna(row.get("notes")) else None
                )

        # 2. Load cash_overrides.csv with flexible date parsing (5 columns)
        cash_csv_path = "data/cash_overrides.csv"
        if os.path.exists(cash_csv_path):
            cash_df = pd.read_csv(cash_csv_path)

            # Normalize tx_date to YYYY-MM-DD
            cash_df["tx_date"] = parse_human_dates(cash_df["tx_date"])

            conn.execute("""
                CREATE OR REPLACE TABLE cash_log (
                    tx_date DATE,
                    amount DECIMAL(18,2),
                    override_category VARCHAR,
                    is_loan BOOLEAN,
                    notes VARCHAR
                );
            """)

            conn.register("cash_df_view", cash_df)
            conn.execute("""
                INSERT INTO cash_log 
                SELECT 
                    CAST(tx_date AS DATE) AS tx_date, 
                    CAST(amount AS DECIMAL(18,2)) AS amount, 
                    override_category, 
                    CAST(is_loan AS BOOLEAN) AS is_loan, 
                    notes 
                FROM cash_df_view;
            """)

    # 3. Dynamic views compilation
    tm.create_views()

    # 4. Master ledger view build
    with tm.get_connection() as conn:
        print("[Schema Detection] Binding master view against target table 'classified_ledger'")

        master_view_sql = """
        CREATE OR REPLACE VIEW master_ledger AS
        SELECT 
            raw.transaction_date AS tx_date, 
            raw.raw_description AS merchant_string, 
            raw.amount, 
            COALESCE(cash.override_category, raw.category, 'Unclassified') AS final_category, 
            COALESCE(trip.trip_type, 'Personal/Local') AS travel_context, 
            trip.destination AS trip_location, 
            COALESCE(cash.is_loan, CAST('f' AS BOOLEAN)) AS is_account_receivable 
        FROM classified_ledger AS raw 
        LEFT JOIN trips AS trip 
            ON (CAST(raw.transaction_date AS DATE) BETWEEN CAST(trip.start_date AS DATE) AND CAST(trip.end_date AS DATE)) 
        LEFT JOIN cash_log AS cash 
            ON (CAST(raw.transaction_date AS DATE) = CAST(cash.tx_date AS DATE) 
            AND CAST(raw.amount AS DECIMAL(18,2)) = CAST(cash.amount AS DECIMAL(18,2)));
        """
        conn.execute(master_view_sql)
        print("Intelligent view 'master_ledger' successfully compiled inside database workspace.\n")

        # 5. Output Audit Trace
        print("[Audit Trace Summary]")
        summary_df = conn.execute("""
            SELECT 
                final_category, 
                travel_context, 
                is_account_receivable,
                COUNT(*) as count
            FROM master_ledger
            GROUP BY final_category, travel_context, is_account_receivable
            ORDER BY count DESC
            LIMIT 5;
        """).df()
        print(summary_df.to_string(index=False))


if __name__ == "__main__":
    run_pipeline()
