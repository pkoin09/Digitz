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
    """Inspects headers safely and ingests messy financial data using robust parsing flags."""
    conn = duckdb.connect(str(DB_FILE))

    # DEFENSIVE GUARD: Ensure the base ingestion table exists before we inspect or touch data
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_transactions (
            transaction_id TEXT PRIMARY KEY,
            account_name TEXT,
            account_type TEXT,
            transaction_date DATE,
            raw_description TEXT,
            amount DOUBLE,
            direction TEXT
        );
    """
    )

    # 1. Peek at headers with total fault tolerance enabled (All Varchar, Null Padding)
    df_layout = conn.execute(
        f"""
        SELECT * FROM read_csv_auto(
            '{csv_path}', 
            header=True, 
            delim=',',
            all_varchar=True,
            null_padding=True,
            ignore_errors=True
        ) LIMIT 0
    """
    )
    csv_cols = df_layout.description
    available_headers = [col[0] for col in csv_cols]

    # 2. Map our required fields to the actual headers found in the file
    date_col = get_matching_column(
        available_headers, ["Date", "Transaction Date", "date", "post date"]
    )
    desc_col = get_matching_column(
        available_headers, ["Description", "memo", "details", "transaction description"]
    )
    amt_col = get_matching_column(
        available_headers, ["Amount", "amt", "value", "transaction amount"]
    )

    if date_col == "NULL" or desc_col == "NULL":
        raise ValueError(
            f"Could not automatically map Date or Description columns. Found: {available_headers}"
        )

    print(f"Ingesting {csv_path} into {account_name}...")

    # 3. Clean and Cast on the fly using native SQL functions
    #
    # TODO (AI Tier Expansion / Zero-Loss Data Recovery):
    # Currently, rows with unparseable amounts (like 'NotANumber' or completely blank values)
    # are strictly dropped via the WHERE clause because the raw_transactions table enforces a
    # NOT NULL constraint on the 'amount' column.
    #
    # To scale up to thousands of production rows without losing data:
    #   1. Execute a migration to drop the NOT NULL constraint on raw_transactions.amount.
    #   2. Remove the text parsing filter from the WHERE clause below so corrupt amounts land as NULL.
    #   3. Update core/classifier.py to flag rows where amount IS NULL as 'UNCLASSIFIED_CORRUPT'.
    #   4. Route 'UNCLASSIFIED_CORRUPT' transactions to your LLM tier, instructing the model to
    #      infer or reconstruct the numerical amount using historical context or the raw description.

    conn.execute(
        f"""
        INSERT INTO raw_transactions (
            transaction_id, account_name, account_type, 
            transaction_date, raw_description, amount, direction
        )
        SELECT 
            md5(concat_ws('_', {date_col}, {desc_col}, {amt_col})),
            '{account_name}',
            '{account_type}',
            TRY_CAST({date_col} AS DATE) AS transaction_date,
            {desc_col},
            -- Advanced Clean: Convert (50.00) to -50.00, strip spaces, then try to cast to numeric
            CASE 
                WHEN {amt_col} LIKE '(%)' THEN -TRY_CAST(REGEXP_REPLACE({amt_col}, '[() ]', '', 'g') AS DOUBLE)
                ELSE TRY_CAST({amt_col} AS DOUBLE)
            END AS amount,
            CASE 
                WHEN '{account_type}' = 'credit_card' THEN 'Expense'
                WHEN {amt_col} LIKE '(%)' THEN 'Expense'
                WHEN TRY_CAST({amt_col} AS DOUBLE) < 0 THEN 'Expense'
                ELSE 'Income'
            END AS direction
        FROM read_csv_auto(
            '{csv_path}', 
            header=True, 
            delim=',',
            all_varchar=True,
            null_padding=True,
            ignore_errors=True
        )
        -- Strict Validation Filter: Drop structural junk before it hits schema constraints
        WHERE {date_col} IS NOT NULL 
          AND {amt_col} IS NOT NULL 
          AND TRY_CAST(REGEXP_REPLACE({amt_col}, '[() ]', '', 'g') AS DOUBLE) IS NOT NULL
        ON CONFLICT (transaction_id) DO NOTHING;
    """
    )

    # DuckDB automatically populates .rowcount on the connection/cursor object
    # after an INSERT, UPDATE, or DELETE statement terminates.
    changes = conn.rowcount if hasattr(conn, "rowcount") else -1
    if changes == -1:
        # Fallback if your specific wrapper abstracts it:
        changes = conn.execute("SELECT COUNT(*) FROM raw_transactions").fetchone()[0]
        print(f"Statement processed. Total rows now in raw_transactions: {changes}")
    else:
        print(f"Successfully processed statement! Rows added/updated: {changes}")

    conn.close()