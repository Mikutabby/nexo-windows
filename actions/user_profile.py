"""
user_profile.py — Perfil dinámico del usuario para NEXO.
Aprende hábitos, preferencias y patrones de uso automáticamente.
Persiste en config/user_profile.json.
"""
from __future__ import annotations

import json
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path

_PROFILE_FILE = Path(__file__).resolve().parent.parent / "config" / "user_profile.json"
_lock = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(_PROFILE_FILE.read_text("utf-8"))
    except Exception:
        return {
            "name": "Usuario",
            "language": "es",
            "preferences": {},
            "habits": {},
            "frequent_actions": {},
            "frequent_places": {},
            "frequent_contacts": {},
            "schedule_hints": {},
            "notes": [],
            "created": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
        }


def _save(profile: dict):
    _PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    profile["last_updated"] = datetime.now().isoformat()
    _PROFILE_FILE.write_text(json.dumps(profile, indent=2, ensure_ascii=False), "utf-8")


# ── auto-learning API (called from main.py on each tool execution) ────────────

def record_action(action_name: str, params: dict | None = None):
    """Registra el uso de una acción para aprender patrones."""
    with _lock:
        p = _load()
        hour = datetime.now().hour
        dow  = datetime.now().strftime("%A").lower()

        # frequent actions counter
        fa = p.setdefault("frequent_actions", {})
        fa[action_name] = fa.get(action_name, 0) + 1

        # schedule hints: which hour/day the user tends to use which actions
        sh = p.setdefault("schedule_hints", {})
        key = f"{dow}_{hour:02d}h"
        sh.setdefault(key, {})
        sh[key][action_name] = sh[key].get(action_name, 0) + 1

        # learn frequent places from maps
        if action_name == "google_maps" and params:
            places = p.setdefault("frequent_places", {})
            for field in ("origin", "destination", "query"):
                val = (params.get(field) or "").strip()
                if val:
                    places[val] = places.get(val, 0) + 1

        # learn frequent contacts from messages
        if action_name == "send_message" and params:
            contacts = p.setdefault("frequent_contacts", {})
            to = (params.get("receiver") or params.get("to") or "").strip()
            if to:
                contacts[to] = contacts.get(to, 0) + 1

        _save(p)


# ── main action handler ───────────────────────────────────────────────────────

def user_profile(parameters: dict, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "view").lower().strip()

    if action == "view":
        p = _load()
        fa = sorted(p.get("frequent_actions", {}).items(), key=lambda x: -x[1])[:5]
        fp = sorted(p.get("frequent_places", {}).items(), key=lambda x: -x[1])[:5]
        fc = sorted(p.get("frequent_contacts", {}).items(), key=lambda x: -x[1])[:5]
        prefs = p.get("preferences", {})

        lines = [
            f"👤 Perfil: {p.get('name','?')}",
            f"   Idioma: {p.get('language','es')}",
            f"   Actualizado: {p.get('last_updated','?')[:10]}",
            "",
            "🔁 Acciones más frecuentes:",
        ]
        for k, v in fa:
            lines.append(f"   • {k}: {v}x")
        if fp:
            lines.append("\n📍 Lugares frecuentes:")
            for k, v in fp:
                lines.append(f"   • {k}: {v}x")
        if fc:
            lines.append("\n💬 Contactos frecuentes:")
            for k, v in fc:
                lines.append(f"   • {k}: {v}x")
        if prefs:
            lines.append("\n⚙️ Preferencias:")
            for k, v in prefs.items():
                lines.append(f"   • {k}: {v}")
        return "\n".join(lines)

    elif action == "set_preference":
        key = params.get("key", "")
        val = params.get("value", "")
        if not key:
            return "❌ Especificá key y value."
        with _lock:
            p = _load()
            p.setdefault("preferences", {})[key] = val
            _save(p)
        return f"✅ Preferencia '{key}' = '{val}' guardada."

    elif action == "set_name":
        name = params.get("name", "").strip()
        if not name:
            return "❌ Especificá un nombre."
        with _lock:
            p = _load()
            p["name"] = name
            _save(p)
        return f"✅ Nombre actualizado a '{name}'."

    elif action == "add_note":
        note = params.get("note", "").strip()
        if not note:
            return "❌ Especificá la nota."
        with _lock:
            p = _load()
            p.setdefault("notes", []).append({
                "text": note,
                "date": datetime.now().isoformat()
            })
            _save(p)
        return f"📝 Nota guardada."

    elif action == "notes":
        p = _load()
        notes = p.get("notes", [])
        if not notes:
            return "No hay notas guardadas."
        return "📝 Notas:\n" + "\n".join(
            f"  [{n['date'][:10]}] {n['text']}" for n in notes[-10:]
        )

    elif action == "reset":
        _PROFILE_FILE.unlink(missing_ok=True)
        return "♻️ Perfil de usuario reseteado."

    elif action == "habits":
        p = _load()
        sh = p.get("schedule_hints", {})
        if not sh:
            return "Aún no hay suficientes datos de hábitos."
        now_dow = datetime.now().strftime("%A").lower()
        now_h   = datetime.now().hour
        # show today's typical activity
        key = f"{now_dow}_{now_h:02d}h"
        today_acts = sh.get(key, {})
        lines = [f"🕐 Hábitos para {now_dow} a las {now_h:02d}h:"]
        if today_acts:
            for k, v in sorted(today_acts.items(), key=lambda x: -x[1]):
                lines.append(f"   • {k}: {v}x")
        else:
            lines.append("   Sin datos para esta hora.")
        return "\n".join(lines)

    else:
        return f"Acción desconocida: '{action}'. Opciones: view, set_preference, set_name, add_note, notes, habits, reset."
