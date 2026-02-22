import os
from typing import Any, Dict
import yaml

POLICY_PATH = os.getenv("IDS_POLICY_PATH", "app/policy.yaml")

def load_policy() -> Dict[str, Any]:
    with open(POLICY_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
