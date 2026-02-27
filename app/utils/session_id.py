import re

MAX_SESSION_ID = 64


def normalize_session_id(session_id: str) -> str:
    """
    Normalize user supplied session id.

    - trims whitespace
    - lowercase
    - spaces -> underscore
    - removes illegal characters
    - length limited
    """

    if not session_id:
        return "default"

    sid = session_id.strip().lower()

    # spaces -> underscore
    sid = re.sub(r"\s+", "_", sid)

    # allow only safe chars
    sid = re.sub(r"[^a-z0-9_\-]", "", sid)

    # enforce max length
    sid = sid[:MAX_SESSION_ID]

    if not sid:
        sid = "default"

    return sid
