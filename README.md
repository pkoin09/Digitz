# Digitz Financial Ingestion Engine 🪙

A private, lightning-fast, local financial data pipeline that transforms messy, real-world bank CSV statement lines into structured, audit-ready tax ledgers using **DuckDB** and **Gemini AI**. It uses a **hybrid two-tier classification pipeline** to process and analyze transactions, combining high-efficiency SQL logic with AI-driven semantic enrichment.

## Data Flow & Classification Strategy

1. **Deterministic Classification (DuckDB Query Engine):**

- The majority of transactions, including well-known merchants (POS stores, subscription providers, utility companies, etc.) are classified using optimized, case-insensitive SQL matching rules for speed and accuracy.
- Pattern matching and string manipulation strip out marketplace prefixes (e.g., `"DD *"`, `"UBER EATS"`) to reveal the real merchant or platform beneath.

2. **AI-Powered Semantic Classification:**

- Transactions that remain `UNCLASSIFIED` after SQL rules are routed to the LLM-based layer, which performs contextual and semantic mapping beyond static rule chains.

### Transaction Schema

Each transaction is tracked across multiple axes for downstream analysis:

- **Merchant Name:** The resolved entity actually receiving funds (e.g., `Wingstop` rather than `DD *WINGSTOP ...`).
- **Category:** Broad classes for reporting and trending (e.g., `Groceries`, `Meals`, `Transport`, `Travel`).
- **Sub-Category:** More precise grouping within each category (e.g., `Groceries -> Grocery Delivery`, `Transport -> Uber Rides`, `Transport -> Public Transit`).
- **Channel:** The mechanism or pathway through which the transaction occurred:
  - `pos` (point-of-sale / in-store)
  - `online` (web or app purchase, direct bill)
  - Named marketplaces or services (`doordash`, `uber_eats`, `instacart`, etc.)
  - Financial channels (`atm`, `ach`, `p2p`)

### Processing Order: Specificity Before Generalization

To ensure accurate categorizations, rules are applied in a strict top-down order:

1. **Marketplace Channels & Prefix Handling:** Detect and clean up intermediary or white-label marketplace tags before general text rules apply (e.g., turn `"DD *WINGSTOP"` into `Wingstop`).
2. **Explicit Financial Types:** Catch credit card payments, ATM transactions, and direct transfers.
3. **Digital Subscriptions & Streaming:** Match major recurring streaming and digital services (Netflix, Spotify, Apple, Hulu, etc.).
4. **Standard Merchants & Retailers:** Fall back on general rules for common merchants, brick-and-mortar, and uncategorized retail spending.

This layered approach balances deterministic reliability and flexibility in adapting to new vendors or transaction types.

## 🛑 Core Philosophy: Privacy Over Bloat

Commercial accounting tools require you to hand over your bank login credentials to third-party cloud aggregators. **This engine runs entirely on your local machine.**

- Download raw statement CSVs
- Ingest securely
- Run AI classification locally
- Delete sensitive source files after ingestion

**Your raw financial footprint never leaves your Mac.**

---

## 🚀 Key Features

- **Zero-Double Counting Reconciliation**  
  Automatically detects and nets out internal card payments, balance clearing, and bank-to-bank transfers into a neutral `Transfer` category, eliminating fake "Income" or double-counted "Expenses".
- **Dual-Tier Categorization**
  - Tier 1: Blazing-fast local SQL pattern matching for known merchants (handles masked strings like `SFW_#22`).
  - Tier 2: AI-powered patching sends unresolved transactions to `gemini-2.5-flash` for human-readable categorization.
- **Resilient API Architecture**  
  Implements exponential backoff with randomized jitter to recover from `503`/`429` server limits during AI patching.
- **Keychain Secured Enclave**  
  Reads Google Gemini API credentials straight from macOS Keychain. No `.env` or plaintext key exposure.
- **Local SQLite/DuckDB Persistence**  
  Dedupes transactions based on cryptographic signatures. No double ingestion.

---

## 📁 System Architecture

```
├── core/
│   ├── ai_tier.py        # Gemini integration & retry logic
│   ├── analytics.py      # Pandas & Matplotlib budgeting
│   ├── classifier.py     # SQL rule-based categorization
│   └── tax_reporter.py   # Tax totals & CSV export
├── infra/
│   ├── csv_ingest.py     # CSV ingestion logic
│   └── db_init.py        # Database init scripts
├── data/
│   └── finance.db        # Your embedded DuckDB database
├── main.py               # Main CLI/entrypoint
└── README.md             # Documentation

```

