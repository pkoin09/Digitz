# core/ai_tier.py
import json
import duckdb
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = ROOT_DIR / "data" / "finance.db"


def get_unclassified_descriptions():
    """Fetches unique unclassified descriptions to minimize AI tokens."""
    conn = duckdb.connect(str(DB_FILE))
    res = conn.execute(
        """
        SELECT DISTINCT raw_description 
        FROM classified_ledger 
        WHERE category = 'UNCLASSIFIED'
    """
    ).fetchall()
    conn.close()
    return [row[0] for row in res]


def generate_ai_mappings(raw_descriptions):
    """
    Placeholder for your LLM call.
    Simulates sending the batch to an AI and getting a structured JSON payload back.
    """
    if not raw_descriptions:
        return {}

    print(f"Sending {len(raw_descriptions)} unique messy strings to the AI Tier...")

    # This system prompt enforces strict rules so the AI doesn't hallucinate categories
    system_prompt = """
    You are a financial data normalization engine. You take a list of messy bank statement descriptions 
    and return a structured JSON map matching them to standard Merchant Names and Categories 
    (e.g., Shopping, Groceries, Meals, Transport, Utilities, Entertainment, Income, Transfer, Unclassified).
    """

    # Simulating the structured JSON response your AI tier will return
    # In production, replace this with your actual LLM API call (e.g., google-genai SDK)
    simulated_llm_json = """
    {
        "APEX PET HOSPITAL CORP": {"merchant": "Apex Pet Hospital", "category": "Medical"},
        "BG-RESTAURANT SFO": {"merchant": "SFO Restaurant", "category": "Meals"},
        "RECURRING DEBIT VERIZON WIRELESS": {"merchant": "Verizon Wireless", "category": "Utilities"},
        "CRV*NETFLIX INC": {"merchant": "Netflix", "category": "Entertainment"}
    }
    """
    return json.loads(simulated_llm_json)


def apply_ai_classifications():
    """Pulls unclassified rows, consults the AI, and patches the database."""
    messy_strings = get_unclassified_descriptions()

    if not messy_strings:
        print("No unclassified transactions found. AI Tier idling.")
        return

    # Call the AI model
    mappings = generate_ai_mappings(messy_strings)

    # Patch the database with the intelligence payload
    conn = duckdb.connect(str(DB_FILE))
    patched_count = 0

    for raw_desc, info in mappings.items():
        # Update rows where the description matches
        conn.execute(
            """
            UPDATE classified_ledger
            SET merchant_name = ?,
                category = ?
            WHERE raw_description = ? AND category = 'UNCLASSIFIED'
        """,
            [info["merchant"], info["category"], raw_desc],
        )
        # Track our successful updates directly via a quick verification check or tracking the loop matches
        patched_count += 1
        
    print(f"AI Tier successfully processed {patched_count} unique merchant mapping rules.")
    conn.close()
