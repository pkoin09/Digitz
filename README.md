# Digitz Financial Ingestion Engine 🪙

Digitz is a private, local-first pipeline that turns messy bank CSV exports into clean ledgers. I built it as a simple way to overcome the 'how much did i spend on ... ?' questions that pop up before tax time, take it with a grain of salt as i dont know uncle sam's lingo & mathematics. It's built on **DuckDB** for the heavy lifting and **Gemini AI** for the stuff that plain string matching can't figure out. Everything runs on your machine (more on the Gemini part later) — nothing gets uploaded to a third-party aggregator, and no bank credentials ever leave your laptop.

- The short version of how it works, Two tiers:
  - most transactions get classified instantly with SQL rules (fast, deterministic, free).
  - Whatever's left over, gets handed to a language model for a second pass.

---

## Contents

1. [Core Philosophy: Privacy Over Bloat](#core-philosophy-privacy-over-bloat)
2. [Key Features](#key-features)
3. [System Architecture](#system-architecture)
4. [Classification Strategy](docs/classification-strategy.md)
   i. [Deterministic Classification (DuckDB)](docs/classification-strategy.md)
   ii. [AI-Powered Semantic Classification](docs/classification-strategy.md)
   iii. [Transaction Schema](docs/classification-strategy.md)
   iv. [Processing Order](docs/classification-strategy.md)
5. [Getting Started](docs/getting-started.md)
   i. [Prerequisites](docs/getting-started.md)
   ii. [Ingesting Credit Cards](docs/getting-started.md)
   iii. [Ingesting Checking Accounts](docs/getting-started.md)
   iv. [Trip & Cash Sidecar Context](docs/getting-started.md)
   v. [Tax & Coverage Report](docs/getting-started.md)
6. [Database Rescue — Undoing Mistakes](docs/database-rescue.md)
7. [Adding a New Classification Rule](#adding-a-new-classification-rule)
8. [SQL & Pandas Cookbook](docs/sql-cookbook.md)
   i. [Quick Previews & Category Summaries](docs/sql-cookbook.md)
   ii. [Pandas & DuckDB Power-Moves](docs/sql-cookbook.md)
   iii. [Platform vs. Merchant Isolation](docs/sql-cookbook.md)
   iv. [Tax Report Output](docs/sql-cookbook.md)

---

## Core Philosophy: Privacy Over Bloat

Most finance apps want your bank login so they can sync everything to their servers. Digitz doesn't work that way — it never touches your credentials, and it doesn't need to. The whole flow looks like this:

- Download the raw statement CSVs from your bank yourself (or query them from wherever they live - not from the bank ofcourse ... hmm! will look into that)
- Ingest them locally
- Let the AI tier classify whatever SQL couldn't
- Delete the source files once they're in the database (If you need to).

The only thing that ever leaves your machine is an anonymized transaction description sent to Gemini for classification — never account numbers, balances, or anything that identifies you. A log is kept, with exactly what was sent 'logs/ai_cassification_audit.log'.

> **Where your API key lives:**
> **macOS (recommended):** pulled straight from Keychain, so it's never sitting in plaintext anywhere.
> **Windows / everything else:** set `GEMINI_API_KEY` in a `.env` file or as a system environment variable. The `.env` file is gitignored out of the box, so it won't end up in a commit by accident.

---

## Key Features

- **No double-counted transfers.** Card payments, balance clearing, and bank-to-bank transfers get automatically netted into a neutral `Transfer` category, so you don't end up with "income" or expenses counted twice.
- **Two-tier categorization.** Tier 1 is local SQL doing pattern matching on known merchants — including the annoying masked ones like `SFW_#22`. Tier 2 kicks in only for what's left, sending it to `gemini-2.5-flash` for a human-readable label.
- **Handles flaky APIs gracefully.** If Gemini throws a `503` or `429`, the retry logic backs off with jitter instead of hammering the endpoint.
- **Credentials stay out of your shell history.** Keychain on macOS, `.env`/environment variable everywhere else — either way, nothing gets hardcoded.
- **Nothing gets ingested twice.** Transaction gets an MD5 signature from its date, description, and amount. Re-running an import on the same file hits a wall instead of creating a duplicate mess.
- **Trips and cash live on the side.** Business trip date ranges and manual cash entries overlay onto the ledger without needing to re-run ingestion — they join into a `master_ledger` view alongside everything else which give the ability to filter business transactions, loans to friends easily.
- **Smart trip context — category whitelist + P2P excluded.** When you're on a business trip, only travel-relevant categories (`Travel`, `Transport`, `Meals`, `Cash`) get tagged with the trip's context. P2P payments (Zelle, Venmo) are also excluded — you can send money to anyone from anywhere, so they don't imply physical presence during a trip. Groceries, subscriptions, and shopping during a trip window are assumed to be home-related (e.g used instacart for your roomate or family to reeive).

---

## System Architecture

```
├── core/
│   ├── ai_tier.py          # Gemini integration & exponential backoff retry
│   ├── analytics.py        # Pandas & Matplotlib spend analysis
│   ├── cash_manager.py     # Manual cash/loan override sidecar (cash_log table)
│   ├── classifier.py       # SQL rule-based Tier 1 categorization
│   ├── pipeline.py         # Sidecar context pipeline (trips + cash → master_ledger)
│   ├── tax_reporter.py     # Tax category summary & CSV export
│   └── trip_manager.py     # Trip metadata, ledger_with_trips & monthly_burn_summary views
├── infra/
│   ├── csv_ingest.py       # Fuzzy header detection, sign normalization, dedup ingestion
│   ├── db_init.py          # Database schema bootstrap
│   └── db_seed.py          # Test data seeder
├── data/
│   ├── finance.db          # Embedded DuckDB database
│   ├── overrides/
│   │   ├── cash.csv        # Manual cash & loan override entries
│   │   └── trips.csv       # Trip date ranges (Business / Personal)
│   └── raw_data/           # Source statement CSVs (ingest then delete)
├── utils/
│   └── logger.py           # AI payload audit logger (logs before every Gemini call)
├── tests/
│   ├── test_idempotency.py
│   └── test_trip_manager.py
├── main.py                 # CLI entry point
└── CLAUDE.md               # Dev guidance for Claude Code
```

---

## Examples

### Business Trip Context

When you're on a business trip, in-person transactions automatically get tagged with the trip's context. Edit `data/overrides/trips.csv` to define trip date ranges, then run the sidecar pipeline:

```sh
uv run python -m core.pipeline
```

```sql
SELECT tx_date, merchant_string, amount, travel_context, trip_location
FROM ledger_with_trips
WHERE travel_context != 'Personal/Local'
ORDER BY tx_date;
```

| tx_date    | merchant_string     | amount | travel_context | trip_location |
| ---------- | ------------------- | ------ | -------------- | ------------- |
| 2026-03-16 | LYFT \*RIDE THU 2PM | -31.17 | Business       | San Francisco |
| 2026-03-17 | TACO BELL 1234      | -18.42 | Business       | San Francisco |
| 2026-03-18 | WALMART ATM         | -60.00 | Business       | San Francisco |

> **Category whitelist:** Only `Travel`, `Transport`, `Meals`, and `Cash` categories get trip context. Subscriptions, groceries, and shopping during a trip are assumed to be home-related. **P2P excluded:** Zelle/Venmo payments during a trip do _not_ get travel context — you can send money from anywhere, so they don't imply physical presence.

### Loan Tracking

Manual cash/loan overrides live in `data/overrides/cash.csv` and surface in the `master_ledger` view via the `is_account_receivable` flag:

```csv
tx_date,amount,override_category,is_loan,notes
03/06/2026,-73.98,Roommate Split Loan,TRUE,Temporary loan for utility split
```

```sql
SELECT tx_date, merchant_string, amount, final_category, is_account_receivable
FROM master_ledger
WHERE is_account_receivable = TRUE;
```

| tx_date    | merchant_string | amount | final_category | is_account_receivable |
| ---------- | --------------- | ------ | -------------- | --------------------- |
| 2026-03-06 | Roommate Split  | -73.98 | Transfer       | TRUE                  |

---

## Adding a New Classification Rule

> **Why add a manual rule instead of letting Gemini handle it?** Even with a prepaid Gemini plan, a SQL rule wins on **speed** (instant vs. a network round-trip), **consistency** (deterministic — the same merchant always gets the same label, run after run), **privacy** (the description never leaves your machine), and **reliability** (no dependency on network or API availability). Add a rule for any merchant you see repeatedly; leave the long tail to the AI.

The sample data won't cover every merchant you use, so here's how to teach Digitz about a new one. All Tier 1 rules live in a single `CASE` statement inside `core/classifier.py`. Each transaction is classified along **four axes** — you need a `WHEN` clause in each:

| Axis | What it sets | Example for "Amazon Prime Video" |
|---|---|---|
| `merchant_name` | The clean entity name | `'Amazon Prime Video'` |
| `category` | The broad bucket | `'Subscriptions'` |
| `sub_category` | The specific grouping | `'Video Streaming'` |
| `channel` | How it happened | `'online'` |

### Step-by-step: Add "Amazon Prime Video"

1. **Find the description your bank uses.** Check `raw_description` in DuckDB for the unrecognized transaction:

   ```sh
   duckdb data/finance.db -c "SELECT raw_description FROM raw_transactions WHERE raw_description ILIKE '%PRIME%VIDEO%';"
   ```

   Typical bank descriptions look like `PRIME VIDEO *1234` or `AMZN PRIME VIDEO`.

2. **Add a `WHEN` clause to each `CASE` block** in `core/classifier.py`. Insert it **above** the general `AMAZON`/`AMZN` catch-all so the more specific rule wins:

   ```python
   # In the merchant_name CASE — place before the general Amazon rule
   WHEN raw_description ILIKE '%PRIME%VIDEO%' THEN 'Amazon Prime Video'

   # In the category CASE — under Subscriptions
   WHEN raw_description ILIKE '%PRIME%VIDEO%' THEN 'Subscriptions'

   # In the sub_category CASE — under Video Streaming
   WHEN raw_description ILIKE '%PRIME%VIDEO%' THEN 'Video Streaming'

   # In the channel CASE — under online
   WHEN raw_description ILIKE '%PRIME%VIDEO%' THEN 'online'
   ```

3. **Re-run classification** (no need to re-ingest — the `ON CONFLICT DO UPDATE` re-applies rules to existing rows):

   ```sh
   uv run python -m core.classifier
   ```

4. **Verify:**

   ```sh
   duckdb data/finance.db -c "SELECT * FROM classified_ledger WHERE merchant_name = 'Amazon Prime Video';"
   ```

### Tips

- **Specificity ordering matters.** Rules run top-down, most specific first. Always place a new, narrow rule *above* any broader catch-all it could be swallowed by (e.g. `PRIME VIDEO` before `AMAZON`).
- **Case-insensitive matching.** All patterns use `ILIKE` (PostgreSQL-style case-insensitive `LIKE`), so `%PRIME%VIDEO%` matches `prime video`, `PRIME VIDEO`, etc.
- **Don't know the merchant?** Leave it out — anything still tagged `UNCLASSIFIED` gets sent to the Gemini AI tier automatically on the next classification run.
- **Existing transactions get re-classified.** The pipeline uses `ON CONFLICT DO UPDATE`, so adding or fixing a rule and re-running `core.classifier` updates already-ingested rows in place.

For the deeper dives — how classification actually decides what's what, step-by-step setup, fixing a bad import, and a pile of ready-to-run SQL/pandas snippets — see the [Contents](#contents) above.
