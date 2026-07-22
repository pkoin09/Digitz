# Finance Tracker Engine — Project Context & Handoff Guide

## 📌 Executive Summary
This project is an automated personal finance classification pipeline built in Python and DuckDB. It parses raw bank and credit card transaction exports, applies deterministic SQL rule-based categorization, runs an AI fallback layer for unclassified transactions, and outputs clean analytical ledgers and views.

---

## 🛠️ Tech Stack & Database Architecture
* **Language & Runtime:** Python 3.x
* **Database Engine:** DuckDB (`data/finance.db`)
* **Core Modules:**
  * `core/classifier.py`: Runs deterministic classification, schema updates, and handles AI fallback triggers.
  * `core/ai_tier.py`: AI classification engine for unclassified transactions (`merchant_name = 'UNKNOWN'`).
  * `core/trip_manager.py`: (Newly planned/in-progress) Handles validated trip metadata.
  * `utils/logger.log`: Local file audit for AI fallback payloads.

### Ledger Schema (`classified_ledger`)
* `transaction_id` (TEXT, PK)
* `transaction_date` (DATE)
* `account_name` (TEXT)
* `raw_description` (TEXT)
* `merchant_name` (TEXT)
* `category` (TEXT)
* `sub_category` (TEXT)
* `amount` (DOUBLE)
* `direction` (TEXT)
* `channel` (TEXT)

---

## ✅ Completed Milestones & Status

### 1. Classification Engine Rules Locked (`core/classifier.py`)
* **Merchant & Category Standardizations:**
  * Intermediary Delivery Platform stripping (DoorDash, Instacart, Grubhub).
  * Explicit Uber Eats vs. Uber Rideshare separation.
  * Direct merchant catchers for Lyft, CVS, Subscriptions, Gas stations, Grocery stores.
* **Credit Card & Internal Payment Alignment (FIXED):**
  * Merchant Name: `'Credit Card Payment'` or `'Internal Transfer'`.
  * Category: `'Transfer'`.
  * Sub-Category: Added explicit mappings for `'Credit Card Payment'` and `'Internal Transfer'` (replaces legacy `'UNCLASSIFIED'` behavior).

---

## 📋 Next Immediate To-Dos & Active Tasks

### Task 1: Create `core/trip_manager.py` (In Progress)
* Implement trip metadata tracking with flexible human-readable dates (`MM/DD/YYYY`).
* Auto-convert inputs to ISO `YYYY-MM-DD` for DuckDB native storage.
* **Schema for `trips` Table:**
  ```sql
  CREATE TABLE IF NOT EXISTS trips (
      trip_id VARCHAR PRIMARY KEY,
      start_date DATE NOT NULL,
      end_date DATE NOT NULL,
      trip_type VARCHAR NOT NULL, -- 'Business' | 'Personal'
      destination VARCHAR NOT NULL,
      notes VARCHAR
  );

Python Logic Spec:
from datetime import datetime
# Parse from MM/DD/YYYY -> Save as native DuckDB DATE
s_date = datetime.strptime(start_date_str, "%m/%d/%Y").date()
e_date = datetime.strptime(end_date_str, "%m/%d/%Y").date()

Task 2: Build the Dynamic Trip Join View
Create a view joining classified_ledger with trips on date ranges to assign travel_context without hardcoding trip rules into the main classifier.

CREATE OR REPLACE VIEW ledger_with_trips AS
SELECT 
    l.*,
    COALESCE(t.trip_type, 'Personal/Local') AS travel_context,
    t.trip_id,
    t.destination
FROM classified_ledger l
LEFT JOIN trips t 
  ON l.transaction_date >= t.start_date 
 AND l.transaction_date <= t.end_date;

Task 3: Deploy Fixed vs. Variable Monthly Burn View (monthly_burn_summary)
Build reporting query to isolate true monthly burn rate by excluding internal transfers and credit card payments.

CREATE OR REPLACE VIEW monthly_burn_summary AS 
SELECT 
    strftime(transaction_date, '%Y-%m') AS monthly_period,
    ROUND(SUM(CASE 
        WHEN category IN ('Subscriptions', 'Fees') 
          OR (category = 'Transfer' AND sub_category = 'Rent Payment')
        THEN ABS(amount) ELSE 0 
    END), 2) AS fixed_overhead,
    ROUND(SUM(CASE 
        WHEN category IN ('Meals', 'Groceries', 'Shopping', 'Transport', 'Travel', 'Medical')
        THEN ABS(amount) ELSE 0 
    END), 2) AS variable_lifestyle,
    ROUND(SUM(CASE 
        WHEN category NOT IN ('Transfer', 'Income') 
          OR sub_category = 'Rent Payment'
        THEN ABS(amount) ELSE 0 
    END), 2) AS total_operational_spend
FROM ledger_with_trips
GROUP BY 1
ORDER BY 1 DESC;

