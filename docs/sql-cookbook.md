# SQL & Pandas Cookbook

[← Back to main README](../README.md)

A grab bag of queries and snippets for actually poking around your ledger once it's built — previewing raw files, summarizing spend, slicing by platform, and generating the tax report.

## i) Quick Previews & Category Summaries

### Instantly Preview a Raw CSV File

```sql
SELECT * FROM 'data/raw_data/chase_creditcard_1_transactions.csv' LIMIT 5;
```

| Transaction Date | Post Date  | Description              | Category     | Type | Amount  | Memo |
| ----------------- | ---------- | ------------------------ | ------------ | ---- | ------- | ---- |
| 2026-01-03        | 2026-01-05 | UBER EATS 8005928996     | Food & Drink | Sale | -46.33  | NULL |
| 2026-01-08        | 2026-01-09 | DOORDASH*CHIPOTLE        | Food & Drink | Sale | -16.77  | NULL |
| 2026-01-12        | 2026-01-13 | AMAZON.COM 2A097LG7      | Shopping     | Sale | -125.42 | NULL |
| 2026-01-15        | 2026-01-15 | SAFEWAY STORE 2214 SFO   | Groceries    | Sale | -100.51 | NULL |
| 2026-01-18        | 2026-01-19 | AMZN PRIME MEMBERSHIP    | Shopping     | Sale | -14.99  | NULL |

### Category Summary (Group By All)

```sql
SELECT category, direction, COUNT(*) AS n, ROUND(SUM(amount), 2) AS net
FROM classified_ledger
GROUP BY ALL
ORDER BY net ASC;
```

| category      | direction | n   | net        |
| ------------- | --------- | --- | ---------- |
| Transfer      | Expense   | 208 | -170668.34 |
| Groceries     | Expense   | 357 | -37083.69  |
| Shopping      | Expense   | 252 | -19525.22  |
| Meals         | Expense   | 548 | -10936.65  |
| Transport     | Expense   | 255 | -7565.30   |
| Cash          | Expense   | 9   | -600.00    |
| Medical       | Expense   | 23  | -553.13    |
| Travel        | Expense   | 2   | -506.09    |
| Subscriptions | Expense   | 39  | -502.61    |
| Fees          | Expense   | 11  | -249.22    |
| Utilities     | Expense   | 6   | -59.94     |
| Transfer      | Income    | 87  | 97983.86   |
| Income        | Income    | 88  | 223366.95  |

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

| category      | 2026-02  | 2026-03  | 2026-04  | 2026-05  | 2026-06  | 2026-07  |
| ------------- | -------- | -------- | -------- | -------- | -------- | -------- |
| Income        | 5103.97  | 7586.95  | 5133.08  | 5120.14  | 5249.69  | 2544.70  |
| Groceries     | -1148.39 | -1565.77 | -683.65  | -2229.27 | -2300.04 | -594.69  |
| Meals         | -420.93  | -574.57  | -419.58  | -536.61  | -551.86  | -201.55  |
| Shopping      | -373.07  | -946.71  | -1081.88 | -477.48  | -454.99  | -647.21  |
| Transport     | -264.08  | -450.10  | -390.12  | -396.97  | -403.40  | -76.58   |
| Transfer      | -2327.85 | -1487.16 | -1599.82 | -1651.01 | -1732.02 | -1589.30 |
 Subscriptions | -27.48   | -37.47   | -37.47   | -27.48   | -27.48   | -27.48   |
| Fees          | -7.53    | —        | -26.01   | —        | -23.59   | —        |
| Medical       | —        | -54.11   | —        | -47.41   | —        | —        |
| Cash          | -60.00   | -40.00   | —        | —        | —        | —        |
| Utilities     | -9.99    | —        | —        | -9.99    | -9.99    | —        |

### Trip Context — `ledger_with_trips` View

```sql
SELECT tx_date, merchant_string, amount, travel_context, trip_location
FROM ledger_with_trips
WHERE travel_context != 'Personal/Local'
ORDER BY tx_date;
```

| tx_date    | merchant_string                    | amount   | travel_context | trip_location |
| ---------- | ----------------------------------- | -------- | --------------- | ------------- |
| 2026-03-16 | LYFT *RIDE THU 2PM                   | -31.17   | Business         | San Francisco |
| 2026-03-17 | TACO BELL 1234                      | -18.42   | Business         | San Francisco |
| 2026-03-18 | WALMART ATM                         | -60.00   | Business         | San Francisco |

> **Category whitelist:** Only `Travel`, `Transport`, `Meals`, and `Cash` categories get trip context. Subscriptions, groceries, and shopping during a trip are assumed to be home-related. **P2P excluded:** Zelle/Venmo payments are also excluded from trip context — you can send money from anywhere, so they don't imply physical presence during a trip.

### Monthly Burn Breakdown — `monthly_burn_summary` View

```sql
SELECT * FROM monthly_burn_summary LIMIT 6;
```

