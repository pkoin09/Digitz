# Digitz Financial Ingestion Engine 🪙

A private, lightning-fast, local financial data pipeline that transforms messy, real-world bank CSV statement lines into structured, audit-ready tax ledgers using **DuckDB** and **Gemini AI**. It uses a **hybrid two-tier classification pipeline** to process and analyze transactions, combining high-efficiency SQL logic with AI-driven semantic enrichment.

## Data Flow & Classification Strategy

1. **Deterministic Classification (DuckDB Query Engine):**

- The majority of transactions, including well-known merchants (POS stores, subscription providers, utility companies, etc.) are classified using optimized, case-insensitive SQL matching rules for speed and accuracy.
- Pattern matching and string manipulation strip out marketplace prefixes (e.g., `"DD *"`, `"UBER EATS"`) to reveal the real merchant or platform beneath.

2. **AI-Powered Semantic Classification:**

- Transactions that remain `UNCLASSIFIED` after SQL rules are routed to `gemini-2.5-flash`, which performs contextual and semantic mapping beyond static rule chains.
- Every outbound batch is logged locally to `logs/ai_classification_audit.log` before transmission for privacy review.

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

**Only anonymized transaction descriptions are ever sent outbound** — to Gemini for classification. No account numbers, balances, or personal identifiers leave your machine.

> **API Key Storage:**  
> **macOS (recommended):** credentials are pulled directly from Keychain — zero plaintext exposure.  
> **Windows / other platforms:** set `GEMINI_API_KEY` in a `.env` file or as a system environment variable. The `.env` file is gitignored by default.

---

## 🚀 Key Features

- **Zero-Double Counting Reconciliation**  
  Automatically detects and nets out internal card payments, balance clearing, and bank-to-bank transfers into a neutral `Transfer` category, eliminating fake "Income" or double-counted "Expenses".
- **Dual-Tier Categorization**
  - Tier 1: Blazing-fast local SQL pattern matching for known merchants (handles masked strings like `SFW_#22`).
  - Tier 2: AI-powered patching sends unresolved transactions to `gemini-2.5-flash` for human-readable categorization.
- **Resilient API Architecture**  
  Implements exponential backoff with randomized jitter to recover from `503`/`429` server limits during AI patching.
- **Keychain / Env-Var Secured Credentials**  
  macOS: pulls from Keychain. All other platforms: reads `GEMINI_API_KEY` from environment or `.env` file (gitignored).
- **Local DuckDB Persistence**  
  Dedupes transactions based on MD5 cryptographic signatures (date + description + amount). No double ingestion, ever.
- **Trip & Cash Sidecar Context**  
  Overlay business trip date ranges and manual cash overrides onto the ledger without re-running ingestion. Builds a `master_ledger` view that joins travel context and loan flags into every transaction.

---

## 📁 System Architecture

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

## 🛠️ Getting Started

### 1. Prerequisites

**macOS — save your Gemini API key to Keychain:**

```sh
security add-generic-password -a "$USER" -s "gemini-api" -w "YOUR_GEMINI_API_KEY_HERE"
```

**Windows / other — add to `.env` file in the project root:**

```
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
```

### 2. Ingest Credit Card Statements

Credit card: expenses are _positive_, payments _negative_.

```sh
uv run main.py --file data/raw_data/chase_creditcard_1_transactions.csv   --name chase   --type credit_card
uv run main.py --file data/raw_data/amex_creditcard_2_transactions.csv    --name amex    --type credit_card
uv run main.py --file data/raw_data/apple_card_3_transactions.csv         --name apple   --type credit_card
uv run main.py --file data/raw_data/discover_creditcard_4_transactions.csv --name discover --type credit_card
```

### 3. Ingest Checking Accounts

Checking: deposits are _positive_, outflows _negative_.

```sh
uv run main.py --file data/raw_data/bofa_checking_5_transactions.csv --name bofa --type checking
```

### 4. Apply Trip & Cash Context (Sidecar Pipeline)

