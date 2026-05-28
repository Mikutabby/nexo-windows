"""
vision_guardian.py — Guardian de visión ambiental de NEXO.
Monitorea la pantalla en background con Gemini Vision y ofrece ayuda proactiva
cuando detecta algo urgente o relevante para el usuario.
"""
from __future__ import annotations

import base64
import io
import json
import threading
import time
from pathlib import Path
from typing import Callable

_BASE_DIR   = Path(__file__).resolve().parent.parent
_API_FILE   = _BASE_DIR / "config" / "api_keys.json"
_STATE_FILE = _BASE_DIR / "config" / "vision_guardian_state.json"

_DEFAULT_INTERVAL = 90        # seconds between checks
_GEMINI_MODEL     = "gemini-2.5-flash"
_VISION_PROMPT    = (
    "Analizá esta captura de pantalla del escritorio de un usuario. "
    "Tu tarea es detectar situaciones urgentes o donde el asistente de voz podría ayudar proactivamente. "
    "Situaciones que merecen comentario: errores críticos visibles, documentos abiertos con posibles problemas, "
    "tareas que llevan mucho tiempo, emails importantes, alertas del sistema, código con errores evidentes. "
    "Si NO hay nada urgente ni destacable, respondé SOLO la palabra: OK\n"
    "Si hay algo relevante, respondé con UNA oración corta en español (máximo 15 palabras) "
    "describiendo qué ves y qué podrías ayudar. No uses emojis en la respuesta."
)

_lock          = threading.Lock()
_guardian_thread: threading.Thread | None = None
_stop_event    = threading.Event()
_inject_callback: Callable[[str], None] | None = None
_is_active     = False
_last_insight  = ""  # Avoid repeating the same insight


def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text("utf-8"))
    except Exception:
        # Desactivado por defecto — el usuario debe activarlo desde Configuración
        return {"enabled": False, "interval": _DEFAULT_INTERVAL}


def _save_state(state: dict):
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), "utf-8")
    except Exception:
        pass


def is_enabled() -> bool:
    return _load_state().get("enabled", False)


def _capture_screen() -> bytes | None:
    """Captura la pantalla y retorna JPEG bytes."""
    try:
        import mss
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # primary monitor
            img = sct.grab(monitor)
            # Convert to PIL and resize
            from PIL import Image
            pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            # Scale down to reduce API cost
            pil.thumbnail((1280, 720), Image.LANCZOS)
            buf = io.BytesIO()
            pil.save(buf, format="JPEG", quality=75)
            return buf.getvalue()
    except Exception as e:
        print(f"[VisionGuardian] Capture error: {e}")
        return None


def _analyze_screenshot(img_bytes: bytes) -> str:
    """Sends screenshot to Gemini Vision and returns insight or 'OK'."""
    try:
        from google import genai
        from google.genai import types

        api_key = json.loads(_API_FILE.read_text("utf-8")).get("gemini_api_key", "")
        if not api_key:
            return "OK"

        client = genai.Client(api_key=api_key)
        img_b64 = base64.b64encode(img_bytes).decode()

        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=[
                types.Part(
                    inline_data=types.Blob(
                        mime_type="image/jpeg",
                        data=img_b64
                    )
                ),
                types.Part(text=_VISION_PROMPT),
            ],
        )
        text = (response.text or "").strip()
        return text if text else "OK"
    except Exception as e:
        print(f"[VisionGuardian] Vision API error: {e}")
        return "OK"


def _is_nexo_speaking() -> bool:
    """Prevent interrupting NEXO while it's speaking."""
    try:
        from actions import vision_guardian as _self
        return getattr(_self, "_nexo_speaking_ref", lambda: False)()
    except Exception:
        return False


