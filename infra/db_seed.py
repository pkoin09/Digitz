import duckdb
from pathlib import Path

# Gets the directory where this file lives, then goes up 1 level to the project root
ROOT_DIR = Path(__file__).parent.parent
DB_FILE = ROOT_DIR / "data" / "finance.db"


def seed_db():
    """Seeds the database with basic rules and a few raw sample statements."""
    conn = duckdb.connect(DB_FILE)

    print("Cleaning up old data safely...")
    tables_to_clear = ["raw_transactions", "merchant_map", "master_entities"]

    # delete data from the tables in the correct order: raw_transactions -> merchant_map -> master_entities
    for table in tables_to_clear:
        try:
            conn.execute(f"DELETE FROM {table};")
        except duckdb.CatalogException:
            # If the database is brand new and the table doesn't exist yet,
            # this catches the error and skips it silently (acting like IF EXISTS)
            print(f"  Table '{table}' not found. Skipping truncation.")

    # Seed Master Entities
    print("Seeding Master Entities...")

    entities = [
        (101, "Uber Ride", "Transportation"),
        (102, "Uber Eats", "Dining / Delivery"),
        (103, "Safeway", "Groceries"),
        (104, "Credit Card Payment", "Transfer"),
    ]

    conn.executemany("INSERT INTO master_entities VALUES (?, ?, ?);", entities)
    print(f"Seeded {len(entities)} Master Entities.")
    print("========================================")

    # Seed Priority Rules
    print("Seeding Priority Rules...")
    rules = [
        # pattern, match_type, entity_id, priority
        ("^UBER \\*EATS", "regex", 102, 1),  # High priority: must catch Eats first
        ("UBER", "keyword", 101, 2),  # Low priority catch-all for Rides
        ("SAFEWAY", "keyword", 103, 2),
        ("INSTACART\\*SAFEWAY", "regex", 103, 1),
        ("CHASE CREDIT CARD PPD", "keyword", 104, 1),
    ]

    conn.executemany("INSERT INTO merchant_map VALUES (?, ?, ?, ?);", rules)
    print(f"Seeded {len(rules)} Priority Rules.")
    print("========================================")

    # Seed Raw Statements
    print("Seeding Sample Raw Statements (Simulating CSV imports)...")
    sample_txs = [
        # id, account, type, date, raw_desc, amount, direction, entity_id
        (
            "tx_001",
            "Chase Checking",
            "Checking",
            "2026-06-01",
            "UBER *EATS PENDING SAN JOSE",
            -34.50,
            "Expense",
            None,
        ),
        (
            "tx_002",
            "Chase Checking",
            "Checking",
            "2026-06-02",
            "UBER *TRIP HELP.UBER.COM",
            -15.00,
            "Expense",
            None,
        ),
        (
            "tx_003",
            "Amex Card",
            "Credit Card",
            "2026-06-03",
            "SAFEWAY STORE 0402",
            -112.10,
            "Expense",
            None,
        ),
        (
            "tx_004",
            "Chase Checking",
            "Checking",
            "2026-06-05",
            "CHASE CREDIT CARD PPD PMT",
            -500.00,
            "Transfer",
            None,
        ),
    ]

    conn.executemany(
        "INSERT INTO raw_transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?);", sample_txs
    )
    print(f"Seeded {len(sample_txs)} sample raw transactions.")
    print("========================================")

    conn.close()
    print("Database seeding complete.")
