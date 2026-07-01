# main.py
import argparse
from infra.db_init import init_db
from infra.db_seed import seed_db
from infra.csv_ingest import ingest_statement
from core.classifier import run_classification_pipeline, verify_results
from core.ai_tier import apply_ai_classifications


def main():
    # 1. Setup the mistake-trapping argument rules
    parser = argparse.ArgumentParser(description="Digitz Financial Ingestion Engine")

    parser.add_argument("--file", required=True, help="Path to the statement CSV file")
    parser.add_argument(
        "--name",
        required=True,
        help="Friendly name for the account (e.g., chase_prime)",
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=["checking", "credit_card"],
        help="Type of banking account",
    )

    args = parser.parse_args()

    print("========================================")
    print("STARTING DIGITZ PIPELINE")
    print("========================================")

    # 2. Run the pipeline sequentially using the validated flags
    # init_db()
    # seed_db()

    # # Pass the clean arguments straight to your native DuckDB loader
    # ingest_statement(csv_path=args.file, account_name=args.name, account_type=args.type)

    # run_classification_pipeline()
    # verify_results()

    # Step 1: Ingest raw data into raw_transactions (Deals with file anomalies, drops total math junk)
    ingest_statement(csv_path=args.file, account_name=args.name, account_type=args.type)

    # Step 2: Run deterministic rules (Clears out obvious matches instantly)
    run_classification_pipeline()

    # Step 3: Run AI Tier Patching (Sweeps remaining UNCLASSIFIED rows)
    apply_ai_classifications()

    # Step 4: Output final ledger summary metrics
    verify_results()


if __name__ == "__main__":
    main()
