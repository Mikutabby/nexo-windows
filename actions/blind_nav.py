"""
NEXO — Navegacion por voz para usuarios con discapacidad visual
=================================================================
Permite controlar toda la PC mediante comandos de voz.

COMO FUNCIONA:
  1. El usuario activa el modo ciego desde la configuracion.
  2. NEXO escucha continuamente (o al pulsar el hotkey).
  3. El usuario habla un comando natural: "abre Chrome", "click en aceptar",
     "escribe hola mundo", "que hay en la pantalla", etc.
  4. NEXO toma un screenshot, lo analiza con Gemini Vision y ejecuta la accion.
  5. NEXO narra el resultado en voz alta.

DEPENDENCIAS:
  - google-generativeai   (ya instalado en NEXO)
  - pyttsx3               (TTS offline; fallback: Windows SAPI)
  - Pillow                (screenshot; fallback: mss)
  - pyaudio + speech_recognition (microfono; ya usados en NEXO)
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import io
import json
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

# ── Win32 para acciones de mouse/teclado ──────────────────────────────────────
_user32   = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# Flags de mouse_event
_ME_LDOWN  = 0x0002
_ME_LUP    = 0x0004
_ME_RDOWN  = 0x0008
_ME_RUP    = 0x0010
_ME_WHEEL  = 0x0800

# Flags de keybd_event / SendInput (VK codes comunes)
_VK = {
    "enter": 0x0D, "escape": 0x1B, "tab": 0x09, "backspace": 0x08,
    "space": 0x20, "delete": 0x2E, "up": 0x26, "down": 0x28,
    "left": 0x25, "right": 0x27, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "f1": 0x70, "f2": 0x71,
    "f3": 0x72, "f4": 0x73, "f5": 0x74, "alt": 0x12,
    "ctrl": 0x11, "shift": 0x10, "win": 0x5B,
}


def _click(x: int, y: int, right: bool = False) -> None:
    _user32.SetCursorPos(x, y)
    time.sleep(0.05)
    dn = _ME_RDOWN if right else _ME_LDOWN
    up = _ME_RUP   if right else _ME_LUP
    _user32.mouse_event(dn, 0, 0, 0, 0)
    time.sleep(0.05)
    _user32.mouse_event(up, 0, 0, 0, 0)


def _double_click(x: int, y: int) -> None:
    _click(x, y)
    time.sleep(0.08)
    _click(x, y)


def _scroll(direction: str, amount: int = 3) -> None:
    delta = 120 * amount * (-1 if direction == "down" else 1)
    _user32.mouse_event(_ME_WHEEL, 0, 0, ctypes.c_int(delta), 0)


def _press_key(vk: int) -> None:
    _user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    _user32.keybd_event(vk, 0, 0x0002, 0)   # KEYEVENTF_KEYUP


def _type_text(text: str) -> None:
    """Escribe texto caracter por caracter usando SendInput Unicode."""
    INPUT_KEYBOARD = 1
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP   = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk",         ctypes.wintypes.WORD),
            ("wScan",       ctypes.wintypes.WORD),
            ("dwFlags",     ctypes.wintypes.DWORD),
            ("time",        ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class _INPUT(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.wintypes.DWORD), ("_input", _INPUT)]

    inputs = []
    for ch in text:
        code = ord(ch)
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            ki = KEYBDINPUT(0, code, flags, 0, None)
            inp = INPUT(INPUT_KEYBOARD, _INPUT(ki))
            inputs.append(inp)

    arr = (INPUT * len(inputs))(*inputs)
    ctypes.windll.user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


# ── TTS ───────────────────────────────────────────────────────────────────────
class _TTS:
    """Text-to-speech: pyttsx3 → SAPI → noop."""

    def __init__(self, rate: int = 175):
        self._engine = None
        self._lock   = threading.Lock()
        self._rate   = rate
        self._thread: threading.Thread | None = None
        self._queue: list[str] = []
        self._ev     = threading.Event()
        self._stop   = False
        self._init()
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def _init(self) -> None:
        try:
            import pyttsx3
            eng = pyttsx3.init()
            eng.setProperty("rate", self._rate)
            voices = eng.getProperty("voices")
            # Preferir voz en español si existe
            for v in (voices or []):
                if "spanish" in v.name.lower() or "es-" in getattr(v, "id", "").lower():
                    eng.setProperty("voice", v.id)
                    break
            self._engine = eng
        except Exception:
            self._engine = None

    def say(self, text: str) -> None:
        with self._lock:
            self._queue.append(text)
        self._ev.set()

    def _worker(self) -> None:
        while not self._stop:
            self._ev.wait()
            self._ev.clear()
            while True:
                with self._lock:
                    if not self._queue:
                        break
                    text = self._queue.pop(0)
                self._speak_now(text)

    def _speak_now(self, text: str) -> None:
        if self._engine:
            try:
                self._engine.say(text)
                self._engine.runAndWait()
                return
            except Exception:
                pass
        # Fallback: Windows SAPI via PowerShell
        try:
            ps = (
                f"Add-Type -AssemblyName System.Speech; "
                f"$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Rate={max(-5, min(5, (self._rate - 175) // 25))}; "
                f"$s.Speak([System.Text.Encoding]::UTF8.GetString("
                f"[System.Text.Encoding]::UTF8.GetBytes('{text.replace(chr(39), '')}')));"
                f"$s.Dispose()"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                timeout=15, capture_output=True,
            )
        except Exception:
            pass   # Sin TTS disponible — silencioso

    def stop(self) -> None:
        self._stop = True
        self._ev.set()


# ── Screenshot ────────────────────────────────────────────────────────────────
def _take_screenshot() -> bytes | None:
    """Captura la pantalla completa y devuelve bytes JPEG."""
    try:
        from PIL import ImageGrab
        img  = ImageGrab.grab()
        buf  = io.BytesIO()
        img.save(buf, "JPEG", quality=82)
        return buf.getvalue()
    except Exception:
        pass
    try:
        import mss, mss.tools
        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[0])
            from PIL import Image as _PILImage
            img = _PILImage.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=82)
            return buf.getvalue()
    except Exception:
        return None


# ── Gemini Vision ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """Eres NEXO, asistente de accesibilidad para un usuario con discapacidad visual.
El usuario no puede ver la pantalla y depende completamente de ti.

