# core/ai_tier.py
import os
import json
import time
import random
import subprocess
import uuid
import duckdb
from pathlib import Path
from google import genai
from google.genai import types
from google.genai.errors import APIError
# Import the audit utility from your shared utilities path
from utils.logger import log_cloud_payload

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = ROOT_DIR / "data" / "finance.db"


def get_gemini_api_key():
    """Defensively retrieves the Gemini API Key from macOS Keychain or Environment."""
    # 1. Try macOS Keychain
    try:
        return (
            subprocess.check_output(
                ["security", "find-generic-password", "-s", "gemini-api", "-w"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 2. Fall back to Environment Variable
    return os.environ.get("GEMINI_API_KEY")


def get_unclassified_descriptions():
    """Fetches unique unclassified transactions based on unknown merchant criteria."""
    conn = duckdb.connect(str(DB_FILE))
    res = conn.execute("""
        SELECT DISTINCT raw_description 
        FROM classified_ledger 
        WHERE merchant_name = 'UNKNOWN'
    """).fetchall()
    conn.close()
    return [row[0] for row in res]


def generate_ai_mappings(client, raw_descriptions, max_retries: int = 5):
    """
    Sends a unique list of unclassified descriptions to Gemini for structured categorization.
    Implements dynamic backoff + random jitter to survive temporary API outages (503 / 429).
    """
    if not raw_descriptions:
        return {}

    # Create a batch id and audit-log the raw outbound strings locally before hitting the wire
    batch_id = str(uuid.uuid4())
    log_cloud_payload(batch_id, [{"desc": d} for d in raw_descriptions])

    print(f"Sending {len(raw_descriptions)} unique messy strings to Gemini [Batch: {batch_id}]...")

    prompt = f"""
    You are a financial data normalization engine. Analyze this list of raw bank statement descriptions.
    For each item, extract a clean Merchant Name, assign a macro Category, determine a hyper-specific Sub-Category, and isolate the transactional Channel.

    Allowed Categories & Guidelines:
    - Shopping: Retail stores, online retail, department stores, apparel, and hardware.
    - Groceries: Supermarkets, grocery stores, wholesale clubs, and convenience stores.
    - Meals: Restaurants, fast food joints, coffee shops, bakeries, and food delivery services.
    - Transport: Rideshares (Uber, Lyft), public transit, parking, toll roads, and gas stations.
    - Utilities: Phone bills, electricity, internet, gas, and digital streaming subscriptions.
    - Entertainment: Concerts, movies, sporting events, gaming platforms, and recreational venues.
    - Income: Payroll direct deposits, interest earned, freelance earnings, or gig-work revenue.
    - Transfer: Credit card payments, moving money between checking/savings, or paying off credit card balances.
    - Medical: Pharmacies, doctor co-pays, hospital visits, dental work, and vision clinics.
    - Fees: Bank maintenance fees, credit card interest charges, annual fees, and overdraft charges.

    Channel Target Inferences:
    - Set channel to 'doordash', 'uber_eats', 'instacart', or 'grubhub' if those delivery middleman apps handled the logistics.
    - Set channel to 'online' for standard digital subscription entities, web hosting, or clear e-commerce invoices.
    - Set channel to 'pos' for physical, local retail operations, store numbers, or standard local storefront terminals.

    Raw Descriptions to process:
    {json.dumps(raw_descriptions, indent=2)}
    """

    # FIXED: Added missing 'sub_category' and 'channel' fields to the JSON parser schema mapping
    array_schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "raw_description": {"type": "STRING"},
                "merchant": {"type": "STRING"},
                "category": {"type": "STRING"},
                "sub_category": {"type": "STRING"},
                "channel": {"type": "STRING"},
            },
            "required": ["raw_description", "merchant", "category", "sub_category", "channel"],
        },
    }

    base_delay = 2.0  # Initial wait duration in seconds

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_schema=array_schema
                ),
            )

            raw_results = json.loads(response.text)

            # Re-map array outputs into structural key-lookup fields
            processed_mappings = {}
            for item in raw_results:
                processed_mappings[item["raw_description"]] = {
                    "merchant": item["merchant"],
                    "category": item["category"],
                    "sub_category": item["sub_category"],
                    "channel": item["channel"],
                }

            return processed_mappings

        except APIError as e:
            if e.code in [503, 429] and attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                jitter = random.uniform(-1.0, 1.0)
                sleep_time = max(0.5, delay + jitter)
                print(
                    f"\n⚠️ API Busy ({e.code}). Retrying in {sleep_time:.2f}s... (Attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(sleep_time)
            else:
                print(f"AI Tier Error: Generation failed after {attempt + 1} attempts. Details: {e}")
                return {}
        except Exception as e:
            print(f"Unexpected Integration Error: {e}")
            return {}


def apply_ai_classifications():
    """Pulls unclassified rows, consults Gemini, and patches the database ledger."""
    api_key = get_gemini_api_key()

    if not api_key:
        print(
            "AI Tier Warning: GEMINI_API_KEY not found in macOS Keychain or Environment variables. Skipping."
        )
        return

    messy_strings = get_unclassified_descriptions()

    if not messy_strings:
        print("No unclassified transactions found. AI Tier idling.")
        return

    client = genai.Client(api_key=api_key)
    mappings = generate_ai_mappings(client, messy_strings)

    if not mappings:
        return

    conn = duckdb.connect(str(DB_FILE))
    patched_count = 0

    for raw_desc, info in mappings.items():
        conn.execute(
            """
            UPDATE classified_ledger
            SET merchant_name = ?,
                category = ?,
                sub_category = ?,
                channel = ?
            WHERE raw_description = ? AND merchant_name = 'UNKNOWN'
        """,
            [
                info.get("merchant", "UNKNOWN"),
                info.get("category", "UNCLASSIFIED"),
                info.get("sub_category", "UNCLASSIFIED"),
                info.get("channel", "pos"),
                raw_desc,
            ],
        )
        patched_count += 1

    print(f"AI Tier successfully integrated {patched_count} live merchant rules into the ledger.")
    conn.close()