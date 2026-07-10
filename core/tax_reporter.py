# core/tax_reporter.py
import duckdb
import csv
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = ROOT_DIR / "data" / "finance.db"
REPORT_FILE = ROOT_DIR / "data" / "tax_summary_report.csv"

def generate_tax_report():
    """Generates an IRS-ready summary and transaction audit log."""
    if not DB_FILE.exists():
        print(f"Error: Database not found at {DB_FILE}. Please run your ingestion pipeline first.")
        return

    conn = duckdb.connect(str(DB_FILE))
    
    print("\n========================================")
    print("       GENERATING TAX REPORT SUMMARY     ")
    print("========================================")

    # 1. Category Summary Query
    summary_query = """
        SELECT 
            category,
            COUNT(*) as total_count,
            ROUND(SUM(CASE WHEN direction = 'Expense' THEN -ABS(amount) ELSE ABS(amount) END), 2) as net_amount
        FROM classified_ledger
        GROUP BY category
        ORDER BY net_amount ASC;
    """
    
    print("\n--- Summary by Category ---")
    summary_rows = conn.execute(summary_query).fetchall()
    
    print(f"{'Category':<20} | {'Count':<6} | {'Total Amount':<12}")
    print("-" * 44)
    for row in summary_rows:
        print(f"{row[0]:<20} | {row[1]:<6} | ${row[2]:>10.2f}")

    # 2. Export All Transactions for Your Tax Prep / Tax Guy
    export_query = """
        SELECT 
            transaction_date, 
            account_name, 
            merchant_name, 
            category, 
            amount, 
            direction,
            raw_description
        FROM classified_ledger
        ORDER BY transaction_date DESC;
    """
    all_transactions = conn.execute(export_query).fetchall()

    # Save to CSV
    with open(REPORT_FILE, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Header row
        writer.writerow(["Date", "Account/Card", "Clean Merchant", "Tax Category", "Amount", "Direction", "Raw Statement Line"])
        # Data rows
        writer.writerows(all_transactions)

    print("\n========================================")
    print(f" Report Saved! Hand this sheet to your tax guy:")
    print(f" -> {REPORT_FILE.relative_to(ROOT_DIR)}")
    print("========================================\n")
    
    conn.close()

if __name__ == "__main__":
    generate_tax_report()