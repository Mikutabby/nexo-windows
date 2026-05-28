"""
screen_reader.py — Lector de pantalla y navegación por voz para NEXO.

Designed for blind and motor-impaired users. Features:
  • TTS inmediato (SAPI Windows) — sin deps extra
  • Descripción de pantalla optimizada para ciegos (via Gemini Vision)
  • Encontrar y hacer clic en elementos por descripción de voz
  • Navegar: escribir, teclas, scroll, ventanas
  • Monitoreo continuo de cambios en pantalla
  • Modo ciego: respuestas siempre detalladas y en audio
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

# ── Optional imports ──────────────────────────────────────────────────────────
try:
    import mss
    import mss.tools
    _HAS_MSS = True
except ImportError:
    _HAS_MSS = False

try:
    import PIL.Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    _HAS_GUI = True
except ImportError:
    _HAS_GUI = False

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE = Path(__file__).resolve().parent.parent
_CFG  = _BASE / "config" / "api_keys.json"

# ── Internal state ─────────────────────────────────────────────────────────────
_monitor_thread: threading.Thread | None = None
_monitor_stop   = threading.Event()
_last_window_title = ""
_tts_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# TTS — Windows SAPI via PowerShell (zero extra deps, always available)
# ─────────────────────────────────────────────────────────────────────────────

def _tts_speak(text: str, rate: int = 1, wait: bool = False):
    """
    Speak text immediately using Windows SAPI (no pyttsx3 needed).
    rate: -10 (very slow) to +10 (very fast). 0 = normal, 1 = slightly fast.
    wait=True blocks until speech finishes.
    """
    if not text or not text.strip():
        return
    # Escape for PowerShell single-quoted string
    safe = text.replace("'", " ").replace('"', ' ').replace('\n', '. ')[:1000]
    ps_cmd = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Rate = {rate}; "
        f"$s.Speak('{safe}')"
    )
    CREATE_NO_WINDOW = 0x08000000
    if wait:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            creationflags=CREATE_NO_WINDOW, timeout=30,
        )
    else:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            creationflags=CREATE_NO_WINDOW,
        )


def _tts_stop():
    """Stop all active SAPI speech (kill powershell processes speaking)."""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process powershell | Where-Object {$_.MainWindowTitle -eq ''} | Stop-Process -Force"],
            creationflags=0x08000000, timeout=5,
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Gemini Vision helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_api_key() -> str:
    try:
        return json.loads(_CFG.read_text("utf-8")).get("gemini_api_key", "")
    except Exception:
        return ""


def _capture_screen(monitor: int = 0) -> tuple[bytes, str]:
    """Capture primary screen and return (jpeg_bytes, mime_type)."""
    png: bytes = b""
    if _HAS_MSS:
        with mss.mss() as sct:
            mons = sct.monitors
            idx = min(monitor + 1, len(mons) - 1)
            shot = sct.grab(mons[idx])
            png = mss.tools.to_png(shot.rgb, shot.size)
    else:
        try:
            from PIL import ImageGrab as _ig
            img = _ig.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            png = buf.getvalue()
        except Exception as e:
            raise RuntimeError(f"No se pudo capturar pantalla: {e}")

    if _HAS_PIL:
        from PIL import Image as _PILImage
        img2 = _PILImage.open(io.BytesIO(png)).convert("RGB")
        img2.thumbnail((1280, 720), _PILImage.BILINEAR)
        buf2 = io.BytesIO()
        img2.save(buf2, format="JPEG", quality=75)
        return buf2.getvalue(), "image/jpeg"
    return png, "image/png"


def _ask_gemini_vision(image_bytes: bytes, mime: str, prompt: str) -> str:
    """Send image + prompt to Gemini Vision and return text response."""
    from google import genai
    from google.genai import types as gt
    client = genai.Client(
        api_key=_get_api_key(),
        http_options={"api_version": "v1beta"},
    )
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            gt.Part.from_bytes(data=image_bytes, mime_type=mime),
            gt.Part.from_text(text=prompt),
        ],
    )
    return (resp.text or "").strip()


# ─────────────────────────────────────────────────────────────────────────────
# Screen description optimized for blind users
# ─────────────────────────────────────────────────────────────────────────────

_BLIND_SYSTEM = (
    "Sos NEXO, asistente de IA. Estás ayudando a una persona ciega o con baja visión. "
    "Tu descripción de pantalla DEBE ser:"
    "\n• Exhaustiva: describe TODO lo que hay en pantalla."
    "\n• Ordenada: de arriba a abajo, izquierda a derecha."
    "\n• Específica: menciona nombres de botones, etiquetas, textos visibles."
    "\n• Orientada a la acción: dice qué puede hacer el usuario con cada elemento."
    "\n• En español, vos (Argentina)."
    "\nNO uses frases como 'la imagen muestra'. Describe como si narraras en vivo."
)


def _describe_screen_for_blind(monitor: int = 0, question: str = "") -> str:
    """Get a detailed screen description suitable for blind users."""
    image_bytes, mime = _capture_screen(monitor)
    if question:
        prompt = f"{_BLIND_SYSTEM}\n\nPregunta específica: {question}"
    else:
        prompt = (
            f"{_BLIND_SYSTEM}\n\n"
            "Describí en detalle qué hay en pantalla ahora mismo. "
            "Empezá por: qué aplicación está activa, qué ventana/pestaña, "
            "qué contenido principal hay, y qué controles/botones son visibles."
        )
    return _ask_gemini_vision(image_bytes, mime, prompt)


def _read_active_window_title() -> str:
    """Get the title of the currently active window."""
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value or ""
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Find element on screen and click it (AI-powered)
# ─────────────────────────────────────────────────────────────────────────────

def _find_element_coordinates(description: str) -> tuple[int, int] | None:
    """
    Use Gemini Vision to find where a UI element is on screen.
    Returns (x, y) pixel coordinates or None if not found.
    """
    image_bytes, mime = _capture_screen(0)
    W = 1920  # fallback — we'll use the actual screen size
    try:
        import ctypes
        W = ctypes.windll.user32.GetSystemMetrics(0)
        H = ctypes.windll.user32.GetSystemMetrics(1)
    except Exception:
        H = 1080

    prompt = (
        f"En esta captura de pantalla, encontrá el elemento: \"{description}\".\n"
        f"La pantalla es de {W}×{H} píxeles.\n"
        "Respondé ÚNICAMENTE con las coordenadas del CENTRO del elemento en este formato exacto:\n"
        "X=NNN Y=NNN\n"
        "Donde NNN son píxeles desde la esquina superior izquierda.\n"
        "Si el elemento no existe en pantalla, respondé exactamente: NO_ENCONTRADO"
    )
    result = _ask_gemini_vision(image_bytes, mime, prompt)
    m = re.search(r"X\s*=\s*(\d+)\s+Y\s*=\s*(\d+)", result, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _click_element(description: str, double: bool = False) -> str:
    """Find element by description and click it."""
    if not _HAS_GUI:
        return "❌ pyautogui no está instalado (pip install pyautogui)."
    coords = _find_element_coordinates(description)
    if coords is None:
        return f"❌ No encontré '{description}' en la pantalla."
    x, y = coords
    if double:
        pyautogui.doubleClick(x, y)
    else:
        pyautogui.click(x, y)
    return f"✅ Clic en '{description}' — coordenadas ({x}, {y})."


# ─────────────────────────────────────────────────────────────────────────────
# Dwell click — hands-free clicking by hovering
# ─────────────────────────────────────────────────────────────────────────────

_dwell_thread: threading.Thread | None = None
_dwell_stop = threading.Event()
_DWELL_TIME  = 2.0   # seconds to hold still before auto-click
_DWELL_RADIUS = 20   # pixels of movement allowed


def _dwell_loop():
    """Background loop: auto-click when cursor stays still for DWELL_TIME seconds."""
    if not _HAS_GUI:
        return
    last_pos = pyautogui.position()
    still_since = time.time()
    last_click_pos = (-999, -999)

    while not _dwell_stop.is_set():
        time.sleep(0.1)
        try:
            pos = pyautogui.position()
        except Exception:
            continue

        dx = abs(pos.x - last_pos.x)
        dy = abs(pos.y - last_pos.y)

        if dx > _DWELL_RADIUS or dy > _DWELL_RADIUS:
            last_pos = pos
            still_since = time.time()
            continue

        held = time.time() - still_since
        if held >= _DWELL_TIME:
            # Don't click in the same spot twice in a row
            cdx = abs(pos.x - last_click_pos[0])
            cdy = abs(pos.y - last_click_pos[1])
            if cdx > _DWELL_RADIUS or cdy > _DWELL_RADIUS:
                pyautogui.click(pos.x, pos.y)
                last_click_pos = (pos.x, pos.y)
            still_since = time.time() + 0.5  # cooldown


def _start_dwell():
    global _dwell_thread
    if _dwell_thread and _dwell_thread.is_alive():
        return "Clic por permanencia ya activo."
    _dwell_stop.clear()
    _dwell_thread = threading.Thread(target=_dwell_loop, daemon=True)
    _dwell_thread.start()
    return "✅ Clic por permanencia activado (2 segundos de espera)."


def _stop_dwell():
    global _dwell_thread
    _dwell_stop.set()
    _dwell_thread = None
    return "⏹ Clic por permanencia desactivado."


# ─────────────────────────────────────────────────────────────────────────────
# Screen change monitor
# ─────────────────────────────────────────────────────────────────────────────

def _monitor_loop():
    """Announce window title changes for blind users."""
    global _last_window_title
    while not _monitor_stop.is_set():
        time.sleep(1.5)
        title = _read_active_window_title()
        if title and title != _last_window_title:
            _last_window_title = title
            _tts_speak(f"Ventana: {title}", rate=2)


def _start_monitor() -> str:
    global _monitor_thread
    if _monitor_thread and _monitor_thread.is_alive():
        return "Monitor de pantalla ya activo."
    _monitor_stop.clear()
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
    _monitor_thread.start()
    return "✅ Monitor activado — NEXO anunciará cada cambio de ventana."


def _stop_monitor() -> str:
    _monitor_stop.set()
    return "⏹ Monitor de pantalla desactivado."


# ─────────────────────────────────────────────────────────────────────────────
# Read clipboard
# ─────────────────────────────────────────────────────────────────────────────

def _read_clipboard() -> str:
    try:
        import ctypes
        CF_UNICODETEXT = 13
        ctypes.windll.user32.OpenClipboard(0)
        h = ctypes.windll.user32.GetClipboardData(CF_UNICODETEXT)
        text = ctypes.wstring_at(h)
        ctypes.windll.user32.CloseClipboard()
        return text or ""
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Main action dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def screen_reader(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "describe").lower().strip()

    def _log(msg: str):
        print(f"[ScreenReader] {msg}")
        if player:
            try:
                player.write_log(f"[reader] {msg}")
            except Exception:
                pass

    # ── describe / read — describe screen for blind users ────────────────────
    if action in ("describe", "read", "ver", "leer", "pantalla"):
        question = params.get("question", params.get("q", "")).strip()
        _log("Analizando pantalla para usuario con discapacidad visual…")

        # Get current cursor position — always include for blind users
        _cursor_info = ""
        try:
            import ctypes as _ct_sr
            class _PT(_ct_sr.Structure):
                _fields_ = [("x", _ct_sr.c_long), ("y", _ct_sr.c_long)]
            _pt = _PT()
            _ct_sr.windll.user32.GetCursorPos(_ct_sr.byref(_pt))
            _cursor_info = f"Posición del cursor: X={_pt.x}, Y={_pt.y}."
        except Exception:
            pass

        try:
            description = _describe_screen_for_blind(
                monitor=int(params.get("monitor", 0)),
                question=question,
            )
            # Prepend cursor position so blind user always knows where cursor is
            if _cursor_info:
                description = f"{_cursor_info}\n\n{description}"
            return description
        except Exception as e:
            return f"❌ Error describiendo pantalla: {e}"

    # ── read_window — announce active window ──────────────────────────────────
    elif action in ("read_window", "ventana", "window"):
        title = _read_active_window_title()
        if not title:
            msg = "No pude obtener el título de la ventana activa."
        else:
            msg = f"Ventana activa: {title}"
        return msg

    # ── read_clipboard — speak clipboard content ──────────────────────────────
    elif action in ("read_clipboard", "portapapeles", "clipboard"):
        text = _read_clipboard()
        if not text:
            msg = "El portapapeles está vacío."
        elif len(text) > 500:
            msg = f"Portapapeles ({len(text)} caracteres): {text[:500]}… (truncado)"
        else:
            msg = f"Portapapeles: {text}"
        return msg

    # ── click_here — click at current cursor position (blind: "haz click ahí") ─
    elif action in ("click_here", "click_ahi", "clic_ahi", "ahi", "aqui",
                    "click_there", "clic_aqui", "hacer_clic_ahi"):
        try:
            import ctypes as _ct_click
            class _PT2(_ct_click.Structure):
                _fields_ = [("x", _ct_click.c_long), ("y", _ct_click.c_long)]
            _pt2 = _PT2()
            _ct_click.windll.user32.GetCursorPos(_ct_click.byref(_pt2))
            _ct_click.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
            _ct_click.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
            msg = f"✅ Clic en ({_pt2.x}, {_pt2.y})."
            return msg
        except Exception as e:
            return f"❌ Error al hacer clic: {e}"

    # ── click — find element by description and click ─────────────────────────
    elif action in ("click", "clic", "hacer_clic", "presionar"):
        element = params.get("element", params.get("target", "")).strip()
        if not element:
            # No element specified → click at current cursor position
            try:
                import ctypes as _ct_cc
                class _PT3(_ct_cc.Structure):
                    _fields_ = [("x", _ct_cc.c_long), ("y", _ct_cc.c_long)]
                _pt3 = _PT3()
                _ct_cc.windll.user32.GetCursorPos(_ct_cc.byref(_pt3))
                _ct_cc.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                _ct_cc.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                msg = f"✅ Clic en la posición del cursor: ({_pt3.x}, {_pt3.y})."
                return msg
            except Exception as e:
                return f"❌ Error al hacer clic: {e}"
        double = str(params.get("double", "false")).lower() == "true"
        _log(f"Buscando '{element}' en pantalla…")
        result = _click_element(element, double=double)
        return result

    # ── type — type text via keyboard ─────────────────────────────────────────
    elif action in ("type", "escribir", "tipear", "write"):
        text = params.get("text", params.get("content", "")).strip()
        if not text:
            return "❌ Especificá el texto a escribir."
        if not _HAS_GUI:
            return "❌ pyautogui no está instalado."
        try:
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
        except ImportError:
            pyautogui.write(text, interval=0.04)
        msg = f"✅ Texto escrito: '{text[:40]}{'…' if len(text) > 40 else ''}'"
        return msg

    # ── key — press keyboard key or shortcut ─────────────────────────────────
    elif action in ("key", "tecla", "shortcut", "atajo"):
        key = params.get("key", params.get("shortcut", "")).strip().lower()
        if not key:
            return "❌ Especificá la tecla (ej: 'enter', 'tab', 'alt+f4', 'ctrl+c')."
        if not _HAS_GUI:
            return "❌ pyautogui no está instalado."
        try:
            if "+" in key:
                parts = [k.strip() for k in key.split("+")]
                pyautogui.hotkey(*parts)
            else:
                pyautogui.press(key)
            msg = f"✅ Tecla presionada: {key}"
            return msg
        except Exception as e:
            return f"❌ Error al presionar tecla: {e}"

    # ── scroll — scroll up/down/left/right ────────────────────────────────────
    elif action in ("scroll", "desplazar", "deslizar"):
        direction = params.get("direction", "down").lower()
        amount    = int(params.get("amount", 3))
        if not _HAS_GUI:
            return "❌ pyautogui no está instalado."
        clicks = amount if direction in ("up", "arriba") else -amount
        if direction in ("left", "izquierda"):
            pyautogui.hscroll(-amount)
            msg = f"✅ Scroll izquierda {amount}."
        elif direction in ("right", "derecha"):
            pyautogui.hscroll(amount)
            msg = f"✅ Scroll derecha {amount}."
        else:
            pyautogui.scroll(clicks)
            dir_word = "arriba" if clicks > 0 else "abajo"
            msg = f"✅ Scroll {dir_word} {amount}."
        return msg

    # ── announce — speak arbitrary text immediately ───────────────────────────
    elif action in ("announce", "decir", "speak", "hablar", "leer_texto"):
        text = params.get("text", params.get("message", "")).strip()
        if not text:
            return "❌ Especificá el texto a anunciar."
        return text

    # ── stop — stop current TTS speech ───────────────────────────────────────
    elif action in ("stop", "silenciar", "parar", "callar"):
        _tts_stop()
        return "🔇 Lectura detenida."

    # ── monitor_start / monitor_stop — announce window title changes ──────────
    elif action in ("monitor_start", "iniciar_monitor", "monitor"):
        return _start_monitor()

    elif action in ("monitor_stop", "detener_monitor"):
        return _stop_monitor()

    # ── dwell_start / dwell_stop — hands-free clicking ───────────────────────
    elif action in ("dwell_start", "iniciar_dwell", "dwell", "permanencia"):
        return _start_dwell()

    elif action in ("dwell_stop", "detener_dwell"):
        return _stop_dwell()

    # ── help — list available commands ───────────────────────────────────────
    elif action in ("help", "ayuda", "comandos"):
        commands = [
            "📋 COMANDOS DE ACCESIBILIDAD NEXO",
            "",
            "🖥  PANTALLA (para usuarios ciegos):",
            "  'describí la pantalla'  — descripción detallada de todo lo visible",
            "  'qué ventana tengo abierta'  — nombre de la ventana activa",
            "  'leé el portapapeles'  — contenido copiado",
            "  'activar monitor de pantalla'  — anuncia cambios de ventana automáticamente",
            "",
            "🖱  NAVEGACIÓN:",
            "  'hacé clic en [elemento]'  — ej: 'hacé clic en el botón Guardar'",
            "  'doble clic en [elemento]'  — doble clic en elemento",
            "  'scrolleá arriba/abajo'  — desplazar pantalla",
            "  'presioná [tecla]'  — ej: 'presioná Enter', 'presioná Alt+F4'",
            "  'escribí [texto]'  — escribir texto en el campo activo",
            "",
            "⏱  CLIC POR PERMANENCIA (sin manos):",
            "  'activar clic por permanencia'  — clic automático al mantener cursor quieto 2s",
            "  'desactivar clic por permanencia'",
            "",
            "🔊  VOZ:",
            "  'leé [texto]'  — NEXO lee el texto en voz alta",
            "  'silenciá el lector'  — detener lectura actual",
        ]
        help_text = "\n".join(commands)
        return help_text

    return (
        f"Acción '{action}' no reconocida. "
        "Decí 'ayuda de accesibilidad' para ver todos los comandos disponibles."
    )
