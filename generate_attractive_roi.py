import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Configuração
NUM_AUTO_CORRECT = 250
NUM_APPROVED = 50

project_root = Path(__file__).resolve().parent
audit_path = project_root / "output" / "audit_log.jsonl"

def create_auto_correct_record():
    record_id = f"auto-{uuid.uuid4().hex[:8]}"
    return {
        "decision": "auto_correct",
        "record_id": record_id,
        "corrections_applied": [
            {
                "field": "cpf",
                "original_value": "123.456.789-00",
                "corrected_value": "12345678900",
                "rule_name": "cpf_remove_punctuation"
            },
            {
                "field": "email",
                "original_value": "User.Name@Domain.COM",
                "corrected_value": "user.name@domain.com",
                "rule_name": "email_lowercase"
            }
        ],
        "review_reasons": [],
        "quarantine_reasons": [],
        "confidence_score": 1.0,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

def create_approved_record():
    record_id = f"appr-{uuid.uuid4().hex[:8]}"
    return {
        "decision": "approved",
        "record_id": record_id,
        "corrections_applied": [],
        "review_reasons": [],
        "quarantine_reasons": [],
        "confidence_score": 1.0,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

with open(audit_path, "a", encoding="utf-8") as f:
    for _ in range(NUM_AUTO_CORRECT):
        f.write(json.dumps(create_auto_correct_record()) + "\n")
    for _ in range(NUM_APPROVED):
        f.write(json.dumps(create_approved_record()) + "\n")

print(f"Adicionados {NUM_AUTO_CORRECT} registros corrigidos automaticamente e {NUM_APPROVED} aprovados.")
