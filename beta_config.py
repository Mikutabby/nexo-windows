"""beta_config.py — NEXO Beta restrictions."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "config" / "beta_state.json"

PRO_TOOLS: set[str] = {
    "whatsapp", "gmail_control", "google_calendar", "google_drive",
    "social_media", "tiktok_analyzer", "image_generation", "flight_finder",
    "arca_invoice", "document_creator", "rgb_control", "game_updater",
    "dev_agent", "codebase", "git_control", "code_helper",
    "file_processor", "agent_task",
}

DAILY_LIMIT = 100

def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

def is_pro_tool(tool_name: str) -> bool:
    return tool_name in PRO_TOOLS

def check_daily_limit() -> tuple[bool, int]:
    state = _load_state()
    today = str(date.today())
    if state.get("date") != today:
        state = {"date": today, "calls": 0}
        _save_state(state)
    calls = state.get("calls", 0)
    return calls < DAILY_LIMIT, calls

def increment_calls() -> int:
    state = _load_state()
    today = str(date.today())
    if state.get("date") != today:
        state = {"date": today, "calls": 0}
    state["calls"] = state.get("calls", 0) + 1
    _save_state(state)
    return state["calls"]

def pro_tool_message(tool_name: str) -> str:
    return (
        f"La función \'{tool_name}\' es exclusiva de NEXO PRO. "
        "Actualizá tu plan para desbloquear esta y todas las funciones avanzadas."
    )

def daily_limit_message(calls: int) -> str:
    return (
        f"Llegás al límite diario de {DAILY_LIMIT} interacciones de NEXO Beta. "
        "El contador se reinicia mañana. Con NEXO PRO tenés uso ilimitado."
    )
