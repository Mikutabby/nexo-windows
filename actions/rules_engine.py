"""
rules_engine.py — Motor de reglas y alertas inteligentes para NEXO.
Reglas tipo 'si pasa esto → hacé esto'.
Persiste en config/rules.json.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

_RULES_FILE = Path(__file__).resolve().parent.parent / "config" / "rules.json"
_lock = threading.Lock()
_runner_started = False
_player_ref = None
_speak_ref = None


# ── persistence ──────────────────────────────────────────────────────────────

def _load() -> list[dict]:
    try:
        return json.loads(_RULES_FILE.read_text("utf-8"))
    except Exception:
        return []


def _save(rules: list[dict]):
    _RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _RULES_FILE.write_text(json.dumps(rules, indent=2, ensure_ascii=False), "utf-8")


def _log(msg: str):
    print(f"[Rules] {msg}")
    if _player_ref:
        _player_ref.write_log(f"[rules] {msg}")


# ── condition evaluation ──────────────────────────────────────────────────────

def _evaluate_condition(cond: dict) -> bool:
    """Evalúa una condición. Tipos: time, file_exists, always, phrase (on-demand)."""
    typ = cond.get("type", "")

    if typ == "time":
        # {"type":"time","hour":8,"minute":0,"days":["monday","friday"]}
        now = datetime.now()
        h = cond.get("hour", -1)
        m = cond.get("minute", 0)
        days = cond.get("days", [])
        day_names = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
        today = day_names[now.weekday()]
        time_match = (now.hour == h and now.minute == m)
        day_match = (not days) or (today in [d.lower() for d in days])
        return time_match and day_match

    if typ == "file_exists":
        return Path(cond.get("path", "")).exists()

    if typ == "always":
        return True

    if typ == "phrase":
        return False   # phrase triggers evaluated on-demand via check_phrase_triggers()

    return False


def _run_action(action: dict):
    """Ejecuta la acción de una regla disparada."""
    typ = action.get("type", "notify")

    if typ == "notify":
        msg = action.get("message", "Regla disparada")
        _log(f"🔔 Alerta: {msg}")
        if _speak_ref:
            _speak_ref(msg)
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast("NEXO", msg, duration=6, threaded=True)
        except Exception:
            pass

    elif typ == "open_url":
        import webbrowser
        webbrowser.open(action.get("url", ""))

    elif typ == "run_script":
        import subprocess
        subprocess.Popen(action.get("command", ""), shell=True)

    elif typ == "speak":
        if _speak_ref:
            _speak_ref(action.get("message", ""))

    elif typ == "open_app":
        try:
            from actions.open_app import open_app
            open_app(parameters={"app_name": action.get("app_name", "")}, response=None, player=None)
            _log(f"📂 App abierta: {action.get('app_name','?')}")
        except Exception as e:
            _log(f"Error open_app: {e}")

    elif typ == "spotify_play":
        try:
            from actions.spotify_control import spotify_control
            spotify_control(
                parameters={"action": "play", "query": action.get("query", "")},
                player=None
            )
            _log(f"🎵 Spotify: {action.get('query','?')}")
        except Exception as e:
            _log(f"Error spotify_play: {e}")

    elif typ == "browser":
        try:
            from actions._chrome_launch import open_in_chrome
            open_in_chrome(action.get("url", "https://google.com"))
            _log(f"🌐 Browser: {action.get('url','?')}")
        except Exception as e:
            _log(f"Error browser: {e}")

    elif typ == "smart_home":
        try:
            from actions.smart_home import smart_home
            smart_home(
                parameters={"device": action.get("device",""), "action": action.get("action","on")},
                player=None
            )
            _log(f"🏠 Smart home: {action.get('device','?')} → {action.get('action','?')}")
        except Exception as e:
            _log(f"Error smart_home: {e}")

    elif typ == "composite":
        for sub in action.get("actions", []):
            try:
                _run_action(sub)
            except Exception as e:
                _log(f"Error en sub-acción {sub.get('type','?')}: {e}")


# ── background runner ─────────────────────────────────────────────────────────

def _runner_loop():
    """Verifica reglas periódicamente (cada 55s para coincidir con minutos exactos)."""
    last_checked: dict[str, str] = {}
    while True:
        time.sleep(55)
        rules = _load()
        now_key = datetime.now().strftime("%Y-%m-%d %H:%M")
        for rule in rules:
            if not rule.get("enabled", True):
                continue
            rid = rule.get("id", "")
            # avoid firing twice in same minute
            if last_checked.get(rid) == now_key:
                continue
            try:
                if _evaluate_condition(rule.get("condition", {})):
                    last_checked[rid] = now_key
                    _log(f"Regla '{rule.get('name','?')}' disparada")
                    _run_action(rule.get("action", {}))
            except Exception as e:
                _log(f"Error en regla '{rule.get('name','?')}': {e}")


def _normalize_phrase(text: str) -> str:
    """Lowercase + strip punctuation for flexible matching."""
    import re
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def check_phrase_triggers(user_text: str) -> list[dict]:
    """
    Evalúa si el texto del usuario dispara alguna regla de tipo 'phrase'.
    Retorna lista de reglas coincidentes (puede ser vacía).
    match types: contains (default), exact, startswith
    Comparación es insensible a mayúsculas y signos de puntuación.
    """
    text_lower = user_text.lower().strip()
    text_norm  = _normalize_phrase(user_text)
    triggered  = []
    for rule in _load():
        if not rule.get("enabled", True):
            continue
        cond = rule.get("condition", {})
        if cond.get("type") != "phrase":
            continue
        trigger_raw = cond.get("trigger", "").strip()
        if not trigger_raw:
            continue
        trigger_lower = trigger_raw.lower().strip()
        trigger_norm  = _normalize_phrase(trigger_raw)
        match_type    = cond.get("match", "contains")

        matched = False
        if match_type == "exact":
            # Accept if exact (with or without punctuation)
            matched = (text_lower == trigger_lower) or (text_norm == trigger_norm)
        elif match_type == "contains":
            matched = (trigger_lower in text_lower) or (trigger_norm in text_norm)
        elif match_type == "startswith":
            matched = text_lower.startswith(trigger_lower) or text_norm.startswith(trigger_norm)

        if matched:
            triggered.append(rule)
    return triggered


def start_rules_runner(player=None, speak=None):
    global _runner_started, _player_ref, _speak_ref
    _player_ref = player
    _speak_ref = speak
    if not _runner_started:
        _runner_started = True
        t = threading.Thread(target=_runner_loop, daemon=True)
        t.start()
        _log("Motor de reglas iniciado.")


# ── main action handler ───────────────────────────────────────────────────────

def rules_engine(parameters: dict, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "list").lower().strip()

    if action == "list":
        rules = _load()
        if not rules:
            return "No hay reglas configuradas."
        lines = []
        for r in rules:
            st = "✅" if r.get("enabled", True) else "⏸"
            cond = r.get("condition", {})
            act  = r.get("action", {})
            lines.append(f"{st} [{r['id']}] {r.get('name','?')} — condición: {cond.get('type')} → acción: {act.get('type')}")
        return "📋 Reglas:\n" + "\n".join(lines)

    elif action == "create":
        name      = params.get("name", "Regla nueva")
        condition = params.get("condition", {"type": "always"})
        act_def   = params.get("action_def", {"type": "notify", "message": "Regla disparada"})
        with _lock:
            rules = _load()
            rid = f"r{int(time.time())}"
            rules.append({
                "id": rid,
                "name": name,
                "enabled": True,
                "condition": condition,
                "action": act_def,
            })
            _save(rules)
        return f"✅ Regla '{name}' creada (ID: {rid})."

    elif action == "delete":
        rid = str(params.get("rule_id", ""))
        with _lock:
            rules = _load()
            orig = len(rules)
            rules = [r for r in rules if r.get("id") != rid]
            if len(rules) == orig:
                return f"❌ No encontré la regla '{rid}'."
            _save(rules)
        return f"🗑 Regla '{rid}' eliminada."

    elif action in ("enable", "disable"):
        rid = str(params.get("rule_id", ""))
        enabled = (action == "enable")
        with _lock:
            rules = _load()
            for r in rules:
                if r.get("id") == rid:
                    r["enabled"] = enabled
                    _save(rules)
                    return f"{'✅' if enabled else '⏸'} Regla '{rid}' {'habilitada' if enabled else 'deshabilitada'}."
        return f"❌ No encontré la regla '{rid}'."

    elif action == "trigger":
        # manual trigger by id
        rid = str(params.get("rule_id", ""))
        rules = _load()
        for r in rules:
            if r.get("id") == rid:
                _run_action(r.get("action", {}))
                return f"⚡ Regla '{r.get('name','?')}' ejecutada manualmente."
        return f"❌ No encontré la regla '{rid}'."

    elif action == "alert":
        # Smart alert: just send a notification now
        msg = params.get("message", "Alerta de NEXO")
        _run_action({"type": "notify", "message": msg})
        return f"🔔 Alerta enviada: {msg}"

    elif action == "list_phrases":
        rules = _load()
        phrases = [r for r in rules if r.get("condition", {}).get("type") == "phrase"]
        if not phrases:
            return "No hay automatizaciones por frase configuradas."
        lines = []
        for r in phrases:
            st   = "✅" if r.get("enabled", True) else "⏸"
            cond = r.get("condition", {})
            act  = r.get("action", {})
            trigger  = cond.get("trigger", "?")
            act_type = act.get("type", "?")
            lines.append(f"{st} [{r['id']}] Frase: '{trigger}' → {act_type}")
        return "⚡ Automatizaciones por frase:\n" + "\n".join(lines)

    else:
        return f"Acción desconocida: '{action}'. Opciones: list, list_phrases, create, delete, enable, disable, trigger, alert."
