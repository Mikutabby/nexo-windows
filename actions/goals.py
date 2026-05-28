"""
goals.py — Sistema de objetivos persistentes para NEXO.
Metas a largo plazo con seguimiento y progreso.
Persiste en config/goals.json.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

_GOALS_FILE = Path(__file__).resolve().parent.parent / "config" / "goals.json"
_lock = threading.Lock()


def _load() -> list[dict]:
    try:
        return json.loads(_GOALS_FILE.read_text("utf-8"))
    except Exception:
        return []


def _save(goals: list[dict]):
    _GOALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _GOALS_FILE.write_text(json.dumps(goals, indent=2, ensure_ascii=False), "utf-8")


def _status_icon(g: dict) -> str:
    if g.get("completed"):
        return "✅"
    deadline = g.get("deadline")
    if deadline:
        try:
            dl = datetime.fromisoformat(deadline)
            if dl < datetime.now():
                return "⚠️"
        except Exception:
            pass
    return "🎯"


def goals(parameters: dict, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "list").lower().strip()

    if action == "list":
        gs = _load()
        if not gs:
            return "No hay objetivos configurados. Usá 'create' para agregar uno."
        lines = ["🎯 Objetivos:"]
        for g in gs:
            icon = _status_icon(g)
            progress = f" [{g.get('progress', 0)}%]" if "progress" in g else ""
            deadline = f" (hasta {g['deadline'][:10]})" if g.get("deadline") else ""
            lines.append(f"  {icon} [{g['id']}] {g['title']}{progress}{deadline}")
            if g.get("description"):
                lines.append(f"       {g['description']}")
            if g.get("steps"):
                done = sum(1 for s in g["steps"] if s.get("done"))
                lines.append(f"       Pasos: {done}/{len(g['steps'])} completados")
        return "\n".join(lines)

    elif action == "create":
        title = params.get("title", "").strip()
        if not title:
            return "❌ Especificá un título para el objetivo."
        with _lock:
            gs = _load()
            gid = f"g{int(time.time())}"
            steps_raw = params.get("steps", [])
            steps = [{"text": s, "done": False} for s in steps_raw] if steps_raw else []
            gs.append({
                "id": gid,
                "title": title,
                "description": params.get("description", ""),
                "deadline": params.get("deadline", ""),
                "progress": 0,
                "completed": False,
                "steps": steps,
                "created": datetime.now().isoformat(),
                "updated": datetime.now().isoformat(),
            })
            _save(gs)
        return f"✅ Objetivo '{title}' creado (ID: {gid})."

    elif action == "update_progress":
        gid = str(params.get("goal_id", ""))
        progress = int(params.get("progress", 0))
        with _lock:
            gs = _load()
            for g in gs:
                if g["id"] == gid:
                    g["progress"] = max(0, min(100, progress))
                    g["updated"] = datetime.now().isoformat()
                    if progress >= 100:
                        g["completed"] = True
                    _save(gs)
                    return f"📊 Progreso de '{g['title']}' actualizado a {progress}%."
        return f"❌ No encontré el objetivo '{gid}'."

    elif action == "complete":
        gid = str(params.get("goal_id", ""))
        with _lock:
            gs = _load()
            for g in gs:
                if g["id"] == gid:
                    g["completed"] = True
                    g["progress"] = 100
                    g["completed_at"] = datetime.now().isoformat()
                    g["updated"] = datetime.now().isoformat()
                    _save(gs)
                    return f"🎉 ¡Objetivo '{g['title']}' completado!"
        return f"❌ No encontré el objetivo '{gid}'."

    elif action == "complete_step":
        gid  = str(params.get("goal_id", ""))
        sidx = int(params.get("step_index", 0))
        with _lock:
            gs = _load()
            for g in gs:
                if g["id"] == gid:
                    steps = g.get("steps", [])
                    if 0 <= sidx < len(steps):
                        steps[sidx]["done"] = True
                        done = sum(1 for s in steps if s.get("done"))
                        g["progress"] = int(done / len(steps) * 100)
                        if g["progress"] >= 100:
                            g["completed"] = True
                        g["updated"] = datetime.now().isoformat()
                        _save(gs)
                        return f"✅ Paso {sidx+1} del objetivo '{g['title']}' completado ({g['progress']}%)."
                    return f"❌ Índice de paso inválido (0-{len(steps)-1})."
        return f"❌ No encontré el objetivo '{gid}'."

    elif action == "add_step":
        gid  = str(params.get("goal_id", ""))
        step = params.get("step", "").strip()
        if not step:
            return "❌ Especificá el texto del paso."
        with _lock:
            gs = _load()
            for g in gs:
                if g["id"] == gid:
                    g.setdefault("steps", []).append({"text": step, "done": False})
                    g["updated"] = datetime.now().isoformat()
                    _save(gs)
                    return f"➕ Paso agregado al objetivo '{g['title']}'."
        return f"❌ No encontré el objetivo '{gid}'."

    elif action == "delete":
        gid = str(params.get("goal_id", ""))
        with _lock:
            gs = _load()
            orig = len(gs)
            gs = [g for g in gs if g["id"] != gid]
            if len(gs) == orig:
                return f"❌ No encontré el objetivo '{gid}'."
            _save(gs)
        return f"🗑 Objetivo '{gid}' eliminado."

    elif action == "detail":
        gid = str(params.get("goal_id", ""))
        gs = _load()
        for g in gs:
            if g["id"] == gid:
                icon = _status_icon(g)
                lines = [
                    f"{icon} {g['title']} ({g['progress']}%)",
                    f"   Descripción: {g.get('description') or '—'}",
                    f"   Creado: {g['created'][:10]}",
                    f"   Actualizado: {g['updated'][:10]}",
                ]
                if g.get("deadline"):
                    lines.append(f"   Deadline: {g['deadline'][:10]}")
                steps = g.get("steps", [])
                if steps:
                    lines.append("   Pasos:")
                    for i, s in enumerate(steps):
                        mark = "✅" if s.get("done") else "⬜"
                        lines.append(f"     {mark} [{i}] {s['text']}")
                return "\n".join(lines)
        return f"❌ No encontré el objetivo '{gid}'."

    else:
        return (f"Acción desconocida: '{action}'. "
                "Opciones: list, create, update_progress, complete, complete_step, add_step, delete, detail.")
