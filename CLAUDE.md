# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Digitz is a local financial data pipeline that ingests bank CSV statements into DuckDB, applies a two-tier classification system (deterministic SQL rules → Gemini AI fallback), and produces structured tax ledgers. All data stays on-device.

## Commands

```sh
# Ingest a statement (credit card or checking)
uv run main.py --file data/raw_data/<file>.csv --name <account> --type [checking|credit_card]

# Ingest + generate tax report in one run
uv run main.py --file data/raw_data/<file>.csv --name <account> --type <type> --report

# Run the sidecar context pipeline (trips + cash overrides + master_ledger view)
uv run python -m core.pipeline

# Run spend analytics
uv run python -m core.analytics

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_idempotency.py -v

# Lint / format
uv run ruff check .
uv run black .

# Open the DuckDB database directly
duckdb data/finance.db
```

> **Note:** `--file`, `--name`, and `--type` are marked `required=True` in `main.py` even when using `--report` alone. Pass dummy values if you only need to regenerate the report from an already-classified DB.

## Architecture

### Pipeline Flow

```
CSV file
  → infra/csv_ingest.py      # Normalizes and dedupes into raw_transactions
  → core/classifier.py       # Tier 1: SQL pattern matching → classified_ledger
  → core/ai_tier.py          # Tier 2: Gemini AI patches remaining UNCLASSIFIED rows
  → core/tax_reporter.py     # Optional: exports tax_summary_report.csv
```

### Sidecar Context Pipeline (`core/pipeline.py`)

Separate from the main ingestion flow. Runs `TripManager` and `CashManager` to sync CSV sidecars into DuckDB, then builds a `master_ledger` VIEW that joins `classified_ledger` with `trips` and `cash_log` for contextual analysis (business vs. personal travel, cash/loan overrides).

### Key Database Tables

| Table | Purpose |
|---|---|
| `raw_transactions` | All ingested statement rows, deduplicated by hash |
| `classified_ledger` | Categorized transactions (merchant, category, sub_category, channel, direction) |
| `trips` | Trip date ranges and type (Business/Personal) for travel context |
| `cash_log` | Manual cash transaction overrides and loan flags |
| `master_ledger` | VIEW joining all of the above for final reporting |

### Transaction Schema Fields

- `merchant_name` — resolved entity (e.g., `Wingstop`, not `DD *WINGSTOP`)
- `category` / `sub_category` — hierarchical classification
- `channel` — how the transaction was made: `pos`, `online`, `doordash`, `instacart`, `atm`, `ach`, `p2p`, etc.
- `direction` — `Expense`, `Income`, or `Transfer`

### Classification Order (Tier 1)

Rules apply top-down by specificity: marketplace prefix stripping → explicit financial types (ATM, credit card payments, transfers) → digital subscriptions → standard merchants.

### Non-obvious Conventions

- **Idempotency via MD5**: `transaction_id = md5(concat_ws('_', date, description, amount))`. Re-ingesting the same CSV is a no-op. Classification uses `ON CONFLICT DO UPDATE` so rules can be updated and re-applied.
- **Apple Card sign inversion**: Apple Card CSVs export purchases as positive numbers (opposite all other cards). `csv_ingest.py` has an explicit `is_apple_card` branch to flip the sign.
- **Fuzzy CSV header detection**: `detect_headers_and_skip_garbage()` scans the first 25 rows for the actual header row (handles BofA files with metadata rows before data) and matches column names by alias (e.g., "date", "trans. date", "transaction date").
- **Legacy tables**: `master_entities` and `merchant_map` (created by `infra/db_init.py`) are not used by the live pipeline — classification is entirely inline SQL in `classifier.py`.

### Gemini API Key

Retrieved from macOS Keychain first (`security find-generic-password -s gemini-api -w`), falls back to `GEMINI_API_KEY` env var. Model used: `gemini-2.5-flash`. Every outbound payload is logged to `logs/ai_classification_audit.log`.

### DB Path Convention

All modules resolve `data/finance.db` relative to the project root using `Path(__file__).resolve().parent.parent`. Tests use `tmp_path` fixtures and `monkeypatch.chdir()` to isolate against the real DB.

## Known Issues

- `core/trip_manager.py:12` — syntax error: the default argument string is unclosed (`"data/finance.db)` missing closing `"`). The `add_trip()` method is also broken (incomplete SQL).
- `core/cash_manager.py` — `logger.warming(...)` should be `logger.warning(...)`.

## Data Directories

- `data/raw_data/` — source CSV statements (never committed)
- `data/overrides/` — sidecar CSVs for trips and cash overrides
- `data/finance.db` — the embedded DuckDB database (never committed)
