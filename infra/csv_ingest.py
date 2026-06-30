# infra/csv_ingest.py
from pathlib import Path
import duckdb

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = ROOT_DIR / "data" / "finance.db"

def ingest_statement(csv_path: str, account_name: str, account_type: str):
    """Leverages DuckDB's native CSV reader to load, clean, and insert data instantly."""
    conn = duckdb.connect(str(DB_FILE))
    
    print(f"Ingesting {csv_path} into {account_name}...")
    
    # 1. Use DuckDB's read_csv_auto to parse headers and handle messy strings natively.
    # 2. We use SQL rules to handle sign-inversion (charges vs credits).
    conn.execute(f"""
        INSERT OR IGNORE INTO raw_transactions (
            transaction_id, account_name, account_type, 
            transaction_date, raw_description, amount, direction
        )
        SELECT 
            -- Generate a unique hash for the row so we don't need a Python duplicate counter
            md5(concat_ws('_', "Date", "Description", "Amount")),
            '{account_name}',
            '{account_type}',
            CAST("Date" AS DATE),
            "Description",
            -- Handle credit card sign inversion directly in SQL:
            -- If it's a credit card statement, charges are positive, so flip them to negative.
            CASE 
                WHEN '{account_type}' = 'credit_card' THEN -ABS(CAST("Amount" AS DOUBLE))
                ELSE CAST("Amount" AS DOUBLE)
            END,
            CASE 
                WHEN '{account_type}' = 'credit_card' THEN 'Expense'
                WHEN CAST("Amount" AS DOUBLE) < 0 THEN 'Expense'
                ELSE 'Income'
            END
        FROM read_csv_auto('{csv_path}', header=True);
    """)
    
    # Check how many rows were loaded
    changes = conn.execute("SELECT changes()").fetchone()[0]
    print(f"Successfully processed statement! Rows added/updated: {changes}")
    conn.close()