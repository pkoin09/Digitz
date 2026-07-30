# Digitz Financial Ingestion Engine 🪙

Digitz is a private, local-first pipeline that turns messy bank CSV exports into clean ledgers. I built it as a simple way to overcome the 'how much did i spend on ... ?' questions that pop up before tax time, take it with a grain of salt as i dont know uncle sam's lingo & mathematics. It's built on **DuckDB** for the heavy lifting and **Gemini AI** for the stuff that plain string matching can't figure out. Everything runs on your machine (more on the Gemini part later) — nothing gets uploaded to a third-party aggregator, and no bank credentials ever leave your laptop.

- The short version of how it works, Two tiers:
  - most transactions get classified instantly with SQL rules (fast, deterministic, free).
  - Whatever's left over, gets handed to a language model for a second pass.

Why lean on the SQL tier at all instead of just letting Gemini label everything? A hand-written rule wins on **speed** (instant, no network round-trip), **consistency** (deterministic — the same merchant gets the same label, run after run), **privacy** (the description never leaves your machine), and **reliability** (no dependency on network or API availability). You write a rule for any merchant you see repeatedly; you leave the long tail — the one-offs and the unrecognizable — to the AI. That split is the whole pitch: deterministic where you can, semantic where you must.

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
   v. [Adding a New Classification Rule](docs/classification-strategy.md)
5. [Getting Started](docs/getting-started.md)
   i. [Prerequisites](docs/getting-started.md)
   ii. [Ingesting Credit Cards](docs/getting-started.md)
   iii. [Ingesting Checking Accounts](docs/getting-started.md)
   iv. [Trip & Cash Sidecar Context](docs/getting-started.md)
   v. [Tax & Coverage Report](docs/getting-started.md)
6. [Database Rescue — Undoing Mistakes](docs/database-rescue.md)
7. [Database Schema — Tables & Views](docs/db-schema.md)
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
- **API Error handling.** If Gemini throws a `503` or `429`, the retry logic backs off with jitter instead of hammering the endpoint.
- **MacOS API credentials in keychain.** Variables live in the keychain, `.env`/environment variable everywhere else — either way, nothing gets hardcoded.
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

- **Business trip tagging** — when you're on a trip, in-person transactions auto-tag with the trip's context in the `master_ledger` / `ledger_with_trips` views. See the ready-to-run queries and sample output in the [SQL Cookbook → Trip Context](docs/sql-cookbook.md) and [Business Trip Expenses](docs/sql-cookbook.md).
- **Loan tracking** — manual cash/loan overrides from `data/overrides/cash.csv` surface in `master_ledger` via the `is_account_receivable` flag. See the worked example in the [SQL Cookbook → Loan Tracking](docs/sql-cookbook.md).

---

For the deeper dives — how classification actually decides what's what, teaching it a new merchant, step-by-step setup, fixing a bad import, and a pile of ready-to-run SQL/pandas snippets — see the [Contents](#contents) above.
