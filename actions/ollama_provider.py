"""
ollama_provider.py — Ollama local LLM client for NEXO.
Acts as a fallback / alternative when Gemini is unavailable (quota, credits, offline).

Requires Ollama running locally:  https://ollama.ai
  ollama pull llama3.2
  ollama serve

Usage:
  from actions.ollama_provider import chat, is_available, list_models
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

# ── Defaults ─────────────────────────────────────────────────────────────────
_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL    = "llama3.2"
_TIMEOUT_PING     = 3    # seconds for availability check
_TIMEOUT_CHAT     = 120  # seconds for chat completion


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_config() -> dict:
    try:
        return json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Public API ────────────────────────────────────────────────────────────────

def is_available() -> bool:
    """Return True if Ollama server responds on the configured URL."""
    cfg = _get_config()
    base = cfg.get("ollama_base_url", _DEFAULT_BASE_URL)
    try:
        req = urllib.request.Request(f"{base}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=_TIMEOUT_PING):
            return True
    except Exception:
        return False


def list_models() -> list[str]:
    """Return list of model names available on the local Ollama server."""
    cfg = _get_config()
    base = cfg.get("ollama_base_url", _DEFAULT_BASE_URL)
    try:
        req = urllib.request.Request(f"{base}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def chat(
    prompt: str,
    *,
    system: str = "",
    model: str = "",
    base_url: str = "",
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    """
    Send a prompt to Ollama and return the assistant response text.
    Raises ConnectionError if Ollama is unreachable.
    Raises RuntimeError on other errors.
    """
    cfg      = _get_config()
    base_url = base_url or cfg.get("ollama_base_url", _DEFAULT_BASE_URL)
    model    = model    or cfg.get("ollama_model",    _DEFAULT_MODEL)

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model":    model,
        "messages": messages,
        "stream":   False,
        "options":  {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_CHAT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "").strip()
    except urllib.error.URLError as e:
        raise ConnectionError(
            f"Ollama no disponible en {base_url}. "
            f"¿Está ejecutándose? (ollama serve) — {e}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Error en Ollama: {e}") from e


def chat_stream(
    prompt: str,
    *,
    system: str = "",
    model: str = "",
    base_url: str = "",
    on_token=None,
) -> str:
    """
    Streaming chat — calls on_token(text_chunk) for each token received.
    Returns the full response when done.
    """
    cfg      = _get_config()
    base_url = base_url or cfg.get("ollama_base_url", _DEFAULT_BASE_URL)
    model    = model    or cfg.get("ollama_model",    _DEFAULT_MODEL)

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model":    model,
        "messages": messages,
        "stream":   True,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    full = []
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_CHAT) as resp:
            for line in resp:
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8"))
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        full.append(token)
                        if on_token:
                            on_token(token)
                    if chunk.get("done"):
                        break
                except Exception:
                    continue
    except urllib.error.URLError as e:
        raise ConnectionError(f"Ollama no disponible: {e}") from e

    return "".join(full)


def pull_model(model: str, base_url: str = "") -> tuple[bool, str]:
    """
    Pull (download) a model on the Ollama server.
    Returns (success, message).
    """
    cfg      = _get_config()
    base_url = base_url or cfg.get("ollama_base_url", _DEFAULT_BASE_URL)

    payload = json.dumps({"name": model, "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/pull",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            status = data.get("status", "")
            return True, f"Modelo '{model}' listo: {status}"
    except Exception as e:
        return False, f"Error descargando '{model}': {e}"