Edit `data/overrides/trips.csv` and `data/overrides/cash.csv`, then run:

```sh
uv run python -m core.pipeline
```

This syncs the override CSVs into DuckDB and builds the `ledger_with_trips`, `monthly_burn_summary`, and `master_ledger` views.

### 5. Tax and Coverage Report

```sh
# Generate report on an already-populated database:
uv run python -m core.tax_reporter

# Or combine ingestion + report in one pass:
uv run main.py --file data/raw_data/chase_creditcard_1_transactions.csv --name chase --type credit_card --report
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

_(Type `.exit` to leave DuckDB)_

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

| Transaction Date | Post Date  | Description              | Category     | Type | Amount  | Memo |
| ---------------- | ---------- | ------------------------ | ------------ | ---- | ------- | ---- |
| 2026-01-03       | 2026-01-05 | UBER EATS 8005928996     | Food & Drink | Sale | -46.33  | NULL |
| 2026-01-08       | 2026-01-09 | DOORDASH*CHIPOTLE        | Food & Drink | Sale | -16.77  | NULL |
| 2026-01-12       | 2026-01-13 | AMAZON.COM 2A097LG7      | Shopping     | Sale | -125.42 | NULL |
| 2026-01-15       | 2026-01-15 | SAFEWAY STORE 2214 SFO   | Groceries    | Sale | -100.51 | NULL |
| 2026-01-18       | 2026-01-19 | AMZN PRIME MEMBERSHIP    | Shopping     | Sale | -14.99  | NULL |

---

### Category Summary (Group By All)

```sql
SELECT category, direction, COUNT(*) AS n, ROUND(SUM(amount), 2) AS net
FROM classified_ledger
GROUP BY ALL
ORDER BY net ASC;
```

| category      | direction | n   | net         |
| ------------- | --------- | --- | ----------- |
| Transfer      | Expense   | 217 | -171268.34  |
| Groceries     | Expense   | 367 | -37650.07   |
| Shopping      | Expense   | 254 | -20031.31   |
| Meals         | Expense   | 312 | -14823.45   |
| Transport     | Expense   |  98 |  -7412.33   |
| Travel        | Expense   |  34 |  -6843.20   |
| Subscriptions | Expense   |  72 |  -3241.88   |
| Medical       | Expense   |  12 |  -1834.55   |
| Income        | Income    | 156 |  67284.19   |

---

### Monthly Category Spending (Pivot Table)

```sql
PIVOT (
  SELECT *
  FROM classified_ledger
  WHERE transaction_date >= DATE '2026-02-01'
    AND transaction_date <  DATE '2026-08-01'
)
ON strftime(transaction_date, '%Y-%m')
USING ROUND(SUM(amount), 2)
GROUP BY category;
```

| category      | 2026-02  | 2026-03  | 2026-04   | 2026-05  | 2026-06  | 2026-07  |
| ------------- | -------- | -------- | --------- | -------- | -------- | -------- |
| Income        | 5103.97  | 7586.95  | 5133.08   | 5120.14  | 5249.69  | 2544.70  |
| Groceries     | -841.22  | -1203.47 | -1094.33  | -978.55  | -1102.88 | -647.21  |
| Meals         | -612.44  | -891.30  | -744.18   | -537.90  | -803.55  | -491.33  |
| Shopping      | -373.07  | -946.71  | -1081.88  | -477.48  | -454.99  | -647.21  |
| Subscriptions | -274.87  | -274.87  | -274.87   | -274.87  | -274.87  | -274.87  |
| Transport     | -198.44  | -312.10  | -287.55   | -244.33  | -319.87  | -189.44  |
| Transfer      | -4200.00 | -4200.00 | -4200.00  | -4200.00 | -4200.00 | -2100.00 |

---

### Trip Context — `ledger_with_trips` View

```sql
SELECT tx_date, merchant_string, amount, travel_context, trip_location
FROM ledger_with_trips
WHERE travel_context != 'Personal/Local'
ORDER BY tx_date;
```

| tx_date    | merchant_string          | amount   | travel_context | trip_location |
| ---------- | ------------------------ | -------- | -------------- | ------------- |
| 2026-03-15 | AIRBNB RENTAL SF         | -312.00  | Business       | San Francisco |
| 2026-03-16 | DOORDASH*CHIPOTLE        | -16.45   | Business       | San Francisco |
| 2026-03-17 | BART CLIPPER CARD        | -12.50   | Business       | San Francisco |
| 2026-03-18 | MARRIOTT SFO AIRPORT     | -289.00  | Business       | San Francisco |
| 2026-03-20 | UNITED AIRLINES          | -387.00  | Business       | San Francisco |

---

### Monthly Burn Breakdown — `monthly_burn_summary` View

```sql
SELECT * FROM monthly_burn_summary LIMIT 6;s
```

| monthly_period | fixed_overhead | variable_lifestyle | total_operational_spend |
| -------------- | -------------- | ------------------ | ----------------------- |
| 2026-07        | 1850.00        | 2941.33            | 4791.33                 |
| 2026-06        | 1850.00        | 3102.44            | 4952.44                 |
| 2026-05        | 1850.00        | 2847.19            | 4697.19                 |
| 2026-04        | 1850.00        | 3219.87            | 5069.87                 |
| 2026-03        | 1850.00        | 4218.55            | 6068.55                 |
| 2026-02        | 1850.00        | 2825.17            | 4675.17                 |

> `fixed_overhead` = Subscriptions + Fees + Rent. `variable_lifestyle` = Meals + Groceries + Shopping + Transport + Travel + Medical.

---

## 🐍 Pandas & DuckDB Power-Moves

### Query the Ledger into a DataFrame

```python
import duckdb
import pandas as pd

