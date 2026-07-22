import logging
from pathlib import Path
import os
import json
from datetime import datetime

# ROOT_PATH = Path(__file__).resolve().parent.parent
# LOG_FILE = ROOT_PATH / "logs" / "ai_classification_audit.log"

# Ensure a dedicated logs directory exists in your workspace
os.makedirs("logs", exist_ok=True)

# Configure a isolated logger specifically for cloud payloads
ai_audit_logger = logging.getLogger("DigitzAIAudit")
ai_audit_logger.setLevel(logging.INFO)

# Prevent log messages from leaking up to the main console print statements
ai_audit_logger.propagate = False

# Establish a file handler for the audit trail
log_file_path = os.path.join("logs", "ai_classification_audit.log")
file_handler = logging.FileHandler(log_file_path, encoding="utf-8")

# Define a clean structural format for the log entries
formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s')
file_handler.setFormatter(formatter)
ai_audit_logger.addHandler(file_handler)

def log_cloud_payload(batch_id: str, raw_payload: list):
    """
    Formally records the exact transaction array being transmitted out
    to the cloud LLM provider for auditing and data privacy reviews.
    """
    log_entry = {
        "batch_id": batch_id,
        "record_count": len(raw_payload),
        "transmitted_data": raw_payload
    }
    # Write as a single line of structured JSON for easy grepping later
    ai_audit_logger.info(f"OUTBOUND_PAYLOAD: {json.dumps(log_entry)}")
