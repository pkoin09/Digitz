import os
import logging
import duckdb
import pandas as pd
from pathlib import Path


class CashManager:
    """
    Manages manual cash transaction overrides and loan sidecar datasets
    within DuckDB.
    """

    def __init__(self, db_path: str = "data/finance.db"):
        self.db_path = db_path
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self):
        """Returns a DuckDB connection instance."""
        return duckdb.connect(self.db_path)

    def init_db(self):
        """Initializes the cash_log schema."""
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cash_log (
                    tx_date DATE,
                    amount DECIMAL(18,2),
                    override_category VARCHAR,
                    is_loan BOOLEAN,
                    notes VARCHAR
                );
            """)

    def sync_from_csv(self, csv_path: str = "data/overrides/cash.csv"):
        """
        Loads and normalizes cash.csv into cash_log.
        """
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"cash.csv not found: {csv_path}")

        cash_df = pd.read_csv(csv_path)
        if cash_df.empty:
            logging.warning(f"{csv_path} loaded but empty")

        # Flexible date parsing -> ISO YYYY-MM-DD
        cash_df["tx_date"] = pd.to_datetime(cash_df["tx_date"], format="mixed").dt.strftime("%Y-%m-%d")

        with self.get_connection() as conn:
            # Re-create table for clean reload
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
