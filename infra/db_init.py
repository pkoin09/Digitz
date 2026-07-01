import duckdb
from pathlib import Path

# Gets the directory where this file lives, then goes up 1 level to the project root
ROOT_DIR = Path(__file__).parent.parent
DB_FILE = ROOT_DIR / "data" / "finance.db"

# Ensure the 'data' directory actually exists first
DB_FILE.parent.mkdir(parents=True, exist_ok=True)


def init_db():
    """Initialize the database"""
    print(f"Initializing database at {DB_FILE}")

    conn = duckdb.connect(str(DB_FILE))

    # 1. Master Entities (The Ground Truth)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS master_entities (
            entity_id INTEGER PRIMARY KEY,
            clean_name VARCHAR NOT NULL,
            primary_category VARCHAR NOT NULL
        );
    """
    )

    # 2. Merchant Classification Map (The Priority Rules)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS merchant_map (
            pattern VARCHAR NOT NULL,
            match_type VARCHAR NOT NULL, -- 'regex' or 'keyword'
            entity_id INTEGER NOT NULL,
            priority INTEGER NOT NULL,    -- 1 = High, 2 = Low
            PRIMARY KEY (pattern),
            FOREIGN KEY (entity_id) REFERENCES master_entities(entity_id)
        );
    """
    )

    # 3. Raw Transactions Table (All statement formats dump here)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_transactions (
            transaction_id VARCHAR PRIMARY KEY,
            account_name VARCHAR NOT NULL,
            account_type VARCHAR NOT NULL, -- 'Credit Card', 'Checking', etc.
            transaction_date DATE NOT NULL,
            raw_description VARCHAR NOT NULL,
            amount DECIMAL(10, 2) NOT NULL,
            direction VARCHAR NOT NULL,    -- 'Expense', 'Income', 'Transfer'
            entity_id INTEGER              -- Populated later via rules/AI
        );
    """
    )

    conn.close()
    print("Database schema successfully created.")
