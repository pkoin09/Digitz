import os
import duckdb
from pathlib import Path


class TripManager:
    """
    Manages trip metadata, sidecar datasets, and travel context logic 
    within DuckDB.
    """

    def __init__(self, db_path: str = "data/finance.db"):
        self.db_path = db_path
        # Ensure parent directory exists
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self):
        """Returns a DuckDB connection instance."""
        return duckdb.connect(self.db_path)

    def init_db(self):
        """Initializes the base trips table schema."""
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trips (
                    trip_id VARCHAR PRIMARY KEY,
                    start_date DATE,
                    end_date DATE,
                    trip_type VARCHAR,
                    destination VARCHAR,
                    notes VARCHAR
                );
            """)

    def add_trip(
        self,
        trip_id: str,
        start_date_str: str,
        end_date_str: str,
        trip_type: str,
        destination: str,
        notes: str = None
    ):
        """
        Inserts or updates a trip entry (Upsert).
        Supports dates in YYYY-MM-DD or MM/DD/YYYY format.
        """
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO trips (trip_id, start_date, end_date, trip_type, destination, notes)
                VALUES (
                    ?, 
                    CAST(? AS DATE), 
                    CAST(? AS DATE), 
                    ?, 
                    ?, 
                    ?
                )
                ON CONFLICT (trip_id) DO UPDATE SET
                    start_date = EXCLUDED.start_date,
                    end_date = EXCLUDED.end_date,
                    trip_type = EXCLUDED.trip_type,
                    destination = EXCLUDED.destination,
                    notes = EXCLUDED.notes;
            """, [trip_id, start_date_str, end_date_str, trip_type, destination, notes])

    def create_views(self):
        """
        Creates auxiliary helper views if classified_ledger exists.
        """
        with self.get_connection() as conn:
            # Check if classified_ledger table is present before compiling ledger views
            tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
            if "classified_ledger" in tables:
                conn.execute("""
                    CREATE OR REPLACE VIEW ledger_with_trips AS
                    SELECT 
                        l.*,
                        t.trip_id,
                        t.trip_type,
                        t.destination,
                        CASE 
                            WHEN t.trip_id IS NOT NULL THEN TRUE 
                            ELSE FALSE 
                        END AS is_travel_expense
                    FROM classified_ledger l
                    LEFT JOIN trips t 
                        ON CAST(l.transaction_date AS DATE) BETWEEN t.start_date AND t.end_date;
                """)