conn = duckdb.connect("data/finance.db")
df = conn.execute("SELECT * FROM classified_ledger").df()
```

### Find Merchants with > $500 Annual Spend

```python
high_spenders_df = conn.execute("""
    SELECT merchant_name, COUNT(*) AS txn_count, ROUND(SUM(amount), 2) AS total_spent
    FROM classified_ledger
    WHERE direction = 'Expense'
    GROUP BY merchant_name
    HAVING total_spent < -500
    ORDER BY total_spent ASC
    LIMIT 10
""").df()

print(high_spenders_df.to_string(index=False))
```

```
        merchant_name  txn_count  total_spent
  Credit Card Payment        217   -171268.34
             Instacart        185    -19556.95
               Safeway        182    -18093.12
                Amazon        147    -12841.33
             DoorDash         258     -4190.11
                 Lyft          74     -3822.45
              Whole Foods       61     -3441.20
               DoorDash        197     -3300.95
               Marriott         12     -2841.00
              Starbucks         88     -1244.33
```

---

### Multi-Index GroupBy by Account & Category

```python
multi_df = df.groupby(['account_name', 'category'])[['amount']].sum()
print(multi_df)
```

```
                              amount
account_name  category
amex          Groceries    -2841.50
              Meals        -1205.33
              Shopping     -3102.45
              Subscriptions  -274.87
              Travel        -1843.00
apple         Meals         -934.21
              Shopping     -1847.33
              Transport      -612.44
bofa          Income        9844.20
              Transfer    -15234.00
chase         Groceries    -1924.11
              Meals        -2847.23
              Shopping     -4291.10
              Subscriptions  -274.87
              Transport      -933.45
discover      Meals         -876.54
              Shopping     -2140.67
              Subscriptions  -274.87
```

```python
# Slice all Groceries spend by card
idx = pd.IndexSlice
groceries_only = multi_df.loc[idx[:, 'Groceries'], :]
print(groceries_only)
```

```
                          amount
account_name category
amex         Groceries -2841.50
chase        Groceries -1924.11
```

---

### Time Series Resampling — Monthly & Weekly Burn

```python
df['transaction_date'] = pd.to_datetime(df['transaction_date'])
time_df = df.set_index('transaction_date')

