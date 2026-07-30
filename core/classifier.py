from pathlib import Path
import duckdb
import uuid

# Import the core classification engines and audit handlers
from core.ai_tier import apply_ai_classifications
from utils.logger import log_cloud_payload

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = ROOT_DIR / "data" / "finance.db"


def run_classification_pipeline():
    """Sweeps through raw_transactions and populates the classified ledger table."""
    conn = duckdb.connect(str(DB_FILE))

    print("Running classification pipeline...")

    # 1. Establish the clean targets architecture schema
    conn.execute("""
        CREATE TABLE IF NOT EXISTS classified_ledger (
            transaction_id TEXT PRIMARY KEY,
            transaction_date DATE,
            account_name TEXT,
            raw_description TEXT,
            merchant_name TEXT,
            category TEXT,
            sub_category TEXT,
            amount DOUBLE,
            direction TEXT,
            channel TEXT
        );
    """)

    print("Running strategic classification sweep...")
    conn.execute("""
        INSERT INTO classified_ledger (
            transaction_id, transaction_date, account_name, 
            raw_description, merchant_name, category, sub_category, amount, direction, channel
        )
        SELECT 
            transaction_id,
            transaction_date,
            account_name,
            raw_description,
            CASE 
                -- A. Explicit Intermediary Delivery Platforms Stripping (Run First)
                WHEN raw_description ILIKE 'DOORDASH*%' THEN REGEXP_REPLACE(raw_description, '(?i)^DOORDASH\*', '')
                WHEN raw_description ILIKE 'DD *%' THEN REGEXP_REPLACE(raw_description, '(?i)^DD \*', '')
                WHEN raw_description ILIKE 'INSTACART*%' THEN REGEXP_REPLACE(raw_description, '(?i)^INSTACART\*', '')
                WHEN raw_description ILIKE 'GRUBHUB*%' THEN REGEXP_REPLACE(raw_description, '(?i)^GRUBHUB\*', '')
                
                -- Isolate Uber Eats specifically before the general Uber catch-all rules execute
                WHEN raw_description ILIKE '%UBER%EATS%' THEN 'Uber Eats'
                WHEN raw_description ILIKE '%UBER%TRIP%' THEN 'Uber'
                
                -- New Direct Catchers for Rideshare/Pharmacy variations
                WHEN raw_description ILIKE '%LYFT%' THEN 'Lyft'
                WHEN raw_description ILIKE '%CVS%' THEN 'CVS Pharmacy'
                
                -- B. Direct Credit Card Payment Catchers
                WHEN raw_description ILIKE '%PAYMENT%THANK%YOU%' THEN 'Credit Card Payment'
                WHEN raw_description ILIKE '%INTERNET%PAYMENT%' THEN 'Credit Card Payment'
                WHEN raw_description ILIKE '%ONLINE%PAYMENT%' THEN 'Credit Card Payment'
                WHEN UPPER(raw_description) = 'PAYMENT' THEN 'Credit Card Payment'
                
                -- C. Cash, ATM & Fees
                WHEN raw_description ILIKE '%ATM WITHDRAWAL%' THEN 'ATM Cash Extraction'
                WHEN raw_description ILIKE '%MAINTENANCE FEE%' THEN 'Bank Fees'
                WHEN raw_description ILIKE '%FINANCE CHARGE%' THEN 'Interest Charge'
                
                -- D. Digital Subscriptions & Services
                WHEN raw_description ILIKE '%NETFLIX%' THEN 'Netflix'
                WHEN raw_description ILIKE '%SPOTIFY%' THEN 'Spotify'
                WHEN raw_description ILIKE '%APPLE.COM/BILL%' THEN 'Apple'
                WHEN raw_description ILIKE '%HULU%' THEN 'Hulu'
                
                -- E. Gas / Fuel Stations
                WHEN raw_description ILIKE '%SHELL%' THEN 'Shell'
                WHEN raw_description ILIKE '%CHEVRON%' THEN 'Chevron'
                WHEN raw_description ILIKE '%EXXON%' THEN 'ExxonMobil'
                
                -- F. Standard Rules & General Fallbacks (Run Last)
                WHEN raw_description ILIKE '%MARRIOTT%' THEN 'Marriott'
                WHEN raw_description ILIKE '%METROCARD%' THEN 'MTA MetroCard'
                WHEN raw_description ILIKE '%SFW_%' OR raw_description ILIKE '%SAFEWAY%' THEN 'Safeway'
                WHEN raw_description ILIKE '%COSTCO%' THEN 'Costco'
                WHEN raw_description ILIKE '%TARGET%' THEN 'Target'
                WHEN raw_description ILIKE '%AMAZON%' OR raw_description ILIKE '%AMZN%' THEN 'Amazon'
                WHEN raw_description ILIKE '%MCDONALDS%' THEN 'McDonalds'
                WHEN raw_description ILIKE '%CHIPOTLE%' THEN 'Chipotle'
                WHEN raw_description ILIKE '%STARBUCKS%' THEN 'Starbucks'
                WHEN raw_description ILIKE '%SWEETGREEN%' THEN 'Sweetgreen'
                WHEN raw_description ILIKE '%AUTOMATIC PAYMENT%' OR raw_description ILIKE '%ONLINE CC PAYMENT%' THEN 'Internal Transfer'
                ELSE 'UNKNOWN' 
            END AS merchant_name,
            
            CASE 
                -- Reclassify Credit Card Payments & Internal Movements
                WHEN raw_description ILIKE '%PAYMENT%THANK%YOU%' 
                  OR raw_description ILIKE '%INTERNET%PAYMENT%' 
                  OR raw_description ILIKE '%ONLINE%PAYMENT%' 
                  OR UPPER(raw_description) = 'PAYMENT' 
                  OR raw_description ILIKE '%AUTOMATIC PAYMENT%' 
                  OR raw_description ILIKE '%ONLINE CC PAYMENT%' THEN 'Transfer'
                
                -- Cash & Fees
                WHEN raw_description ILIKE '%ATM WITHDRAWAL%' THEN 'Cash'
                WHEN raw_description ILIKE '%MAINTENANCE FEE%' OR raw_description ILIKE '%FINANCE CHARGE%' THEN 'Fees'
                
                -- Travel & Lodging
                WHEN raw_description ILIKE '%MARRIOTT%' THEN 'Travel'
                
                -- Medical & Health Services
                WHEN raw_description ILIKE '%CVS%' THEN 'Medical'
                
                -- Subscriptions
                WHEN raw_description ILIKE '%NETFLIX%' 
                  OR raw_description ILIKE '%SPOTIFY%' 
                  OR raw_description ILIKE '%HULU%' 
                  OR raw_description ILIKE '%APPLE.COM/BILL%' THEN 'Subscriptions'
                
                -- Delivery Platforms Category Mappings
                WHEN raw_description ILIKE '%INSTACART%' THEN 'Groceries'
                WHEN raw_description ILIKE '%DOORDASH%' OR raw_description ILIKE 'DD *%' THEN 'Meals'
                WHEN raw_description ILIKE '%UBER%EATS%' THEN 'Meals'
                WHEN raw_description ILIKE '%GRUBHUB%' THEN 'Meals'
                
                -- Everyday Commuting, Rides, & Fuel
                WHEN raw_description ILIKE '%METROCARD%' 
                  OR raw_description ILIKE '%UBER%TRIP%' 
                  OR raw_description ILIKE '%LYFT%'
                  OR raw_description ILIKE '%SHELL%' 
                  OR raw_description ILIKE '%CHEVRON%' 
                  OR raw_description ILIKE '%EXXON%' THEN 'Transport'
                
                -- Standard Direct Rules
                WHEN raw_description ILIKE '%SFW_%' OR raw_description ILIKE '%SAFEWAY%' THEN 'Groceries'
                WHEN raw_description ILIKE '%COSTCO%' THEN 'Groceries'
                WHEN raw_description ILIKE '%TARGET%' THEN 'Shopping'
                WHEN raw_description ILIKE '%AMAZON%' OR raw_description ILIKE '%AMZN%' THEN 'Shopping'
                WHEN raw_description ILIKE '%MCDONALDS%' 
                  OR raw_description ILIKE '%CHIPOTLE%' 
                  OR raw_description ILIKE '%STARBUCKS%' 
                  OR raw_description ILIKE '%SWEETGREEN%' THEN 'Meals'
                ELSE 'UNCLASSIFIED' 
            END AS category,
            
            CASE 
                -- 2. EXPLICIT SUB-CATEGORY MICRO TAGS
                WHEN raw_description ILIKE '%UBER%EATS%' THEN 'Food Delivery'
                WHEN raw_description ILIKE '%UBER%TRIP%' THEN 'Uber Rides'
                WHEN raw_description ILIKE '%LYFT%' THEN 'Rideshare'
                WHEN raw_description ILIKE '%CVS%' THEN 'Pharmacy'
                WHEN raw_description ILIKE '%METROCARD%' THEN 'Public Transit'
                WHEN raw_description ILIKE '%MARRIOTT%' THEN 'Lodging'
                WHEN raw_description ILIKE '%INSTACART%' THEN 'Grocery Delivery'
                WHEN raw_description ILIKE '%DOORDASH%' OR raw_description ILIKE 'DD *%' THEN 'Food Delivery'
                WHEN raw_description ILIKE '%GRUBHUB%' THEN 'Food Delivery'
                WHEN raw_description ILIKE '%NETFLIX%' OR raw_description ILIKE '%HULU%' THEN 'Video Streaming'
                WHEN raw_description ILIKE '%SPOTIFY%' THEN 'Audio Streaming'
                WHEN raw_description ILIKE '%SHELL%' OR raw_description ILIKE '%CHEVRON%' OR raw_description ILIKE '%EXXON%' THEN 'Gas'

                -- Merchant-specific sub-categories (refine UNCLASSIFIED entries)
                WHEN raw_description ILIKE '%STARBUCKS%' THEN 'Coffee Shop'
                WHEN raw_description ILIKE '%CHIPOTLE%' THEN 'Fast Food'
                WHEN raw_description ILIKE '%COSTCO%' THEN 'Wholesale Club'
                WHEN raw_description ILIKE '%SAFEWAY%' OR raw_description ILIKE '%SFW_%' THEN 'Grocery Store'
                WHEN raw_description ILIKE '%AMAZON%' OR raw_description ILIKE '%AMZN%' THEN 'Online Retail'
                WHEN raw_description ILIKE '%TARGET%' THEN 'Department Store'
                WHEN raw_description ILIKE '%APPLE.COM/BILL%' THEN 'Digital Subscription'

                -- Cash & Fees sub-categories
                WHEN raw_description ILIKE '%ATM WITHDRAWAL%' THEN 'ATM Withdrawal'
                WHEN raw_description ILIKE '%FINANCE CHARGE%' THEN 'Interest Charge'
                WHEN raw_description ILIKE '%MAINTENANCE FEE%' THEN 'Bank Fee'

                -- Transfer sub-categories
                WHEN raw_description ILIKE '%PAYMENT%THANK%YOU%'
                  OR raw_description ILIKE '%INTERNET%PAYMENT%'
                  OR raw_description ILIKE '%ONLINE%PAYMENT%'
                  OR UPPER(raw_description) = 'PAYMENT' THEN 'Credit Card Payment'
                ELSE 'UNCLASSIFIED'
            END AS sub_category,
            
            amount,
            direction,
            CASE 
                -- Isolate Intermediary Marketplace Channels
                WHEN raw_description ILIKE '%DOORDASH%' OR raw_description ILIKE 'DD *%' THEN 'doordash'
                WHEN raw_description ILIKE '%INSTACART%' THEN 'instacart'
                WHEN raw_description ILIKE '%UBER%EATS%' THEN 'uber_eats'
                WHEN raw_description ILIKE '%GRUBHUB%' THEN 'grubhub'
                
                -- Digital Channels vs POS vs Direct Banks
                WHEN raw_description ILIKE '%UBER%TRIP%' 
                  OR raw_description ILIKE '%LYFT%'
                  OR raw_description ILIKE '%NETFLIX%' 
                  OR raw_description ILIKE '%SPOTIFY%' 
                  OR raw_description ILIKE '%HULU%' 
                  OR raw_description ILIKE '%APPLE.COM/BILL%' THEN 'online'
                WHEN raw_description ILIKE '%ATM WITHDRAWAL%' THEN 'atm'
                WHEN raw_description ILIKE '%PRIME*MEMBERSHIP%' THEN 'online'
                WHEN raw_description ILIKE '%ACH%' THEN 'ach'
                WHEN raw_description ILIKE '%VENMO%' OR raw_description ILIKE '%PAYPAL%' THEN 'p2p'
                WHEN raw_description ILIKE '%ONLINE%' OR raw_description ILIKE '%AMZN%' THEN 'online'
                ELSE 'pos'
            END AS channel
        FROM raw_transactions
        ON CONFLICT (transaction_id) DO UPDATE SET
            merchant_name = EXCLUDED.merchant_name,
            category = EXCLUDED.category,
            sub_category = EXCLUDED.sub_category,
            channel = EXCLUDED.channel;
    """)
    print("Local SQL sweep complete.")

    # 2. TRIGGER ACTIVE CLOUD AI FALLBACK ENGINE
    print("Evaluating remaining unclassified records for AI Fallback loop...")
    unknown_records = conn.execute("""
        SELECT transaction_id, raw_description, amount 
        FROM classified_ledger 
        WHERE merchant_name = 'UNKNOWN';
    """).fetchall()

    if unknown_records:
        payload_to_send = [
            {"tx_id": row[0], "desc": row[1], "amt": float(row[2])} for row in unknown_records
        ]

        batch_id = str(uuid.uuid4())

        # Log payload accurately to local file environment audits
        print(f"Logging outbound payload for batch {batch_id} to local audit log...")
        log_cloud_payload(batch_id, payload_to_send)

        # Close local connection cleanly to prevent locks while ai_tier writes updates
        conn.close()

        # Fire off the automated cloud classification engine
        apply_ai_classifications()
    else:
        print("0 records flagged as 'UNKNOWN'. Skipping Cloud AI validation tier.")
        conn.close()

    print("Classification sweep complete.")


def verify_results():
    """Quick console reporting tool to see our classification breakdown."""
    conn = duckdb.connect(str(DB_FILE))
    print("\n--- Current Ledger Status ---")

    res = conn.execute("""
        SELECT category, COUNT(*), SUM(amount) 
        FROM classified_ledger 
        GROUP BY category
    """).fetchall()

    for row in res:
        print(f"Category: {row[0]:<15} | Count: {row[1]:<3} | Total: ${row[2]:,.2f}")

    conn.close()
