# infra/csv_ingest.py
from pathlib import Path
import duckdb

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = ROOT_DIR / "data" / "finance.db"


def get_matching_column(available_columns, aliases):
    """Finds which alias exists in the actual CSV columns."""
    for alias in aliases:
        if alias in available_columns:
            return f'"{alias}"'  # Return wrapped in quotes for SQL safety
    return "NULL"


def ingest_statement(csv_path: str, account_name: str, account_type: str):
    """Inspects headers with Python, then executes ultra-fast DuckDB ingestion."""
    conn = duckdb.connect(str(DB_FILE))

    # 1. Peek at the CSV headers first to see what the bank gave us
    # read_csv_auto(...).columns returns a list of string headers instantly
    df_layout = conn.execute(
        f"SELECT * FROM read_csv_auto('{csv_path}', header=True) LIMIT 0"
    )
    csv_cols = df_layout.description
    available_headers = [col[0] for col in csv_cols]

    # 2. Map our required fields to the actual headers in this specific file
    date_col = get_matching_column(
        available_headers, ["Date", "Transaction Date", "date", "post date"]
    )
    desc_col = get_matching_column(
        available_headers, ["Description", "memo", "details", "transaction description"]
    )
    amt_col = get_matching_column(
        available_headers, ["Amount", "amt", "value", "transaction amount"]
    )

    # Fail early if the CSV is missing foundational data structures
    if date_col == "NULL" or desc_col == "NULL":
        raise ValueError(
            f"Could not automatically map Date or Description columns. Found: {available_headers}"
        )

    print(
        f"Ingesting {csv_path} into {account_name} (Mapped: Date->{date_col}, Desc->{desc_col}, Amt->{amt_col})..."
    )

    # 3. Inject the exact column names into the query string dynamically
    cursor = conn.execute(
        f"""
        INSERT INTO raw_transactions (
            transaction_id, account_name, account_type, 
            transaction_date, raw_description, amount, direction
        )
        SELECT 
            md5(concat_ws('_', {date_col}, {desc_col}, {amt_col})),
            '{account_name}',
            '{account_type}',
            CAST({date_col} AS DATE),
            {desc_col},
            CASE 
                WHEN '{account_type}' = 'credit_card' THEN -ABS(CAST({amt_col} AS DOUBLE))
                ELSE CAST({amt_col} AS DOUBLE)
            END,
            CASE 
                WHEN '{account_type}' = 'credit_card' THEN 'Expense'
                WHEN CAST({amt_col} AS DOUBLE) < 0 THEN 'Expense'
                ELSE 'Income'
            END
        FROM read_csv_auto('{csv_path}', header=True)
        -- DuckDB's native way to skip duplicate transaction_ids:
        ON CONFLICT (transaction_id) DO NOTHING;
    """
    )

    # Grab the row count directly from the cursor object
    changes = cursor.rowcount
    print(f"Successfully processed statement! Rows added/updated: {changes}")
    conn.close()
