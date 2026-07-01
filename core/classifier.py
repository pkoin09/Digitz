import duckdb
from pathlib import Path

# Gets the directory where this file lives, then goes up 1 level to the project root
ROOT_DIR = Path(__file__).parent.parent
DB_FILE = ROOT_DIR / "data" / "finance.db"


def run_classification_pipeline():
    """Runs the highly optimized priority match logic to classify raw entries."""
    print("Running classification pipeline...")
    conn = duckdb.connect(DB_FILE)

    # This SQL updates raw_transactions using the strict matching rules.
    # It uses a window function to guarantee priority 1 overrides priority 2.
    query = """
        WITH matched_rules AS (
            SELECT 
                t.transaction_id,
                m.entity_id,
                ROW_NUMBER() OVER(PARTITION BY t.transaction_id ORDER BY m.priority ASC) as rank
            FROM raw_transactions t
            JOIN merchant_map m 
              ON (m.match_type = 'keyword' AND position(m.pattern in t.raw_description) > 0)
              OR (m.match_type = 'regex' AND regexp_matches(t.raw_description, m.pattern))
        )
        UPDATE raw_transactions
        SET entity_id = matched_rules.entity_id
        FROM matched_rules
        WHERE raw_transactions.transaction_id = matched_rules.transaction_id
          AND matched_rules.rank = 1;
    """

    conn.execute(query)
    conn.close()
    print("Classification execution complete.")


# def verify_results():
#     """Outputs the joined table to prove the classification priority worked."""
#     conn = duckdb.connect(DB_FILE)
#     print("\n--- CLASSIFICATION RESULTS REPORT ---")

#     df = conn.execute("""
#         SELECT
#             t.transaction_date as Date,
#             t.raw_description as "Raw Statement Line",
#             COALESCE(e.clean_name, 'UNCLASSIFIED (AI Tier)') as "Clean Name",
#             COALESCE(e.primary_category, 'N/A') as Category,
#             t.amount as Amount
#         FROM raw_transactions t
#         LEFT JOIN master_entities e ON t.entity_id = e.entity_id
#         ORDER BY t.transaction_date ASC
#     """).show() # show() is a method that displays the results in a table format. instead of returning a dataframe.
#     conn.close()
#     print(df.to_string(index=False))
#     print("========================================")


def verify_results():
    """Outputs the joined data using standard Python formatting."""
    conn = duckdb.connect(str(DB_FILE))
    print("\n" + "=" * 85)
    print(
        f"{'DATE':<12} | {'RAW STATEMENT LINE':<35} | {'CLEAN NAME':<20} | {'AMOUNT':<10}"
    )
    print("=" * 85)

    # Fetch all rows as a list of tuples
    rows = conn.execute(
        """
        SELECT 
            t.transaction_date,
            t.raw_description,
            COALESCE(e.clean_name, 'UNCLASSIFIED (AI Tier)'),
            t.amount
        FROM raw_transactions t
        LEFT JOIN master_entities e ON t.entity_id = e.entity_id
        ORDER BY t.transaction_date ASC
    """
    ).fetchall()

    for row in rows:
        date_str = str(row[0])
        desc = row[1] if len(row[1]) <= 33 else row[1][:30] + "..."
        clean_name = row[2]
        amount = f"${row[3]:,.2f}"

        print(f"{date_str:<12} | {desc:<35} | {clean_name:<20} | {amount:<10}")

    print("=" * 85 + "\n")
    conn.close()
    print("Classification results report complete.")
    print("========================================")