---

## 🛠️ Getting Started

### 1. Prerequisites

**Save your Gemini API key securely on macOS Keychain:**

```sh
security add-generic-password -a "$USER" -s "gemini-api" -w "YOUR_GEMINI_API_KEY_HERE"
```

### 2. Ingest Credit Card Statements

Credit card: Expenses are _positive_, payments _negative_.

```sh
uv run main.py --file data/raw_data/chase_creditcard_1_transactions.csv --name chase --type credit_card
uv run main.py --file data/raw_data/discover_creditcard_4_transactions.csv --name discover --type credit_card
```

### 3. Ingest Checking Accounts

Checking: Deposits are _positive_, outflows _negative_.

```sh
uv run main.py --file data/raw_data/bofa_checking_5_transactions.csv --name bofa --type checking
```

### 4. Tax and Coverage Reports

Output final ledger summary and CSV:

```sh
uv run main.py --report
```

---

## 🔧 Database Rescue — Undo Mistakes Instantly

If you wrongly import or mislabel an account, **do not delete your DB**. Use SQL to surgically remove mistakes.

### Step 1: Open DuckDB on your data file

```sh
duckdb data/finance.db
```

### Step 2: Delete Only Faulty Data (Examples)

```sql
-- Option A: Wipe a mis-tagged entire account
DELETE FROM classified_ledger WHERE account_name = 'bofa';
DELETE FROM raw_transactions  WHERE account_name = 'bofa';

-- Option B: Swap-correct multiple accounts at once
DELETE FROM classified_ledger WHERE account_name IN ('amex', 'discover');
DELETE FROM raw_transactions  WHERE account_name IN ('amex', 'discover');

-- Option C: Remove transactions from a date window
DELETE FROM raw_transactions WHERE account_name = 'chase' AND transaction_date BETWEEN '2026-01-15' AND '2026-01-20';
```

_(Type_ `.exit` _to leave DuckDB)_

### Step 3: Re-ingest Clean Data

```sh
uv run main.py --file data/raw_data/bofa_checking_5_transactions.csv --name bofa --type checking
```

---

## 💡 Useful DuckDB SQL Snippets

### Instantly Preview a Raw CSV File

```sql
SELECT * FROM 'data/raw_data/chase_creditcard_1_transactions.csv' LIMIT 5;
```

| Transaction Date | Post Date  | Description            | Category          | Type | Amount  | Memo |
| ---------------- | ---------- | ---------------------- | ----------------- | ---- | ------- | ---- |
| 2026-01-01       | 2026-01-03 | UBER EATS 8005928996   | Food & Drink      | Sale | -46.33  | NULL |
| 2025-01-04       | 2025-01-04 | DOORDASHCHIPOTLE       | Food & Drink      | Sale | -16.77  | NULL |
| 2026-01-05       | 2026-01-06 | AMAZON.COM2A097LG7     | Shopping          | Sale | -125.42 | NULL |
| 2025-01-06       | 2025-01-06 | SAFEWAY STORE 2214 ... | Groceries         | Sale | -100.51 | NULL |
| 2025-01-06       | 2025-01-07 | AMZN PRIME MEMBERSHIP  | Bills & Utilities | Sale | -14.99  | NULL |

---

### Group By All (No Manual Enumeration)

```sql
SELECT category, direction, COUNT(*) AS n, SUM(amount) AS net
FROM classified_ledger
GROUP BY ALL
ORDER BY net ASC;
```

| category  | direction | n   | net        |
| --------- | --------- | --- | ---------- |
| Transfer  | Expense   | 217 | -171268.34 |
| Groceries | Expense   | 367 | -37650.07  |
| Shopping  | Expense   | 254 | -20031.31  |
| ...       | ...       | ... | ...        |

---

### Monthly Category Spending (Pivot Table)

```sql
PIVOT (
  SELECT *
  FROM classified_ledger
  WHERE transaction_date >= DATE '2026-02-01'
    AND transaction_date <  DATE '2026-09-01'
)
ON strftime(transaction_date, '%Y-%m')
USING ROUND(SUM(amount), 2)
GROUP BY category;
```