def _guardian_loop(interval: int, speaking_check: Callable[[], bool]):
    global _last_insight, _is_active
    _is_active = True
    print(f"[VisionGuardian] 👁 Iniciado (cada {interval}s)")

    while not _stop_event.is_set():
        # Wait for the interval (checking stop_event frequently)
        for _ in range(interval * 2):
            if _stop_event.is_set():
                break
            time.sleep(0.5)

        if _stop_event.is_set():
            break

        # Don't run while NEXO is speaking
        if speaking_check():
            continue

        # Capture and analyze
        img_bytes = _capture_screen()
        if not img_bytes:
            continue

        insight = _analyze_screenshot(img_bytes)
        insight = insight.strip()

        if insight and insight.upper() != "OK" and insight != _last_insight:
            _last_insight = insight
            # Inject into NEXO session
            if _inject_callback:
                try:
                    msg = f"[SISTEMA] Alerta del Guardian de Visión: {insight} — Si es relevante, mencionáselo brevemente al usuario."
                    _inject_callback(msg)
                    print(f"[VisionGuardian] 💡 Insight: {insight}")
                except Exception as e:
                    print(f"[VisionGuardian] Inject error: {e}")
        else:
            _last_insight = ""  # Reset so same insight can re-trigger after silence

    _is_active = False
    print("[VisionGuardian] 🛑 Detenido")


def start(
    inject_fn: Callable[[str], None],
    speaking_fn: Callable[[], bool],
    interval: int | None = None,
):
    """Start the vision guardian background thread."""
    global _guardian_thread, _stop_event, _inject_callback

    if _guardian_thread and _guardian_thread.is_alive():
        return  # Already running

    state   = _load_state()
    if not state.get("enabled", False):
        return

    _stop_event.clear()
    _inject_callback = inject_fn

    interval = interval or state.get("interval", _DEFAULT_INTERVAL)

    _guardian_thread = threading.Thread(
        target=_guardian_loop,
        args=(interval, speaking_fn),
        daemon=True,
        name="NEXO-VisionGuardian",
    )
    _guardian_thread.start()


def stop():
    """Stop the vision guardian."""
    global _guardian_thread
    _stop_event.set()
    if _guardian_thread:
        _guardian_thread.join(timeout=2)
        _guardian_thread = None
    print("[VisionGuardian] Detenido por solicitud.")


def vision_guardian(parameters: dict, player=None, **kwargs) -> str:
    """
    Controla el Guardian de Visión Ambiental de NEXO.
    action: 'status' | 'enable' | 'disable' | 'check_now'
    """
    params = parameters or {}
    action = params.get("action", "status").lower()

    state = _load_state()

    if action == "status":
        running = _is_active
        enabled = state.get("enabled", True)
        interval = state.get("interval", _DEFAULT_INTERVAL)
        return (
            f"Guardian de Visión: {'activo' if running else 'inactivo'}. "
            f"{'Habilitado' if enabled else 'Deshabilitado'}, "
            f"analiza cada {interval} segundos."
        )

    elif action == "enable":
        state["enabled"] = True
        _save_state(state)
        return "Guardian de Visión habilitado. Analizaré tu pantalla periódicamente para ofrecerte ayuda proactiva."

    elif action == "disable":
        state["enabled"] = False
        _save_state(state)
        stop()
        return "Guardian de Visión desactivado. No monitorearé la pantalla hasta que lo reactives."

    elif action == "check_now":
        if player:
            player.write_log("[VisionGuardian] Analizando pantalla…")
        img_bytes = _capture_screen()
        if not img_bytes:
            return "No pude capturar la pantalla."
        insight = _analyze_screenshot(img_bytes)
        if insight.upper() == "OK":
            return "La pantalla se ve bien. No detecto nada urgente que requiera atención."
        return f"Observé en tu pantalla: {insight}"

    elif action == "set_interval":
        try:
            secs = int(params.get("seconds", _DEFAULT_INTERVAL))
            secs = max(30, min(600, secs))
            state["interval"] = secs
            _save_state(state)
            return f"Intervalo del Guardian actualizado a {secs} segundos."
        except Exception:
            return "No pude actualizar el intervalo. Especificá los segundos (ej: 60)."

    return f"Acción '{action}' desconocida. Opciones: status, enable, disable, check_now, set_interval."
