import os
import json
import subprocess
import duckdb
from pathlib import Path
from google import genai
from google.genai import types

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = ROOT_DIR / "data" / "finance.db"

def get_gemini_api_key():
    """Defensively retrieves the Gemini API Key from macOS Keychain or Environment."""
    # 1. Try macOS Keychain
    try:
        # Targets the exact service name "-s gemini-api" you just registered
        return subprocess.check_output(
            ["security", "find-generic-password", "-s", "gemini-api", "-w"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 2. Fall back to Environment Variable
    return os.environ.get("GEMINI_API_KEY")

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


def generate_ai_mappings(client, raw_descriptions):
    """Sends a unique list of unclassified descriptions to Gemini for structured categorization."""
    if not raw_descriptions:
        return {}
    
    print(f"Sending {len(raw_descriptions)} unique messy strings to Gemini...")

    prompt = f"""
    You are a financial data normalization engine. Analyze this list of raw bank statement descriptions.
    For each item, extract a clean, recognizable Merchant Name and assign the best matching Category.

    Allowed Categories: [Shopping, Groceries, Meals, Transport, Utilities, Entertainment, Income, Transfer, Medical, Unclassified]

    Raw Descriptions to process:
    {json.dumps(raw_descriptions, indent=2)}
    """

    # We shift from a dynamic dictionary to a flat, well-defined array of objects
    array_schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "raw_description": {"type": "STRING"},
                "merchant": {"type": "STRING"},
                "category": {"type": "STRING"}
            },
            "required": ["raw_description", "merchant", "category"]
        }
    }

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=array_schema
            )
        )
        
        # Parse the JSON array response
        raw_results = json.loads(response.text)
        
        # Convert the array back into the dictionary mapping our database loop expects
        # e.g., {"MESSY_DESC": {"merchant": "Clean", "category": "Type"}}
        processed_mappings = {}
        for item in raw_results:
            processed_mappings[item['raw_description']] = {
                "merchant": item['merchant'],
                "category": item['category']
            }
            
        return processed_mappings
        
    except Exception as e:
        print(f"AI Tier Error: Failed to generate classifications. Details: {e}")
        return {}

def apply_ai_classifications():
    """Pulls unclassified rows, consults Gemini, and patches the database ledger."""
    # Retrieve key from Keychain or Environment
    api_key = get_gemini_api_key()
    
    if not api_key:
        print("AI Tier Warning: GEMINI_API_KEY not found in macOS Keychain or Environment variables. Skipping.")
        return

    messy_strings = get_unclassified_descriptions()
    
    if not messy_strings:
        print("No unclassified transactions found. AI Tier idling.")
        return

    # Initialize client explicitly passing the retrieved token secret
    client = genai.Client(api_key=api_key)
    
    # Pass the client wrapper downstream to the generator execution function
    # Note: Quick tweak below—let's pass the active client directly to generate_ai_mappings
    mappings = generate_ai_mappings(client, messy_strings)
    
    if not mappings:
        return

    conn = duckdb.connect(str(DB_FILE))
    patched_count = 0
    
    for raw_desc, info in mappings.items():
        conn.execute("""
            UPDATE classified_ledger
            SET merchant_name = ?,
                category = ?
            WHERE raw_description = ? AND category = 'UNCLASSIFIED'
        """, [info['merchant'], info['category'], raw_desc])
        
        patched_count += 1
        
    print(f"AI Tier successfully integrated {patched_count} live merchant rules into the ledger.")
    conn.close()