| category | 2026-02 | 2026-03 | 2026-04  | 2026-05 | 2026-06 | 2026-07 |
| -------- | ------- | ------- | -------- | ------- | ------- | ------- |
| Income   | 5103.97 | 7586.95 | 5133.08  | 5120.14 | 5249.69 | 2544.7  |
| Shopping | -373.07 | -946.71 | -1081.88 | -477.48 | -454.99 | -647.21 |
| ...      | ...     | ...     | ...      | ...     | ...     | ...     |

---

## 🐍 Pandas & DuckDB Power-Moves

### Query in-memory DataFrames using DuckDB SQL

```python
import duckdb
import pandas as pd

conn = duckdb.connect("data/finance.db")
df = conn.execute("SELECT * FROM classified_ledger").df()

# Find merchants with > $500 annual spend
high_spenders_df = conn.execute("""
    SELECT merchant_name, SUM(amount) AS total_spent
    FROM df
    WHERE direction = 'Expense'
    GROUP BY merchant_name
    HAVING total_spent < -500
""").df()
```

---

### Multi-Index GroupBy & Unstacking

```python
multi_df = df.groupby(['account_name', 'category'])[['amount']].sum()
print(multi_df)
# Output: MultiIndex with account_name and category hierarchy

# Slice all "Groceries" by card
idx = pd.IndexSlice
groceries_only = multi_df.loc[idx[:, 'Groceries'], :]

# Unstack categories to columns
unstacked_df = multi_df.unstack(level='category', fill_value=0)
```

---

### Time Series Resampling for Monthly/Weekly Burn

```python
df['transaction_date'] = pd.to_datetime(df['transaction_date'])
time_df = df.set_index('transaction_date')

monthly_burn = time_df[time_df['direction'] == 'Expense']['amount'].resample('M').sum()
weekly_burn = time_df[time_df['direction'] == 'Expense']['amount'].resample('W').sum()
```

---

### Cumulative Running Net Worth

```python
bofa_flow = df[df['account_name'] == 'bofa'].sort_values('transaction_date')
bofa_flow['running_balance'] = bofa_flow['amount'].cumsum()
print(bofa_flow[['transaction_date', 'amount', 'running_balance']].tail())
```

---

## 🏪 Platform vs. Merchant Isolation (The "Convenience Tax")

To track markup fees, the engine splits the **Funding Channel** from the **Merchant**.

Example: `INSTACART*ALDI` yields

- Merchant: `Aldi` (pure Groceries)
- Channel: `instacart`

This enables you to see true spend at grocery stores versus platform markups.

---

### Platform Analysis — Using Pandas

```python
import duckdb
import pandas as pd

conn = duckdb.connect("data/finance.db")
df = conn.execute("SELECT category, channel, amount FROM classified_ledger").df()

platform_analysis = df.groupby(['category', 'channel'])[['amount']].agg(['sum', 'count'])

print(platform_analysis)
```

_Output:_

```
                          amount
                            sum   count
category   channel
Groceries  instacart   -19556.95   185
           pos         -18093.12   182
Meals      doordash     -4190.11   258
           pos          -3300.95   197

```

To compare direct vs. channels instantly:

```python
channel_comparison = platform_analysis['amount']['sum'].unstack(level='channel', fill_value=0)
print(channel_comparison)
```

---

### Platform Analysis — Using DuckDB

```sql
SELECT
    category,
    ROUND(SUM(CASE WHEN channel = 'pos' THEN amount ELSE 0 END), 2) AS spent_direct,
    ROUND(SUM(CASE WHEN channel = 'instacart' THEN amount ELSE 0 END), 2) AS spent_via_instacart,
    ROUND(SUM(CASE WHEN channel = 'doordash' THEN amount ELSE 0 END), 2) AS spent_via_doordash,
    ROUND(SUM(amount), 2) AS total_category_burn
FROM classified_ledger
WHERE direction = 'Expense'
GROUP BY ALL
ORDER BY total_category_burn ASC;
```

| category  | spent_direct | spent_via_instacart | spent_via_doordash | total_category_burn |
| --------- | ------------ | ------------------- | ------------------ | ------------------- |
| Groceries | -18093.12    | -19556.95           | 0.00               | -37650.07           |
| Meals     | -3300.95     | 0.00                | -4190.11           | -7491.06            |
