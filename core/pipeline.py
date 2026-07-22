from core.trip_manager import TripManager
from core.cash_manager import CashManager


def run_pipeline(db_path: str = "data/finance.db"):
    print(f"Executing standalone pipeline sweep against local target: {db_path}")
    print("--- Running Context Sidecar Pipeline ---")

    # 1. Sync sidecar datasets via their dedicated managers
    tm = TripManager(db_path=db_path)
    cm = CashManager(db_path=db_path)

    # Sync CSVs into DB
    cm.sync_from_csv("data/cash_overrides.csv")

    # 2. Build helper views
    tm.create_views()

    # 3. Build master_ledger view
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


if __name__ == "__main__":
    run_pipeline()
