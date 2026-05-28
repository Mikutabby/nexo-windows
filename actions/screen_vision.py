"""
screen_vision.py — NEXO puede ver la pantalla del usuario.
Captura la pantalla (incluso con NEXO en segundo plano) y la analiza
con Gemini Vision. Basado en el mismo patrón probado de screen_processor.py.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from pathlib import Path

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import PIL.Image
    _PIL = True
except ImportError:
    _PIL = False

from google import genai
from google.genai import types as gtypes


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE        = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"
_VISION_MODEL = "gemini-2.5-flash"

_SYSTEM = (
    "Eres NEXO, el asistente IA de Tony Stark. "
    "REGLA ABSOLUTA: responde ÚNICAMENTE en español, jamás en inglés. "
    "Analiza la imagen con precisión. Sé conciso pero completo."
)


def _get_api_key() -> str:
    try:
        return json.loads(_CONFIG_PATH.read_text("utf-8")).get("gemini_api_key", "")
    except Exception:
        return ""


def _capture_screen(monitor: int = 0) -> tuple[bytes, str]:
    """
    Captura la pantalla aunque NEXO esté en segundo plano.
    monitor=0 → monitor principal (monitors[1] en mss).
    monitor=1 → segundo monitor (monitors[2] en mss).
    monitors[0] en mss es el virtual combinado de todos.
    """
    if not _MSS:
        if _PIL:
            import PIL.ImageGrab
            img = PIL.ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return _compress(buf.getvalue()), "image/jpeg"
        raise RuntimeError("Instalá mss: pip install mss")

    with mss.mss() as sct:
        mons = sct.monitors  # [0]=combinado, [1]=primario, [2]=secundario...
        # map user index 0→primary(1), 1→secondary(2), etc.
        target_idx = monitor + 1
        if target_idx >= len(mons):
            target_idx = 1 if len(mons) > 1 else 0
        shot = sct.grab(mons[target_idx])
        png  = mss.tools.to_png(shot.rgb, shot.size)

    return _compress(png), "image/jpeg"


def _compress(png_bytes: bytes) -> bytes:
    """Escala y comprime a JPEG para reducir tokens."""
    if not _PIL:
        return png_bytes
    try:
        img = PIL.Image.open(io.BytesIO(png_bytes)).convert("RGB")
        img.thumbnail((1280, 720), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75, optimize=False)
        return buf.getvalue()
    except Exception:
        return png_bytes


def _launch_scan_overlay():
    """Launch the HUD scanning overlay as a subprocess (non-blocking)."""
    overlay = Path(__file__).resolve().parent / "screen_scanner_overlay.py"
    if not overlay.exists():
        print("[Vision] overlay script not found — skipping")
        return
    try:
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
            interpreter = str(base / "pythonw.exe") if (base / "pythonw.exe").exists() else sys.executable
        else:
            py = sys.executable
            # Prefer pythonw.exe (no console window) in same directory as python.exe
            candidate = Path(py).parent / "pythonw.exe"
            interpreter = str(candidate) if candidate.exists() else py

        # CREATE_NO_WINDOW keeps things clean; no DETACHED_PROCESS (can cause env issues)
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            [interpreter, str(overlay)],
            creationflags=CREATE_NO_WINDOW,
        )
        print(f"[Vision] overlay launched: {interpreter}")
    except Exception as e:
        print(f"[Vision] overlay launch failed (non-fatal): {e}")


def screen_vision(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    action   = (parameters.get("action") or "describe").lower().strip()
    question = (parameters.get("question") or "").strip()
    monitor  = int(parameters.get("monitor") or 0)

    if player:
        player.write_log("👁 Vision: capturando pantalla…")
        try:
            player.set_state("THINKING")
        except Exception:
            pass

    # ── Captura (funciona aunque NEXO esté minimizado/en fondo) ────────────
    try:
        image_bytes, mime_type = _capture_screen(monitor)
        print(f"[Vision] 🖥️  Captura: {len(image_bytes):,} bytes  monitor={monitor}")
    except Exception as e:
        return f"❌ No pude capturar la pantalla: {e}"

    # ── Lanzar overlay de escaneo (DESPUÉS de capturar, para no contaminarlo) ─
    _launch_scan_overlay()

    # ── Construir prompt ──────────────────────────────────────────────────────
    if action == "describe" or not question:
        prompt = (
            "Describe en detalle qué está mostrando esta pantalla. "
            "¿Qué aplicaciones están abiertas? ¿Qué está haciendo el usuario? "
            "Responde en español, de forma natural y concisa."
        )
    elif action == "question":
        prompt = question
    elif action == "help":
        prompt = (
            f"El usuario está mirando esta pantalla y necesita ayuda. "
            f"{'Pregunta: ' + question if question else '¿Con qué necesita ayuda?'} "
            f"Dá instrucciones claras y específicas basadas en lo que se ve."
        )
    elif action == "read":
        prompt = (
            "Lee y transcribe TODO el texto visible en esta pantalla. "
            "Organiza la información de forma legible."
        )
    else:
        prompt = question or "¿Qué ves en esta pantalla?"

    full_prompt = f"{_SYSTEM}\n\nPregunta: {prompt}"

    # ── Análisis con Gemini Vision (mismo patrón que screen_processor.py) ────
    try:
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"},
        )

        t0 = time.perf_counter()
        resp = client.models.generate_content(
            model=_VISION_MODEL,
            contents=[
                gtypes.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                gtypes.Part.from_text(text=full_prompt),
            ],
        )
        elapsed = time.perf_counter() - t0

        result = (resp.text or "").strip()
        print(f"[Vision] ✅ {elapsed:.2f}s — {result[:80]}")

        if player:
            player.write_log(f"Vision: {result[:60]}…")

        return result

    except Exception as e:
        msg = f"❌ Error analizando la pantalla: {e}"
        print(f"[Vision] ❌ {e}")
        return msg
    finally:
        if player:
            try:
                player.set_state("LISTENING")
            except Exception:
                pass
