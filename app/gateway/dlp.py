import re
from typing import Dict, List, Tuple

# Simple patterns (good enough for demo; expand later)
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)

def find_pii(text: str) -> List[Dict[str, str]]:
    t = text or ""
    hits: List[Dict[str, str]] = []
    if SSN_RE.search(t):
        hits.append({"type": "SSN"})
    if EMAIL_RE.search(t):
        hits.append({"type": "EMAIL"})
    if CREDIT_CARD_RE.search(t):
        hits.append({"type": "CREDIT_CARD_LIKE"})
    return hits

def redact_pii(text: str) -> Tuple[str, List[Dict[str, str]]]:
    t = text or ""
    hits = find_pii(t)

    t = SSN_RE.sub("[REDACTED_SSN]", t)
    t = EMAIL_RE.sub("[REDACTED_EMAIL]", t)
    # credit card “like” can false-positive; still fine for demo
    t = CREDIT_CARD_RE.sub("[REDACTED_NUMBER]", t)

    return t, hits
