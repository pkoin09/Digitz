import pytest
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
            ('tx4', '2026-03-20', 'Chase', 'Transfer', 'Credit Card Payment', -500.0),
            ('tx5', '2026-03-16', 'Apple', 'Subscriptions', 'App Store', -9.99),
            ('tx6', '2026-03-16', 'Zelle', 'Transfer', 'Person to Person Payment', -50.00),
            ('tx7', '2026-03-16', 'Chipotle', 'Meals', 'Fast Casual', -25.00),
            ('tx8', '2026-03-16', 'Whole Foods', 'Groceries', 'Supermarket', -65.00);
        """)
    return manager

def test_trip_manager_flow(tm):
    # Task 1 Test: Date string conversion & insert
    tm.add_trip("TRIP1", "03/14/2026", "03/18/2026", "Business", "NYC", "Work")

    # Tasks 2 & 3 Test: Deploy and check views
    tm.create_views()

    with tm.get_connection() as conn:
        # Check Task 2 View — Travel category during trip
        tx3_context = conn.execute(
            "SELECT travel_context, trip_location FROM ledger_with_trips WHERE transaction_id = 'tx3'"
        ).fetchone()
        assert tx3_context == ('Business', 'NYC')

        # Subscription during trip should NOT get travel context — only
        # Travel, Transport, Meals, Cash categories get trip context.
        tx5_context = conn.execute(
            "SELECT travel_context, trip_location, is_travel_expense FROM ledger_with_trips WHERE transaction_id = 'tx5'"
        ).fetchone()
        assert tx5_context == ('Personal/Local', None, False)

        # Meals during trip SHOULD get travel context
        tx7_context = conn.execute(
            "SELECT travel_context, trip_location, is_travel_expense FROM ledger_with_trips WHERE transaction_id = 'tx7'"
        ).fetchone()
        assert tx7_context == ('Business', 'NYC', True)

        # Groceries during trip should NOT get travel context — likely home-related
        tx8_context = conn.execute(
            "SELECT travel_context, trip_location, is_travel_expense FROM ledger_with_trips WHERE transaction_id = 'tx8'"
        ).fetchone()
        assert tx8_context == ('Personal/Local', None, False)

        # Check Task 3 View (Excludes CC payment -500.0 and P2P -50.00)
        burn = conn.execute(
            "SELECT fixed_overhead, total_operational_spend FROM monthly_burn_summary WHERE monthly_period = '2026-03'"
        ).fetchone()
        assert burn == (1525.98, 2065.98)
