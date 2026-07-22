import pytest
import duckdb
from core.trip_manager import TripManager

@pytest.fixture
def tm(tmp_path):
    db_file = str(tmp_path / "test_finance.db")
    manager = TripManager(db_path=db_file)

    # Setup mock ledger
    with manager.get_connection() as conn:
        conn.execute("""
            CREATE TABLE classified_ledger (
                transaction_id VARCHAR PRIMARY KEY,
                transaction_date DATE,
                merchant_name VARCHAR,
                category VARCHAR,
                sub_category VARCHAR,
                amount DOUBLE
            );
            INSERT INTO classified_ledger VALUES
            ('tx1', '2026-03-01', 'Landlord', 'Transfer', 'Rent Payment', -1500.0),
            ('tx2', '2026-03-05', 'Netflix', 'Subscriptions', 'Streaming', -15.99),
            ('tx3', '2026-03-15', 'Marriott', 'Travel', 'Lodging', -450.0),
            ('tx4', '2026-03-20', 'Chase', 'Transfer', 'Credit Card Payment', -500.0);
        """)
    return manager

def test_trip_manager_flow(tm):
    # Task 1 Test: Date string conversion & insert
    tm.add_trip("TRIP1", "03/14/2026", "03/18/2026", "Business", "NYC", "Work")

    # Tasks 2 & 3 Test: Deploy and check views
    tm.create_views()

    with tm.get_connection() as conn:
        # Check Task 2 View
        tx3_context = conn.execute(
            "SELECT travel_context, trip_location FROM ledger_with_trips WHERE transaction_id = 'tx3'"
        ).fetchone()
        assert tx3_context == ('Business', 'NYC')

        # Check Task 3 View (Excludes CC payment -500.0)
        burn = conn.execute(
            "SELECT fixed_overhead, total_operational_spend FROM monthly_burn_summary WHERE monthly_period = '2026-03'"
        ).fetchone()
        assert burn == (1515.99, 1965.99)
