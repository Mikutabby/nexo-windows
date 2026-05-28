"""
model_router.py — NEXO AI model routing.

Decides whether to use Gemini or Ollama for each type of task.
The user configures this from the Settings → Modelos IA section.

Task types:
  conversation  — live voice/text conversation (Gemini Native Audio preferred)
  agent         — multi-step agent tasks (dev_agent, code_helper, agent_task)
  search        — quick text queries (web_search, knowledge_base, etc.)
  vision        — screen_vision, image analysis

When Gemini returns a quota / auth error, the router automatically falls back
to Ollama for text tasks (note: voice stays on Gemini — Ollama is text-only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# ── Config keys ───────────────────────────────────────────────────────────────
_TASK_CFG_KEYS: dict[str, str] = {
    "conversation": "model_for_conversation",
    "agent":        "model_for_agents",
    "search":       "model_for_search",
    "vision":       "model_for_vision",
}

_DEFAULTS: dict[str, str] = {
    "model_for_conversation": "gemini",
    "model_for_agents":       "gemini",
    "model_for_search":       "gemini",
    "model_for_vision":       "gemini",
}

# Gemini error strings that indicate quota / billing exhaustion
_QUOTA_ERRORS = (
    "quota",
    "rate limit",
    "resource_exhausted",
    "billing",
    "429",
    "too many requests",
    "you exceeded",
    "free tier",
)

# ── Fallback state ────────────────────────────────────────────────────────────
_gemini_failed = False   # set True on quota error; resets on restart


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _cfg() -> dict:
    try:
        return json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
    except Exception:
        return {}


# ── Public API ────────────────────────────────────────────────────────────────

def get_model_for(task: str) -> str:
    """
    Return 'gemini' or 'ollama' for the given task type.
    If Gemini has hit a quota error and Ollama is available, automatically
    returns 'ollama' regardless of user setting.
    """
    global _gemini_failed
    cfg = _cfg()

    if not cfg.get("ollama_enabled", False):
        return "gemini"

    # If Gemini quota/auth failed during this session, auto-route to Ollama
    if _gemini_failed and _ollama_reachable(cfg):
        return "ollama"

    key     = _TASK_CFG_KEYS.get(task, "model_for_conversation")
    chosen  = cfg.get(key, _DEFAULTS.get(key, "gemini"))
    return chosen


def gemini_ok() -> bool:
    """True if Gemini API key is configured and no quota error has been seen."""
    global _gemini_failed
    return bool(_cfg().get("gemini_api_key", "")) and not _gemini_failed


def ollama_ok() -> bool:
    """True if Ollama is enabled in config and server is reachable."""
    cfg = _cfg()
    if not cfg.get("ollama_enabled", False):
        return False
    return _ollama_reachable(cfg)


def _ollama_reachable(cfg: dict | None = None) -> bool:
    if cfg is None:
        cfg = _cfg()
    try:
        from actions.ollama_provider import is_available
        return is_available()
    except Exception:
        return False


def report_gemini_error(error_text: str) -> bool:
    """
    Call this when a Gemini API call fails.
    Returns True if the error looks like a quota/billing issue (trigger fallback).
    """
    global _gemini_failed
    et = str(error_text).lower()
    if any(kw in et for kw in _QUOTA_ERRORS):
        _gemini_failed = True
        print(f"[ModelRouter] Gemini quota/billing error — switching to Ollama fallback")
        return True
    return False


def reset_gemini_fallback():
    """Call this to clear the fallback flag (e.g. when API key is updated)."""
    global _gemini_failed
    _gemini_failed = False


def quick_chat(
    prompt: str,
    *,
    system: str = "",
    task: str = "agent",
) -> str:
    """
    Fire a one-shot text completion using whichever model is configured
    for the given task. Does NOT touch the live Gemini Audio session.

    Raises on total failure (both providers unavailable).
    """
    model = get_model_for(task)

    if model == "ollama" or (_gemini_failed and _ollama_reachable()):
        from actions.ollama_provider import chat as _ollama_chat
        return _ollama_chat(prompt, system=system)

    # Gemini text fallback (non-live, single-turn)
    cfg     = _cfg()
    api_key = cfg.get("gemini_api_key", "")
    if not api_key:
        raise RuntimeError("No hay API Key de Gemini configurada.")

    try:
        from google import genai as _genai
        client = _genai.Client(api_key=api_key)
        parts  = []
        if system:
            parts.append(system + "\n\n")
        parts.append(prompt)
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[{"role": "user", "parts": [{"text": "".join(parts)}]}],
        )
        return resp.text or ""
    except Exception as e:
        if report_gemini_error(str(e)):
            # Retry with Ollama
            if _ollama_reachable():
                from actions.ollama_provider import chat as _ollama_chat
                return _ollama_chat(prompt, system=system)
        raise


def status() -> dict:
    """Return current routing status for display in UI."""
    cfg = _cfg()
    return {
        "ollama_enabled":   cfg.get("ollama_enabled", False),
        "ollama_base_url":  cfg.get("ollama_base_url", "http://localhost:11434"),
        "ollama_model":     cfg.get("ollama_model", "llama3.2"),
        "ollama_reachable": _ollama_reachable(cfg),
        "gemini_failed":    _gemini_failed,
        "model_for_conversation": cfg.get("model_for_conversation", "gemini"),
        "model_for_agents":       cfg.get("model_for_agents",       "gemini"),
        "model_for_search":       cfg.get("model_for_search",       "gemini"),
        "model_for_vision":       cfg.get("model_for_vision",       "gemini"),
    }
