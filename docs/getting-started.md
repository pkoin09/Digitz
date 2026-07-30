# Getting Started

[← Back to main README](../README.md)

## i) Prerequisites

**macOS — save your Gemini API key to Keychain:**

```sh
security add-generic-password -a "$USER" -s "gemini-api" -w "YOUR_GEMINI_API_KEY_HERE"
```

**Windows / other _even macs if you opt to_ — add it to a `.env` file in the project root:**

```
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
```

## ii) Ingest Credit Card Statements

On a credit card, expenses show up as _positive_ numbers and payments as _negative_ — keep that in mind if the signs look flipped from what you'd expect.

```sh
uv run main.py --file data/raw_data/chase_creditcard_1_transactions.csv   --name chase   --type credit_card
uv run main.py --file data/raw_data/amex_creditcard_2_transactions.csv    --name amex    --type credit_card
uv run main.py --file data/raw_data/apple_card_3_transactions.csv         --name apple   --type credit_card
uv run main.py --file data/raw_data/discover_creditcard_4_transactions.csv --name discover --type credit_card
```

## iii) Ingest Checking Accounts

Checking accounts are the mirror image: deposits are _positive_, outflows are _negative_.

```sh
uv run main.py --file data/raw_data/bofa_checking_5_transactions.csv --name bofa --type checking
```

## iv) Apply Trip & Cash Context (Sidecar Pipeline)

If you want business trips or manual cash entries reflected in the ledger, edit `data/overrides/trips.csv` and `data/overrides/cash.csv`, then run:

```sh
uv run python -m core.pipeline
```

This syncs both override CSVs into DuckDB and (re)builds the `ledger_with_trips`, `monthly_burn_summary`, and `master_ledger` views.

> **Date formats.** Dat columns in the override CSVs are flexible — the parser accepts `M/D/YYYY` (`3/15/2026`), `M/D/YY` (`3/15/26`), `YYYY-MM-DD` (`2026-03-15`), and `YYYY/MM/DD` (`2026/03/15`). Everything is normalized to ISO `YYYY-MM-DD` on the way into DuckDB, so the stored format is always the same regardless of how you typed it. The same applies to the bank statement CSVs ingested via `csv_ingest.py` (it falls back to `TRY_CAST` for anything else it recognizes).

## v) Tax and Coverage Report

```sh
# Generate a report on a database that's already populated:
uv run python -m core.tax_reporter

# Or do ingestion and reporting in one shot:
uv run main.py --file data/raw_data/chase_creditcard_1_transactions.csv --name chase --type credit_card --report
```

---

[← Back to main README](../README.md)