Cuando recibas un comando:
1. Analiza la captura de pantalla provista.
2. Determina la accion mas adecuada para cumplir el comando.
3. Responde SOLO con un JSON valido, sin ningun texto adicional.

Formato de respuesta:
{
  "action": "click" | "double_click" | "right_click" | "type" | "press_key" |
             "scroll" | "open" | "describe" | "none",
  "description": "Descripcion clara de lo que ves y lo que vas a hacer (para leer al usuario)",
  "x": 0,           // pixel x en pantalla (para click)
  "y": 0,           // pixel y en pantalla (para click)
  "text": "",       // texto a escribir (para type)
  "key": "",        // nombre de tecla (enter, escape, tab, etc.)
  "direction": "",  // "up" o "down" (para scroll)
  "amount": 3,      // lineas de scroll
  "app": ""         // nombre de app a abrir (para open)
}

La pantalla tiene resolucion SCREEN_WxSCREEN_H px.
Si no encuentras el elemento pedido, action="describe" y explica lo que ves.
Siempre incluye "description" en español claro y corto para narrar al usuario."""


def _call_gemini_vision(api_key: str, screenshot_bytes: bytes,
                         command: str, screen_w: int, screen_h: int) -> dict | None:
    """Llama a Gemini Vision con el screenshot y el comando del usuario."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        model  = genai.GenerativeModel("gemini-1.5-flash")
        system = _SYSTEM_PROMPT.replace("SCREEN_W", str(screen_w)) \
                                .replace("SCREEN_H", str(screen_h))

        img_part = {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(screenshot_bytes).decode(),
        }
        prompt = f"{system}\n\nComando del usuario: \"{command}\""
        resp   = model.generate_content([prompt, img_part])
        raw    = resp.text.strip()

        # Extraer JSON del response (puede venir dentro de ```json...```)
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            return json.loads(m.group())
    except Exception as e:
        print(f"[BlindNav] Gemini error: {e}")
    return None


