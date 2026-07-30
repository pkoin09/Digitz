# Database Schema

[← Back to main README](../README.md)

All tables live in a single embedded DuckDB file at `data/finance.db`. The pipeline flows in one direction:

```
raw_transactions  →  classified_ledger  →  master_ledger
                        ↑                       ↑
                      trips                  cash_log
```

## Tables

### `raw_transactions` — landing zone for ingested CSVs

Every statement CSV gets normalized into this table on import. This is the rawest form of the data.

| Column | Type | Notes |
|---|---|---|
| `transaction_id` | VARCHAR | Primary key. MD5 hash of (date, description, amount) — guarantees idempotent imports. |
| `account_name` | VARCHAR | Friendly label for the source account (`chase`, `amex`, `bofa`, etc.) |
| `account_type` | VARCHAR | `Credit Card` or `Checking` |
| `transaction_date` | DATE | Date the transaction posted |
| `raw_description` | VARCHAR | The original, unmodified bank description string |
| `amount` | DECIMAL(10,2) | Signed amount — negative for expenses, positive for income/deposits |
| `direction` | VARCHAR | `Expense`, `Income`, or `Transfer` |
| `entity_id` | INTEGER | Nullable. Populated later by classification rules (references `master_entities`) |

### `classified_ledger` — post-classification enriched transactions

Created by `core/classifier.py`. Tier 1 (SQL) and Tier 2 (Gemini AI) both write here. The `ON CONFLICT DO UPDATE` clause means re-running classification updates rows in place — no re-import needed.

| Column | Type | Notes |
|---|---|---|
| `transaction_id` | TEXT | Primary key. Carried over from `raw_transactions`. |
| `transaction_date` | DATE | |
| `account_name` | TEXT | |
| `raw_description` | TEXT | Original bank description (preserved for audit trail) |
| `merchant_name` | TEXT | Clean entity name — `Wingstop`, not `DD *WINGSTOP 1234` |
| `category` | TEXT | Broad bucket: `Groceries`, `Meals`, `Transport`, `Travel`, `Subscriptions`, `Transfer`, etc. |
| `sub_category` | TEXT | Specific grouping: `Food Delivery`, `Uber Rides`, `Grocery Delivery`, etc. |
| `amount` | DOUBLE | |
| `direction` | TEXT | `Expense`, `Income`, `Transfer` |
| `channel` | TEXT | How it happened: `pos`, `online`, `atm`, `ach`, `p2p`, or a marketplace (`doordash`, `instacart`, `uber_eats`) |

### `trips` — business/personal trip date ranges

Edited manually in `data/overrides/trips.csv`, synced to DuckDB by `core/trip_manager.py`.

> **Date parsing.** `start_date` / `end_date` accept `M/D/YYYY`, `M/D/YY`, `YYYY-MM-DD`, or `YYYY/MM/DD`. All are normalized to ISO `YYYY-MM-DD` on insert.

| Column | Type | Notes |
|---|---|---|
| `trip_id` | VARCHAR | Primary key. User-defined label (`sf-trip-march-2026`) |
| `start_date` | DATE | Trip begins |
| `end_date` | DATE | Trip ends |
| `trip_type` | VARCHAR | `Business` or `Personal` |
| `destination` | VARCHAR | City/location (`San Francisco`) |
| `notes` | VARCHAR | Optional free-text |

### `cash_log` — manual cash & loan overrides

Edited manually in `data/overrides/cash.csv`, synced to DuckDB by `core/cash_manager.py`. On sync, the table is **fully replaced** (`CREATE OR REPLACE TABLE`) — the CSV is the source of truth.

| Column | Type | Notes |
|---|---|---|
| `tx_date` | DATE | Transaction date |
| `amount` | DECIMAL(18,2) | Signed — negative for money you gave out, positive for money received |
| `override_category` | VARCHAR | Category override applied to matching rows in `master_ledger` |
| `is_loan` | BOOLEAN | `TRUE` if this is a loan / accounts receivable |
| `notes` | VARCHAR | Free-text explanation |

### `master_entities` — entity ground truth

Populated by `infra/db_init.py`. Referenced by `merchant_map` for rule-based matching.

| Column | Type | Notes |
|---|---|---|
| `entity_id` | INTEGER | Primary key |
| `clean_name` | VARCHAR | Canonical merchant/entity name |
| `primary_category` | VARCHAR | Default category for this entity |

### `merchant_map` — classification priority rules

Links description patterns to entities. Part of the original rule engine infrastructure.

| Column | Type | Notes |
|---|---|---|
| `pattern` | VARCHAR | Primary key. Pattern to match against `raw_description` |
| `match_type` | VARCHAR | `regex` or `keyword` |
| `entity_id` | INTEGER | Foreign key → `master_entities.entity_id` |
| `priority` | INTEGER | `1` = high (checked first), `2` = low |

## Views

Views are rebuilt each time `uv run python -m core.pipeline` runs. They don't store data — they're live queries over the tables above.

### `ledger_with_trips`

Joins `classified_ledger` with `trips` to add trip context to each transaction. Built by `core/trip_manager.py`.

Adds these computed columns on top of `classified_ledger`:

| Column | Type | Notes |
|---|---|---|
| `trip_id` | VARCHAR | NULL if no trip matched |
| `travel_context` | VARCHAR | `Business`, `Personal`, or `Personal/Local` (default) |
| `trip_location` | VARCHAR | Destination city, or NULL |
| `is_travel_expense` | BOOLEAN | `TRUE` if a trip matched |

**Match logic:** a transaction matches a trip if its `transaction_date` falls within `[start_date, end_date]` AND the category is travel-relevant (`Travel`, `Transport`, `Meals`, `Cash`) AND it's not a P2P payment.

### `monthly_burn_summary`

Rolls up spending from `ledger_with_trips` into fixed vs. variable monthly buckets. Built by `core/trip_manager.py`.

| Column | Type | Notes |
|---|---|---|
| `monthly_period` | TEXT | `YYYY-MM` |
| `fixed_overhead` | DOUBLE | Subscriptions + Fees + Rent |
| `variable_lifestyle` | DOUBLE | Meals + Groceries + Shopping + Transport + Travel + Medical |
| `total_operational_spend` | DOUBLE | Everything except Transfer and Income (includes Rent) |

### `master_ledger`

The unified end-state view. Joins `classified_ledger` with both `trips` and `cash_log` to produce a single enriched ledger. Built by `core/pipeline.py`.

| Column | Type | Notes |
|---|---|---|
| `tx_date` | DATE | From `classified_ledger.transaction_date` |
| `merchant_string` | TEXT | From `classified_ledger.raw_description` (original bank text) |
| `amount` | DOUBLE | |
| `final_category` | TEXT | `cash_log.override_category` if matched, otherwise `classified_ledger.category` |
| `travel_context` | VARCHAR | `Business`, `Personal`, or `Personal/Local` |
| `trip_location` | VARCHAR | Destination city, or NULL |
| `is_account_receivable` | BOOLEAN | `TRUE` if matched to a `cash_log` row where `is_loan = TRUE` |

---

[← Back to main README](../README.md)
