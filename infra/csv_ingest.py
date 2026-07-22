# infra/csv_ingest.py
import csv
from pathlib import Path
import duckdb

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = ROOT_DIR / "data" / "finance.db"


def detect_headers_and_skip_garbage(csv_path: str):
    """
    Scans the top of a CSV file to find where the actual transaction table begins.
    """
    date_aliases = ["date", "trans. date", "transaction date", "post date"]
    desc_aliases = [
        "description",
        "memo",
        "details",
        "transaction description",
        "name",
        "payee",
        "merchant",
    ]
    amt_aliases = ["amount", "amt", "value", "transaction amount", "charge"]

    best_header_row = None
    skip_rows = 0

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = list(csv.reader(f))

        for i, row in enumerate(reader[:25]):
            row_clean = [str(cell).strip().lower() for cell in row]
            has_date = any(d in row_clean for d in date_aliases)
            has_desc = any(desc in row_clean for desc in desc_aliases)

            if has_date and has_desc:
                best_header_row = row
                skip_rows = i
                break

    if best_header_row is None:
        raise ValueError(
            f"Could not automatically locate transaction table headers in {csv_path}"
        )

    mapped = {"date": None, "desc": None, "amount": None}
    header_clean = [col.strip().lower() for col in best_header_row]

    for idx, col in enumerate(header_clean):
        if any(d == col or d in col for d in date_aliases) and not mapped["date"]:
            mapped["date"] = f'"{best_header_row[idx]}"'
        elif (
            any(desc == col or desc in col for desc in desc_aliases)
            and not mapped["desc"]
        ):
            mapped["desc"] = f'"{best_header_row[idx]}"'
        elif (
            any(amt == col or amt in col for amt in amt_aliases)
            and not mapped["amount"]
        ):
            mapped["amount"] = f'"{best_header_row[idx]}"'

    if not mapped["date"] or not mapped["desc"]:
        raise ValueError(
            f"Fuzzy match failed. Columns detected: {best_header_row}\nMapped Result: {mapped}"
        )

    if not mapped["amount"]:
        mapped["amount"] = "NULL"

    return skip_rows, mapped


def ingest_statement(csv_path: str, account_name: str, account_type: str):
    """Inspects headers safely and ingests messy financial data using robust parsing flags."""
    conn = duckdb.connect(str(DB_FILE))

    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_transactions (
            transaction_id TEXT PRIMARY KEY,
            account_name TEXT,
            account_type TEXT,
            transaction_date DATE,
            raw_description TEXT,
            amount DOUBLE,
            direction TEXT
        );
    """)

    try:
        skip_rows, mapped = detect_headers_and_skip_garbage(csv_path)
    except Exception as e:
        conn.close()
        raise ValueError(f"Ingestion Aborted: {e}")

    date_col = mapped["date"]
    desc_col = mapped["desc"]
    amt_col = mapped["amount"]

    if amt_col == "NULL":
        conn.close()
        raise ValueError(f"Could not map 'Amount' column automatically in {csv_path}")

    print(f"Ingesting {csv_path} into {account_name}...")

    # Determine raw file sign structures based on card brand patterns
    is_apple_card = "apple" in account_name.lower() or "apple" in csv_path.lower()

    if account_type == "credit_card":
        if is_apple_card:
            amount_calc = (
                f"-(TRY_CAST(REGEXP_REPLACE({amt_col}, '[() ]', '', 'g') AS DOUBLE))"
            )
        else:
            amount_calc = f"""
                CASE 
                    WHEN UPPER({desc_col}) LIKE '%PAYMENT%' OR UPPER({desc_col}) LIKE '%THANK YOU%'
                    THEN ABS(TRY_CAST(REGEXP_REPLACE({amt_col}, '[() ]', '', 'g') AS DOUBLE))
                    ELSE -ABS(TRY_CAST(REGEXP_REPLACE({amt_col}, '[() ]', '', 'g') AS DOUBLE))
                END
            """
    else:
        amount_calc = f"TRY_CAST(REGEXP_REPLACE({amt_col}, '[() ]', '', 'g') AS DOUBLE)"

    # We use COALESCE and try_strptime with a fallback chain of common date formats.
    # This prevents errors regardless of whether DuckDB treats the column as VARCHAR or DATE.
    conn.execute(f"""
        INSERT INTO raw_transactions (
            transaction_id, account_name, account_type, 
            transaction_date, raw_description, amount, direction
        )
        SELECT 
            md5(concat_ws('_', {date_col}, {desc_col}, {amt_col})),
            '{account_name}',
            '{account_type}',
            COALESCE(
                try_strptime({date_col}::VARCHAR, ['%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%m-%d-%Y']),
                TRY_CAST({date_col} AS DATE)
            ) AS transaction_date,
            {desc_col},
            ({amount_calc}) AS amount,
            CASE 
                WHEN ({amount_calc}) < 0 THEN 'Expense'
                ELSE 'Income'
            END AS direction
        FROM read_csv_auto(
            '{csv_path}', 
            header=True, 
            delim=',',
            all_varchar=True,  -- Force raw text parsing so format specifiers are stable
            null_padding=True,
            ignore_errors=True,
            skip={skip_rows}
        )
        WHERE {date_col} IS NOT NULL 
          AND {amt_col} IS NOT NULL 
          AND TRY_CAST(REGEXP_REPLACE({amt_col}, '[() ]', '', 'g') AS DOUBLE) IS NOT NULL
        ON CONFLICT (transaction_id) DO NOTHING;
    """)

    changes = conn.rowcount if hasattr(conn, "rowcount") else -1
    if changes == -1:
        changes = conn.execute("SELECT COUNT(*) FROM raw_transactions").fetchone()[0]
        print(f"Statement processed. Total rows now in raw_transactions: {changes}")
    else:
        print(f"Successfully processed statement! Rows added/updated: {changes}")

    conn.close()
