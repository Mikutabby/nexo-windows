"""
scheduler.py — Automatizaciones programadas para NEXO.
Guarda tareas en config/scheduled_tasks.json y las ejecuta en background.
Soporta: diario, semanal, cada N minutos/horas, hora específica.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from zoneinfo import ZoneInfo
    _BA_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
except Exception:
    from datetime import timezone, timedelta as _td
    _BA_TZ = timezone(_td(hours=-3))

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

_TASKS_FILE = _base_dir() / "config" / "scheduled_tasks.json"

# ─── Persistence ─────────────────────────────────────────────────────────────

def _load_tasks() -> list[dict]:
    try:
        return json.loads(_TASKS_FILE.read_text("utf-8"))
    except Exception:
        return []

def _save_tasks(tasks: list[dict]) -> None:
    _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TASKS_FILE.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), "utf-8")

# ─── Next-run calculator ─────────────────────────────────────────────────────

def _next_run(task: dict) -> Optional[datetime]:
    """Calculate the next datetime this task should run (aware, BA tz)."""
    freq   = task.get("frequency", "daily").lower()
    hour   = int(task.get("hour", 9))
    minute = int(task.get("minute", 0))
    now    = datetime.now(_BA_TZ)

    if freq in ("daily", "diario"):
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    elif freq in ("weekly", "semanal"):
        weekday_map = {
            "lunes":0,"monday":0, "martes":1,"tuesday":1,
            "miercoles":2,"miércoles":2,"wednesday":2,
            "jueves":3,"thursday":3, "viernes":4,"friday":4,
            "sabado":5,"sábado":5,"saturday":5, "domingo":6,"sunday":6,
        }
        target_wd = weekday_map.get(task.get("weekday","monday").lower(), 0)
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        days_ahead = (target_wd - now.weekday()) % 7
        if days_ahead == 0 and candidate <= now:
            days_ahead = 7
        return candidate + timedelta(days=days_ahead)

    elif freq in ("interval", "cada"):
        interval_min = int(task.get("interval_minutes", 60))
        last = task.get("last_run")
        if last:
            last_dt = datetime.fromisoformat(last)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=_BA_TZ)
            return last_dt + timedelta(minutes=interval_min)
        return now + timedelta(minutes=interval_min)

    elif freq in ("once", "una_vez"):
        run_at = task.get("run_at")
        if run_at:
            dt = datetime.fromisoformat(run_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_BA_TZ)
            return dt if dt > now else None
        return None

    return None

# ─── Task runner ─────────────────────────────────────────────────────────────

def _execute_task(task: dict, player=None, speak=None):
    action     = task.get("action", "")
    task_params = task.get("parameters", {})
    name       = task.get("name", task.get("id", "?"))

    print(f"[Scheduler] ▶ Ejecutando: '{name}' → {action}")
    if player:
        player.write_log(f"[sched] Ejecutando: {name}")
    if speak:
        speak(f"Ejecutando tarea programada: {name}")

    try:
        if action == "backup":
            _do_backup(task_params, player)
        elif action == "file_controller":
            from actions.file_controller import file_controller
            file_controller(parameters=task_params, player=player)
        elif action == "web_search":
            from actions.web_search import web_search
            web_search(parameters=task_params, player=player)
        elif action == "browser_control":
            from actions.browser_control import browser_control
            browser_control(parameters=task_params, player=player)
        elif action == "notify":
            _do_notify(task_params)
        elif action == "custom_script":
            _do_script(task_params, player)
        else:
            print(f"[Scheduler] ⚠️ Acción desconocida: {action}")
    except Exception as e:
        print(f"[Scheduler] ❌ Error en '{name}': {e}")
        if player:
            player.write_log(f"[sched] ❌ Error: {e}")

def _do_backup(params: dict, player):
    import shutil
    from datetime import datetime
    source = Path(params.get("source", ""))
    dest   = Path(params.get("destination", Path.home() / "Backups"))
    if not source.exists():
        print(f"[Scheduler] ⚠️ Fuente no existe: {source}")
        return
    dest.mkdir(parents=True, exist_ok=True)
    stamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = dest / f"{source.name}_backup_{stamp}"
    shutil.copytree(str(source), str(target)) if source.is_dir() else shutil.copy2(str(source), str(target))
    msg = f"✅ Backup completado: {target}"
    print(f"[Scheduler] {msg}")
    if player:
        player.write_log(f"[sched] {msg}")

def _do_notify(params: dict):
    try:
        import win10toast
        win10toast.ToastNotifier().show_toast(
            params.get("title", "NEXO"),
            params.get("message", "Recordatorio"),
            duration=8, threaded=True,
        )
    except Exception:
        pass

def _do_script(params: dict, player):
    import subprocess
    script = params.get("script", "")
    if not script:
        return
    result = subprocess.run(script, shell=True, capture_output=True, text=True, timeout=120)
    out = (result.stdout or result.stderr or "").strip()[:200]
    print(f"[Scheduler] Script output: {out}")
    if player:
        player.write_log(f"[sched] Script: {out}")

# ─── Background thread ───────────────────────────────────────────────────────

_runner_started = False
_runner_lock    = threading.Lock()
_speak_ref      = None
_player_ref     = None

def _runner_loop():
    while True:
        time.sleep(30)  # check every 30s
        try:
            tasks = _load_tasks()
            now   = datetime.now(_BA_TZ)
            changed = False
            for task in tasks:
                if not task.get("enabled", True):
                    continue
                nxt = _next_run(task)
                if nxt and now >= nxt:
                    threading.Thread(
                        target=_execute_task,
                        args=(task, _player_ref, _speak_ref),
                        daemon=True,
                    ).start()
                    task["last_run"] = now.isoformat()
                    changed = True
            if changed:
                _save_tasks(tasks)
        except Exception as e:
            print(f"[Scheduler] ⚠️ Runner error: {e}")

def start_runner(player=None, speak=None):
    global _runner_started, _speak_ref, _player_ref
    with _runner_lock:
        _speak_ref  = speak
        _player_ref = player
        if not _runner_started:
            t = threading.Thread(target=_runner_loop, daemon=True, name="SchedulerRunner")
            t.start()
            _runner_started = True
            print("[Scheduler] ✅ Runner iniciado.")

# ─── Public API ──────────────────────────────────────────────────────────────

def scheduler(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    global _speak_ref, _player_ref
    _speak_ref  = speak  or _speak_ref
    _player_ref = player or _player_ref
    start_runner(player, speak)

    params = parameters or {}
    action = params.get("action", "list").lower().strip()

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action == "list":
        tasks = _load_tasks()
        if not tasks:
            return "📋 No hay tareas programadas."
        lines = [f"📋 Tareas programadas ({len(tasks)}):"]
        for t in tasks:
            enabled = "✅" if t.get("enabled", True) else "⏸"
            freq    = t.get("frequency", "?")
            h, m    = t.get("hour", "?"), t.get("minute", "00")
            nxt     = _next_run(t)
            nxt_str = nxt.strftime("%d/%m %H:%M") if nxt else "N/A"
            lines.append(f"  {enabled} [{t['id'][:6]}] {t['name']} — {freq} {h}:{str(m).zfill(2)} | próxima: {nxt_str}")
        return "\n".join(lines)

    # ── CREATE ────────────────────────────────────────────────────────────────
    elif action in ("create", "add", "nueva", "agregar"):
        name      = params.get("name", "Tarea sin nombre")
        freq      = params.get("frequency", "daily").lower()
        hour      = int(params.get("hour", 9))
        minute    = int(params.get("minute", 0))
        weekday   = params.get("weekday", "monday")
        interval  = int(params.get("interval_minutes", 60))
        run_at    = params.get("run_at", "")
        task_action = params.get("task_action", "notify")
        task_params = params.get("task_parameters", {})

        task = {
            "id":         str(uuid.uuid4()),
            "name":       name,
            "frequency":  freq,
            "hour":       hour,
            "minute":     minute,
            "weekday":    weekday,
            "interval_minutes": interval,
            "run_at":     run_at,
            "action":     task_action,
            "parameters": task_params,
            "enabled":    True,
            "last_run":   None,
            "created_at": datetime.now(_BA_TZ).isoformat(),
        }
        tasks = _load_tasks()
        tasks.append(task)
        _save_tasks(tasks)
        nxt = _next_run(task)
        nxt_str = nxt.strftime("%d/%m/%Y a las %H:%M") if nxt else "N/A"
        msg = f"✅ Tarea '{name}' creada. Próxima ejecución: {nxt_str}."
        if player:
            player.write_log(f"[sched] {msg}")
        return msg

    # ── DELETE ────────────────────────────────────────────────────────────────
    elif action in ("delete", "eliminar", "remove"):
        task_id = params.get("task_id", "").strip()
        tasks   = _load_tasks()
        before  = len(tasks)
        tasks   = [t for t in tasks if not t["id"].startswith(task_id)]
        if len(tasks) == before:
            return f"❌ No se encontró la tarea con ID '{task_id}'."
        _save_tasks(tasks)
        return f"🗑 Tarea eliminada."

    # ── ENABLE / DISABLE ──────────────────────────────────────────────────────
    elif action in ("enable", "activar", "disable", "desactivar", "pause", "pausar"):
        task_id = params.get("task_id", "").strip()
        enabled = action in ("enable", "activar")
        tasks   = _load_tasks()
        found   = False
        for t in tasks:
            if t["id"].startswith(task_id):
                t["enabled"] = enabled
                found = True
        if not found:
            return f"❌ Tarea '{task_id}' no encontrada."
        _save_tasks(tasks)
        return f"{'✅ Tarea activada.' if enabled else '⏸ Tarea pausada.'}"

    # ── RUN NOW ───────────────────────────────────────────────────────────────
    elif action in ("run_now", "ejecutar"):
        task_id = params.get("task_id", "").strip()
        tasks   = _load_tasks()
        for t in tasks:
            if t["id"].startswith(task_id):
                threading.Thread(
                    target=_execute_task,
                    args=(t, player, speak),
                    daemon=True,
                ).start()
                return f"▶ Ejecutando '{t['name']}' ahora mismo."
        return f"❌ Tarea '{task_id}' no encontrada."

    else:
        return (
            "Acciones disponibles: list, create, delete, enable, disable, run_now. "
            "Para crear un backup diario: action=create, task_action=backup, "
            "task_parameters={'source':'C:/mi/proyecto', 'destination':'D:/backups'}, "
            "hour=9, frequency=daily, name='Backup diario'."
        )
