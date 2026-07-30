import duckdb
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = ROOT_DIR / "data" / "finance.db"


def get_connection():
    if not DB_FILE.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_FILE}. Ingest some data first!"
        )
    return duckdb.connect(str(DB_FILE))


def check_merchant_spend(merchant_name):
    """Prints out exactly how much you have spent on a specific merchant."""
    conn = get_connection()

    # We use UPPER(?) and wrap the search string with wildcards to make it bulletproof
    query = """
        SELECT 
            strftime(transaction_date, '%Y-%m') as month,
            COUNT(*) as transactions,
            ROUND(SUM(ABS(amount)), 2) as total_spent
        FROM classified_ledger
        WHERE UPPER(merchant_name) LIKE UPPER(?) OR UPPER(raw_description) LIKE UPPER(?)
        GROUP BY month
        ORDER BY month DESC;
    """

    search_str = f"%{merchant_name}%"
    df = conn.execute(query, [search_str, search_str]).df()
    conn.close()

    print(f"\n=== Spend History for: {merchant_name} ===")
    if df.empty:
        print(f"No transactions found matching '{merchant_name}'.")
    else:
        print(df.to_string(index=False))
    return df


def compare_months():
    """Compares spending this month vs last month across all categories."""
    conn = get_connection()

    # Get the last two months represented in your database
    months_query = """
        SELECT DISTINCT strftime(transaction_date, '%Y-%m') as month 
        FROM classified_ledger 
        WHERE transaction_date IS NOT NULL
        ORDER BY month DESC 
        LIMIT 2;
    """
    months = [r[0] for r in conn.execute(months_query).fetchall()]

    if len(months) < 2:
        print(
            "\n[!] Need at least 2 months of data to run a Month-over-Month comparison."
        )
        conn.close()
        return

    current_month, last_month = months[0], months[1]

    # 🌟 FIXED: Injecting the strings directly into the IN clause to make DuckDB's PIVOT happy!
    compare_query = f"""
        PIVOT (
            SELECT 
                category, 
                strftime(transaction_date, '%Y-%m') as month,
                ROUND(SUM(ABS(amount)), 2) as total
            FROM classified_ledger
            WHERE direction = 'Expense' AND strftime(transaction_date, '%Y-%m') IN ('{current_month}', '{last_month}')
            GROUP BY category, month
        )
        ON month
        USING SUM(total);
    """

    df = conn.execute(compare_query).df()
    conn.close()

    # Clean up column names resulting from the pivot
    df.columns = ["Category", current_month, last_month]
    df = df.fillna(0)

    print(f"\n=== Month-over-Month Spending ({last_month} vs {current_month}) ===")
    print(df.to_string(index=False))

    # Plot it out dynamically!
    df.set_index("Category").plot(kind="bar", figsize=(10, 6))
    plt.title("Month-over-Month Spending Comparison")
    plt.ylabel("Total Spent ($)")
    plt.xlabel("Category")
    plt.xticks(rotation=45)
    plt.tight_layout()

    graph_path = ROOT_DIR / "data" / "mom_spending.png"
    plt.savefig(graph_path)
    print(f"\n📊 Graph saved directly to: {graph_path.relative_to(ROOT_DIR)}")
    plt.close()


if __name__ == "__main__":
    try:
        check_merchant_spend("DoorDash")
        compare_months()
    except Exception as e:
        print(f"Analytics Error: {e}")
