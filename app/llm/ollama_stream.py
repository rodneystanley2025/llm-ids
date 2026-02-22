# For streaming token output
import os
import json
from typing import Any, Dict, Iterator, Optional

import requests

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q5_K_M")
EXECUTOR_TIMEOUT_S = float(os.getenv("LLM_EXECUTOR_TIMEOUT_S", "60"))

def ollama_generate_stream(prompt: str, system: Optional[str] = None) -> Iterator[str]:
    """
    Yields text chunks from Ollama /api/generate with stream=true.
    """
    payload: Dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": True,
    }
    if system:
        payload["system"] = system

    with requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json=payload,
        stream=True,
        timeout=EXECUTOR_TIMEOUT_S,
    ) as r:
        r.raise_for_status()

        for raw in r.iter_lines(decode_unicode=True):
            if not raw:
                continue

            data = json.loads(raw)
            chunk = data.get("response", "")
            if chunk:
                yield chunk

            if data.get("done") is True:
                break
