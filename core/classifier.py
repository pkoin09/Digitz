# core/classifier.py
from pathlib import Path
import duckdb

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = ROOT_DIR / "data" / "finance.db"

def run_classification_pipeline():
    """Sweeps through raw_transactions and populates the classified ledger table."""
    conn = duckdb.connect(str(DB_FILE))
    
    print("Running classification pipeline...")

    # 1. Ensure our target classified table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS classified_ledger (
            transaction_id TEXT PRIMARY KEY,
            transaction_date DATE,
            account_name TEXT,
            raw_description TEXT,
            merchant_name TEXT,
            category TEXT,
            amount DOUBLE,
            direction TEXT,
            channel TEXT
        );
    """)

    # 2. Dynamic classification transformation
    # We use UPPER() and strpos() or LIKE for lightning-fast matching.
        # 1. Update the table initialization script
    conn.execute("""
        CREATE TABLE IF NOT EXISTS classified_ledger (
            transaction_id TEXT PRIMARY KEY,
            transaction_date DATE,
            account_name TEXT,
            raw_description TEXT,  -- <--- ENFORCE THIS
            merchant_name TEXT,
            category TEXT,
            amount DOUBLE,
            direction TEXT,
            channel TEXT
        );
    """)

    # 2. Update the processing query to stream it from raw_transactions
    conn.execute("""
        INSERT INTO classified_ledger (
            transaction_id, transaction_date, account_name, 
            raw_description, merchant_name, category, amount, direction, channel
        )
        SELECT 
            transaction_id,
            transaction_date,
            account_name,
            raw_description,  -- <--- PULL THIS
            CASE 
                WHEN UPPER(raw_description) LIKE '%SAFEWAY%' THEN 'Safeway'
                WHEN UPPER(raw_description) LIKE '%COSTCO%' THEN 'Costco'
                WHEN UPPER(raw_description) LIKE '%TARGET%' THEN 'Target'
                WHEN UPPER(raw_description) LIKE '%AMAZON%' OR UPPER(raw_description) LIKE '%AMZN%' THEN 'Amazon'
                WHEN UPPER(raw_description) LIKE '%MCDONALDS%' THEN 'McDonalds'
                WHEN UPPER(raw_description) LIKE '%UBER EATS%' THEN 'Uber Eats'
                WHEN UPPER(raw_description) LIKE '%UBER%' THEN 'Uber'
                WHEN UPPER(raw_description) LIKE '%AUTOMATIC PAYMENT%' OR UPPER(raw_description) LIKE '%ONLINE CC PAYMENT%' THEN 'Internal Transfer'
                ELSE 'UNKNOWN' 
            END AS merchant_name,
            CASE 
                WHEN UPPER(raw_description) LIKE '%SAFEWAY%' THEN 'Groceries'
                WHEN UPPER(raw_description) LIKE '%COSTCO%' THEN 'Groceries'
                WHEN UPPER(raw_description) LIKE '%TARGET%' THEN 'Shopping'
                WHEN UPPER(raw_description) LIKE '%AMAZON%' OR UPPER(raw_description) LIKE '%AMZN%' THEN 'Shopping'
                WHEN UPPER(raw_description) LIKE '%MCDONALDS%' THEN 'Meals'
                WHEN UPPER(raw_description) LIKE '%UBER EATS%' THEN 'Meals'
                WHEN UPPER(raw_description) LIKE '%UBER%' THEN 'Transport'
                WHEN UPPER(raw_description) LIKE '%AUTOMATIC PAYMENT%' OR UPPER(raw_description) LIKE '%ONLINE CC PAYMENT%' THEN 'Transfer'
                ELSE 'UNCLASSIFIED' 
            END AS category,
            amount,
            direction,
            CASE 
                WHEN UPPER(raw_description) LIKE '%ACH%' THEN 'ach'
                WHEN UPPER(raw_description) LIKE '%VENMO%' OR UPPER(raw_description) LIKE '%PAYPAL%' THEN 'p2p'
                WHEN UPPER(raw_description) LIKE '%ONLINE%' OR UPPER(raw_description) LIKE '%AMZN%' THEN 'online'
                ELSE 'pos'
            END AS channel
        FROM raw_transactions
        ON CONFLICT (transaction_id) DO UPDATE SET
            merchant_name = EXCLUDED.merchant_name,
            category = EXCLUDED.category,
            channel = EXCLUDED.channel;
    """)
    
    print("Classification sweep complete.")
    conn.close()

def verify_results():
    """Quick console reporting tool to see our classification breakdown."""
    conn = duckdb.connect(str(DB_FILE))
    print("\n--- Current Ledger Status ---")
    
    # Check classification coverage
    res = conn.execute("""
        SELECT category, COUNT(*), SUM(amount) 
        FROM classified_ledger 
        GROUP BY category
    """).fetchall()
    
    for row in res:
        print(f"Category: {row[0]:<15} | Count: {row[1]:<3} | Total: ${row[2]:,.2f}")
        
    conn.close()