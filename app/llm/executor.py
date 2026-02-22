# For normal LLM calls (non‑streaming)
import os
from typing import Any, Dict, Optional

import requests


PRIMARY_PROVIDER = os.getenv("PRIMARY_LLM_PROVIDER", "ollama")  # only ollama for now
SAFE_PROVIDER = os.getenv("SAFE_LLM_PROVIDER", "ollama")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q5_K_M")

EXECUTOR_TIMEOUT_S = float(os.getenv("LLM_EXECUTOR_TIMEOUT_S", "60"))


def _pick_provider(decision: str) -> str:
    # allow -> primary, review/block -> safe
    return PRIMARY_PROVIDER if decision == "allow" else SAFE_PROVIDER


def _ollama_generate(prompt: str, system: Optional[str] = None) -> str:
    """
    Try /api/generate first.
    If the server responds 404 for /api/generate, fallback to /api/chat.
    """
    # 1) /api/generate (prompt-based)
    payload_generate: Dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload_generate["system"] = system

    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload_generate,
            timeout=EXECUTOR_TIMEOUT_S,
        )
        if r.status_code == 404:
            raise requests.HTTPError("generate_not_found", response=r)
        r.raise_for_status()
        data = r.json()
        return data.get("response", "") or ""
    except requests.HTTPError as ex:
        # Only fallback on "endpoint not found"
        resp = getattr(ex, "response", None)
        if resp is None or resp.status_code != 404:
            raise

    # 2) /api/chat (messages-based)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload_chat: Dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }

    r2 = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload_chat,
        timeout=EXECUTOR_TIMEOUT_S,
    )
    r2.raise_for_status()
    data2 = r2.json()

    # Ollama chat shape is typically: {"message": {"content": "..."}}
    msg = data2.get("message") or {}
    return (msg.get("content") or "").strip()


def call_downstream_llm(
    decision: str,
    prompt: str,
    system: Optional[str] = None,
) -> Dict[str, Any]:
    provider = _pick_provider(decision)

    if provider != "ollama":
        raise RuntimeError(f"Unsupported provider right now: {provider}")

    text = _ollama_generate(prompt=prompt, system=system)

    return {
        "provider": provider,
        "model": OLLAMA_MODEL,
        "text": text,
    }
