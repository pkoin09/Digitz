from infra.db import init_db
from infra.seed import seed_db
from core.classifier import run_classification_pipeline, verify_results


def main():
    """Main entry point for the application."""
    print("Starting Digitz Application...")
    print("========================================")
    init_db()
    seed_db()
    run_classification_pipeline()
    verify_results()


if __name__ == "__main__":
    main()