| monthly_period | fixed_overhead | variable_lifestyle | total_operational_spend |
| -------------- | --------------- | -------------------- | ------------------------- |
| 2026-07        | 27.48           | 1520.03              | 1547.51                   |
| 2026-06        | 51.07           | 3710.29              | 3771.35                   |
| 2026-05        | 27.48           | 3687.74              | 3725.21                   |
| 2026-04        | 63.48           | 2575.23              | 2638.71                   |
| 2026-03        | 37.47           | 3591.26              | 3668.73                   |
| 2026-02        | 35.01           | 2206.47              | 2311.47                   |

> `fixed_overhead` = Subscriptions + Fees + Rent. `variable_lifestyle` = Meals + Groceries + Shopping + Transport + Travel + Medical.

### Business Trip Expenses — `master_ledger` View

The `master_ledger` view joins `classified_ledger` with `trips` and `cash_log` to give you a unified, context-enriched ledger. Here's how to pull all business trip expenses:

```sql
SELECT tx_date, merchant_string, amount, final_category, travel_context, trip_location
FROM master_ledger
WHERE travel_context = 'Business'
  AND final_category NOT IN ('Transfer', 'Income')
ORDER BY tx_date;
```

| tx_date    | merchant_string        | amount   | final_category | travel_context | trip_location |
| ---------- | ---------------------- | -------- | -------------- | -------------- | ------------- |
| 2026-03-16 | LYFT *RIDE THU 2PM      | -31.17   | Transport      | Business       | San Francisco |
| 2026-03-17 | TACO BELL 1234         | -18.42   | Meals          | Business       | San Francisco |
| 2026-03-18 | WALMART ATM            | -60.00   | Cash           | Business       | San Francisco |

### Loan Tracking — `master_ledger` View

Manual cash/loan overrides from `data/overrides/cash.csv` surface in `master_ledger` via the `is_account_receivable` flag:

```sql
SELECT tx_date, merchant_string, amount, final_category, is_account_receivable, notes
FROM master_ledger
WHERE is_account_receivable = TRUE
ORDER BY tx_date;
```

| tx_date    | merchant_string   | amount   | final_category | is_account_receivable | notes                          |
| ---------- | ----------------- | -------- | -------------- | ---------------------- | ------------------------------ |
| 2026-03-06 | Roommate Split    | -73.98   | Transfer       | TRUE                   | Temporary loan for utility split |

---

## ii) Pandas & DuckDB Power-Moves

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
  Credit Card Payment         87    -97983.86
Riverside Apartments LLC      41    -64568.94
              Costco        180    -22674.66
              Amazon        168    -12648.10
             Safeway        108     -8579.47
               Zelle         80     -8115.54
              Target         69     -4076.52
               Uber        153     -3723.10
               H-E-B         44     -3630.97
           Uber Eats         83     -2879.21
```

### Multi-Index GroupBy by Account & Category

```python
multi_df = df.groupby(['account_name', 'category'])[['amount']].sum()
print(multi_df)
```

```
                              amount
account_name  category
amex          Groceries    -5369.41
              Meals        -2189.75
              Shopping     -1667.44
              Transport    -1202.88
              Travel        -506.09
              Medical       -225.20
              Subscriptions  -215.82
              Fees           -39.00
              Transfer     17213.91
apple         Groceries    -5484.52
              Shopping     -3189.56
              Transport    -1117.63
              Meals         -982.54
              Subscriptions  -286.79
              Utilities       -59.94
              Transfer      9596.24
bofa          Transfer   -170668.34
              Income      223366.95
              Cash          -600.00
              Fees          -12.00
chase         Groceries    -8136.64
              Shopping     -4778.68
              Meals        -3128.69
              Transport    -2073.31
              Medical       -327.93
              Transfer     27523.65
discover      Groceries   -18093.12
              Shopping     -9889.54
              Meals        -4635.67
              Transport    -3171.48
              Fees         -198.22
              Transfer     43650.06
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
amex         Groceries  -5369.41
apple        Groceries  -5484.52
chase        Groceries  -8136.64
discover     Groceries -18093.12
```

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

## iii) Platform vs. Merchant Isolation (The "Convenience Tax")

To catch markup fees, the engine keeps the **funding channel** separate from the **merchant** itself.

For example, `INSTACART*ALDI` splits into:

- Merchant: `Aldi` (pure Groceries)
- Channel: `instacart`

That separation is what lets you compare true in-store grocery spend against what you're paying extra for delivery platforms.

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
| --------- | ------------- | --------------------- | -------------------- | ---------------------- | ---------------------- |
| Groceries | -18093.12     | -19556.95              | 0.00                  | -524.33                 | -37650.07               |
| Meals     | -3300.95      | 0.00                   | -4190.11              | -1241.88                | -14823.45               |
| Transport | -933.45       | 0.00                   | 0.00                  | -3822.45                | -7412.33                |

---

## iv) Tax Report Output

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
Shopping              | 254    |   -$20031.31
Meals                 | 312    |   -$14823.45
Transport             |  98    |    -$7412.33
Travel                |  34    |    -$6843.20
Subscriptions         |  72    |    -$3241.88
Medical               |  12    |    -$1834.55
Income                | 156    |   +$67284.19

========================================
 Report Saved! This is just for reference!:
 -> data/tax_summary_report.csv
========================================
```

---

[← Back to main README](../README.md)
