# Database Rescue — Undoing Mistakes

[← Back to main README](../README.md)

Imported the wrong account, or mislabeled one? Don't nuke the whole database — DuckDB makes it easy to surgically remove just the bad rows and re-ingest.

## Step 1: Open DuckDB on your data file

```sh
duckdb data/finance.db
```

## Step 2: Delete Only the Faulty Data

A few common scenarios:

```sql
-- Option A: wipe an entire mis-tagged account
DELETE FROM classified_ledger WHERE account_name = 'bofa';
DELETE FROM raw_transactions  WHERE account_name = 'bofa';

-- Option B: fix multiple accounts that got swapped
DELETE FROM classified_ledger WHERE account_name IN ('amex', 'discover');
DELETE FROM raw_transactions  WHERE account_name IN ('amex', 'discover');

-- Option C: remove transactions from just a date window
DELETE FROM raw_transactions WHERE account_name = 'chase' AND transaction_date BETWEEN '2026-01-15' AND '2026-01-20';
```

_(Type `.exit` when you're done to leave the DuckDB shell.)_

## Step 3: Re-ingest the Clean Data

```sh
uv run main.py --file data/raw_data/bofa_checking_5_transactions.csv --name bofa --type checking
```

---

[← Back to main README](../README.md)
