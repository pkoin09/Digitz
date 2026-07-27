import os
import duckdb
import pandas as pd
from pathlib import Path
from datetime import datetime


class TripManager:
    """Manages trip metadata and travel context views within DuckDB."""

    def __init__(self, db_path: str = "data/finance.db"):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self):
        return duckdb.connect(self.db_path)

    def init_db(self):
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trips (
                    trip_id VARCHAR PRIMARY KEY,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    trip_type VARCHAR NOT NULL,
                    destination VARCHAR NOT NULL,
                    notes VARCHAR
                );
            """)

    def _parse_date(self, date_str: str) -> str:
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str, fmt).date().isoformat()
            except ValueError:
                continue
        raise ValueError(f"Unrecognized date format: {date_str}")

    def add_trip(
        self,
        trip_id: str,
        start_date_str: str,
        end_date_str: str,
        trip_type: str,
        destination: str,
        notes: str = None,
    ):
        s_date = self._parse_date(start_date_str)
        e_date = self._parse_date(end_date_str)
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO trips (trip_id, start_date, end_date, trip_type, destination, notes)
                VALUES (?, CAST(? AS DATE), CAST(? AS DATE), ?, ?, ?)
                ON CONFLICT (trip_id) DO UPDATE SET
                    start_date = EXCLUDED.start_date,
                    end_date = EXCLUDED.end_date,
                    trip_type = EXCLUDED.trip_type,
                    destination = EXCLUDED.destination,
                    notes = EXCLUDED.notes;
            """, [trip_id, s_date, e_date, trip_type, destination, notes])

    def sync_from_csv(self, csv_path: str = "data/overrides/trips.csv"):
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"trips.csv not found: {csv_path}")
        df = pd.read_csv(csv_path)
        for _, row in df.iterrows():
            self.add_trip(
                trip_id=str(row["trip_id"]),
                start_date_str=str(row["start_date"]),
                end_date_str=str(row["end_date"]),
                trip_type=str(row["trip_type"]),
                destination=str(row["destination"]),
                notes=str(row["notes"]) if pd.notna(row.get("notes")) else None,
            )

    def create_views(self):
        with self.get_connection() as conn:
            tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
            if "classified_ledger" not in tables:
                return
            conn.execute("""
                CREATE OR REPLACE VIEW ledger_with_trips AS
                SELECT
                    l.*,
                    t.trip_id,
                    COALESCE(t.trip_type, 'Personal/Local') AS travel_context,
                    t.destination AS trip_location,
                    CASE WHEN t.trip_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_travel_expense
                FROM classified_ledger l
                LEFT JOIN trips t
                    ON CAST(l.transaction_date AS DATE) BETWEEN t.start_date AND t.end_date
                    -- P2P payments (Zelle, Venmo) can be sent from anywhere,
                    -- so they don't imply physical presence during a trip.
                    AND l.sub_category != 'Person to Person Payment'
                    -- Only travel-relevant categories get trip context.
                    -- Groceries, subscriptions, shopping, etc. during a trip
                    -- window are likely home-related, not travel expenses.
                    AND l.category IN ('Travel', 'Transport', 'Meals', 'Cash')
            """)
            conn.execute("""
                CREATE OR REPLACE VIEW monthly_burn_summary AS
                SELECT
                    strftime(transaction_date, '%Y-%m') AS monthly_period,
                    ROUND(SUM(CASE
                        WHEN category IN ('Subscriptions', 'Fees')
                          OR (category = 'Transfer' AND sub_category = 'Rent Payment')
                        THEN ABS(amount) ELSE 0
                    END), 2) AS fixed_overhead,
                    ROUND(SUM(CASE
                        WHEN category IN ('Meals', 'Groceries', 'Shopping', 'Transport', 'Travel', 'Medical')
                        THEN ABS(amount) ELSE 0
                    END), 2) AS variable_lifestyle,
                    ROUND(SUM(CASE
                        WHEN category NOT IN ('Transfer', 'Income')
                          OR sub_category = 'Rent Payment'
                        THEN ABS(amount) ELSE 0
                    END), 2) AS total_operational_spend
                FROM ledger_with_trips
                GROUP BY 1
                ORDER BY 1 DESC;
            """)