# ── BlindNavigator ────────────────────────────────────────────────────────────
class BlindNavigator:
    """
    Motor de navegacion por voz para usuarios con discapacidad visual.

    Uso:
        nav = BlindNavigator(api_key, on_status=callback)
        nav.start()          # activa escucha continua
        nav.stop()           # desactiva
        nav.process_text(t)  # procesa un comando ya transcrito
    """

    def __init__(
        self,
        api_key      : str = "",
        on_status    : Callable[[str], None] | None = None,
        tts_rate     : int = 175,
        gemini_api_key: str | None = None,   # alias
    ):
        self._api_key   = gemini_api_key if gemini_api_key is not None else api_key
        self._on_status = on_status or (lambda s: None)
        self._tts       = _TTS(rate=tts_rate)
        self._running   = False
        self._lock      = threading.Lock()

        # Dimensiones de pantalla
        try:
            _u = ctypes.windll.user32
            self._sw = _u.GetSystemMetrics(0)
            self._sh = _u.GetSystemMetrics(1)
        except Exception:
            self._sw, self._sh = 1920, 1080

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
        self._on_status("activo")
        self._tts.say(
            "Navegación por voz activada. "
            "Puedes decirme qué quieres hacer y yo lo haré por ti. "
            "Por ejemplo: describe la pantalla, abre Chrome, "
            "o haz click en el botón aceptar."
        )

    def stop(self) -> None:
        with self._lock:
            self._running = False
        self._on_status("inactivo")
        self._tts.say("Navegación por voz desactivada.")

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    # ── Procesar comando ───────────────────────────────────────────────────────
    def process_text(self, text: str) -> None:
        """
        Procesa un comando de voz ya transcrito.
        Llama a Gemini Vision, ejecuta la accion y narra el resultado.
        Se puede llamar desde cualquier hilo.
        """
        if not self._running:
            return
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    def _process(self, text: str) -> None:
        self._on_status(f"procesando: {text[:40]}")

        # Comandos locales sin necesitar screenshot
        lower = text.lower().strip()
        if any(w in lower for w in ("silencio", "para", "stop", "calla")):
            self._on_status("activo")
            return

        # Tomar screenshot
        shot = _take_screenshot()
        if shot is None:
            self._tts.say("No pude capturar la pantalla. Intenta de nuevo.")
            self._on_status("activo")
            return

        # Consultar Gemini Vision
        result = _call_gemini_vision(
            self._api_key, shot, text, self._sw, self._sh
        )
        if result is None:
            self._tts.say(
                "Tuve un problema al analizar la pantalla. "
                "Verifica tu conexión a internet."
            )
            self._on_status("activo")
            return

        description = result.get("description", "")
        action      = result.get("action", "none")

        # Narrar descripcion primero
        if description:
            self._tts.say(description)

        # Ejecutar accion
        try:
            self._execute(result)
        except Exception as e:
            print(f"[BlindNav] Error ejecutando accion: {e}")
            self._tts.say(f"Ocurrió un error al ejecutar la acción: {action}")

        self._on_status("activo")

    def _execute(self, action_dict: dict) -> None:
        """Ejecuta la accion devuelta por Gemini."""
        action = action_dict.get("action", "none")

        if action in ("click", "double_click", "right_click"):
            x = int(action_dict.get("x", self._sw // 2))
            y = int(action_dict.get("y", self._sh // 2))
            # Clampar coordenadas a la pantalla
            x = max(0, min(self._sw - 1, x))
            y = max(0, min(self._sh - 1, y))
            if action == "double_click":
                _double_click(x, y)
            elif action == "right_click":
                _click(x, y, right=True)
            else:
                _click(x, y)
            time.sleep(0.3)

        elif action == "type":
            text = action_dict.get("text", "")
            if text:
                _type_text(text)
                time.sleep(0.2)

        elif action == "press_key":
            key = action_dict.get("key", "").lower()
            vk  = _VK.get(key)
            if vk:
                _press_key(vk)
                time.sleep(0.1)
            elif len(key) == 1:
                _type_text(key)

        elif action == "scroll":
            direction = action_dict.get("direction", "down")
            amount    = int(action_dict.get("amount", 3))
            _scroll(direction, amount)

        elif action == "open":
            app = action_dict.get("app", "")
            if app:
                try:
                    subprocess.Popen(
                        f'start "" "{app}"',
                        shell=True, creationflags=0x00000008,
                    )
                except Exception:
                    try:
                        subprocess.Popen(["explorer", app])
                    except Exception:
                        pass

        elif action == "describe":
            pass   # ya se narro la descripcion arriba

        # "none" → no hacer nada adicional

    # ── TTS rate ───────────────────────────────────────────────────────────────
    def set_tts_rate(self, rate_normalized: float) -> None:
        """Ajusta la velocidad de voz TTS. rate_normalized: 0.1–1.0."""
        # Mapear 0.1–1.0 a ~100–250 wpm para pyttsx3
        wpm = int(100 + rate_normalized * 150)
        self._tts._rate = wpm
        if self._tts._engine is not None:
            try:
                self._tts._engine.setProperty("rate", wpm)
            except Exception:
                pass

    # ── Shortcuts de comandos por voz sin screenshot ──────────────────────────
    def quick_describe(self) -> None:
        """Describe la pantalla actual en voz alta sin pedir comando."""
        threading.Thread(target=self._quick_describe, daemon=True).start()

    def _quick_describe(self) -> None:
        self._on_status("describiendo pantalla...")
        shot = _take_screenshot()
        if shot is None:
            self._tts.say("No pude capturar la pantalla.")
            self._on_status("activo")
            return
        result = _call_gemini_vision(
            self._api_key, shot,
            "Describe detalladamente todo lo que ves en esta pantalla para un usuario ciego.",
            self._sw, self._sh,
        )
        if result:
            self._tts.say(result.get("description", "No pude obtener descripción."))
        else:
            self._tts.say("No pude describir la pantalla.")
        self._on_status("activo")