monthly_burn = time_df[time_df['direction'] == 'Expense']['amount'].resample('ME').sum()
weekly_burn  = time_df[time_df['direction'] == 'Expense']['amount'].resample('W').sum()

print(monthly_burn.tail(6))
```

```
transaction_date
2026-02-28   -5103.87
2026-03-31   -6247.19
2026-04-30   -4985.62
2026-05-31   -5418.44
2026-06-30   -4793.21
2026-07-31   -4791.33
Freq: ME, Name: amount, dtype: float64
```

---

### Cumulative Running Balance (Checking Account)

```python
bofa_flow = df[df['account_name'] == 'bofa'].sort_values('transaction_date')
bofa_flow['running_balance'] = bofa_flow['amount'].cumsum()
print(bofa_flow[['transaction_date', 'merchant_name', 'amount', 'running_balance']].tail(6))
```

```
  transaction_date    merchant_name   amount  running_balance
          2026-07-01   Direct Deposit  5249.69          5249.69
          2026-07-03         Landlord -2100.00          3149.69
          2026-07-08           Amazon  -143.21          3006.48
          2026-07-12         Instacart  -87.43          2919.05
          2026-07-15       Chase Card -1250.00          1669.05
          2026-07-19          Safeway   -84.33          1584.72
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
conn = duckdb.connect("data/finance.db")
df = conn.execute("SELECT category, channel, amount FROM classified_ledger").df()

platform_analysis = df.groupby(['category', 'channel'])[['amount']].agg(['sum', 'count'])
platform_analysis.columns = ['total_spent', 'txn_count']
print(platform_analysis)
```

```
                           total_spent  txn_count
category   channel
Groceries  instacart       -19556.95        185
           pos             -18093.12        182
           uber_eats          -524.33         12
Meals      doordash          -4190.11        258
           pos               -3300.95        197
           uber_eats         -1241.88         47
Transport  pos                -933.45         74
           uber_eats         -3822.45         74
```

---

### Platform Analysis — Using DuckDB

```sql
SELECT
    category,
    ROUND(SUM(CASE WHEN channel = 'pos'       THEN amount ELSE 0 END), 2) AS spent_direct,
    ROUND(SUM(CASE WHEN channel = 'instacart' THEN amount ELSE 0 END), 2) AS spent_via_instacart,
    ROUND(SUM(CASE WHEN channel = 'doordash'  THEN amount ELSE 0 END), 2) AS spent_via_doordash,
    ROUND(SUM(CASE WHEN channel = 'uber_eats' THEN amount ELSE 0 END), 2) AS spent_via_uber_eats,
    ROUND(SUM(amount), 2) AS total_category_burn
FROM classified_ledger
WHERE direction = 'Expense'
GROUP BY ALL
ORDER BY total_category_burn ASC;
```

| category  | spent_direct | spent_via_instacart | spent_via_doordash | spent_via_uber_eats | total_category_burn |
| --------- | ------------ | ------------------- | ------------------ | ------------------- | ------------------- |
| Groceries | -18093.12    | -19556.95           | 0.00               | -524.33             | -37650.07           |
| Meals     | -3300.95     | 0.00                | -4190.11           | -1241.88            | -14823.45           |
| Transport | -933.45      | 0.00                | 0.00               | -3822.45            | -7412.33            |

---

## 🧾 Tax Report Output

```sh
uv run python -m core.tax_reporter
```

```
========================================
       GENERATING TAX REPORT SUMMARY
========================================

--- Summary by Category ---
Category             | Count  | Total Amount
--------------------------------------------
Transfer             | 217    |  -$171268.34
Groceries            | 367    |   -$37650.07
Shopping             | 254    |   -$20031.31
Meals                | 312    |   -$14823.45
Transport            |  98    |    -$7412.33
Travel               |  34    |    -$6843.20
Subscriptions        |  72    |    -$3241.88
Medical              |  12    |    -$1834.55
Income               | 156    |   +$67284.19

========================================
 Report Saved! This is just for reference!:
 -> data/tax_summary_report.csv
========================================
```
