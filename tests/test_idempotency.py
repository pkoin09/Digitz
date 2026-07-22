import pytest
import pandas as pd
import duckdb
from core.pipeline import run_pipeline
from core.trip_manager import TripManager

@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    db_file = str(tmp_path / "finance.db")
    data_dir = tmp_path / "data"
    overrides_dir = data_dir / "overrides"
    overrides_dir.mkdir(parents=True)

    # Pre-populate classified_ledger table
    conn = duckdb.connect(db_file)
    conn.execute("""
        CREATE TABLE classified_ledger (
            transaction_id VARCHAR PRIMARY KEY,
            transaction_date DATE,
            raw_description VARCHAR,
            category VARCHAR,
            sub_category VARCHAR,
            amount DOUBLE
        );
        INSERT INTO classified_ledger VALUES
        ('tx_100', '2026-03-15', 'AIRBNB RENTAL', 'Travel', 'Lodging', -300.00),
        ('tx_200', '2026-03-16', 'CASH ADVANCE', 'Transfer', 'Cash', -100.00);
    """)
    conn.close()

    trip_csv = overrides_dir / "trips.csv"
    cash_csv = overrides_dir / "cash.csv"

    pd.DataFrame([{
        "trip_id": "TRIP_01",
        "start_date": "03/14/2026",
        "end_date": "03/18/2026",
        "trip_type": "Business",
        "destination": "Austin",
        "notes": "Conference"
    }]).to_csv(trip_csv, index=False)

    pd.DataFrame([{
        "tx_date": "03/16/2026",
        "amount": -100.00,
        "override_category": "Cash",
        "is_loan": True,
        "notes": "Cash advance"
    }]).to_csv(cash_csv, index=False)

    monkeypatch.chdir(tmp_path)
    return db_file, trip_csv, cash_csv


def test_pipeline_itempotency_and_csv_persistence(setup_env):
    db_file, trip_csv, cash_csv = setup_env

    # 1. First pipeline sweep
    run_pipeline(db_path=db_file)

    conn = duckdb.connect(db_file)
    initial_trips = conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    initial_master = conn.execute("SELECT COUNT(*) FROM master_ledger").fetchone()[0]
    assert initial_trips == 1
    assert initial_master == 2
    conn.close()

    # 2. Add new row AND update existing row in trips.csv
    updated_trips = [
        {
            "trip_id": "TRIP_01",
            "start_date": "03/14/2026",
            "end_date": "03/19/2026",
            "trip_type": "Business",
            "destination": "Austin TX",
            "notes": "Extended Conference"
        },
        {
            "trip_id": "TRIP_02",
            "start_date": "04/01/2026",
            "end_date": "04/05/2026",
            "trip_type": "Personal",
            "destination": "Denver",
            "notes": "Vacation"
        }
    ]
    pd.DataFrame(updated_trips).to_csv(trip_csv, index=False)

    # 3. Second pipeline sweep (Simulates running pipeline anytime)
    run_pipeline(db_path=db_file)

    # 4. Assert records updated without duplicate creation
    conn = duckdb.connect(db_file)
    final_trips = conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    trip_1_dest = conn.execute("SELECT destination FROM trips WHERE trip_id = 'TRIP_01'").fetchone()[0]

    assert final_trips == 2  # 1 modified + 1 new (no duplicate rows created)
    assert trip_1_dest == "Austin TX"  # Updated in-place safely

    # Verify master_ledger view correctly references updated trip
    travel_context = conn.execute("SELECT travel_context FROM master_ledger WHERE tx_date = '2026-03-15'").fetchone()[0]
    assert travel_context == "Business"

    conn.close()
