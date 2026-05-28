"""
screen_processor.py — Vision module for NEXO
Uses Gemini generate_content (NOT Live) to analyse images.
Returns plain text → main NEXO session speaks it.
No separate audio stream, no race conditions, always Spanish.
"""
from __future__ import annotations

import base64
import io
import json
import sys
import time
from pathlib import Path

import numpy as np

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False

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


# ── Config ─────────────────────────────────────────────────────────────────────

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

_BASE        = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"

def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_config_key(key: str, value) -> None:
    try:
        cfg = _load_config()
        cfg[key] = value
        _CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"[Vision] ⚠️  No se pudo guardar '{key}': {e}")

def _get_api_key() -> str:
    key = _load_config().get("gemini_api_key", "")
    if not key:
        raise RuntimeError("gemini_api_key no encontrada en config.")
    return key

def _get_os() -> str:
    return _load_config().get("os_system", "windows").lower()


# ── Vision model (fast, multimodal, NOT Live) ──────────────────────────────────
_VISION_MODEL = "gemini-2.5-flash"

_VISION_SYSTEM = (
    "Eres NEXO, el asistente IA de Tony Stark. "
    "REGLA ABSOLUTA E IRROMPIBLE: responde ÚNICAMENTE en español. "
    "Jamás uses inglés, ni una sola palabra. "
    "Analiza la imagen con precisión. "
    "Sé conciso — máximo 2 oraciones salvo que pidan más detalle. "
    "Habla con el humor seco y compostura británica de NEXO."
)


# ── Image compression ──────────────────────────────────────────────────────────
_IMG_MAX_W = 640
_IMG_MAX_H = 480
_JPEG_Q    = 70

def _compress(img_bytes: bytes, source_format: str = "PNG") -> tuple[bytes, str]:
    if not _PIL:
        return img_bytes, f"image/{source_format.lower()}"
    try:
        img = PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
        return buf.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"[Vision] ⚠️  Compresión fallida: {e}")
        return img_bytes, f"image/{source_format.lower()}"


# ── Screen capture ─────────────────────────────────────────────────────────────
def _capture_screen() -> tuple[bytes, str]:
    if not _MSS:
        raise RuntimeError("mss no instalado. Ejecuta: pip install mss")
    with mss.mss() as sct:
        monitors = sct.monitors
        target   = monitors[1] if len(monitors) > 1 else monitors[0]
        shot     = sct.grab(target)
        png      = mss.tools.to_png(shot.rgb, shot.size)
    return _compress(png, "PNG")


# ── Camera capture ─────────────────────────────────────────────────────────────
def _cv2_backend() -> int:
    if not _CV2:
        return 0
    os_name = _get_os()
    if os_name == "windows":
        return cv2.CAP_DSHOW
    if os_name == "mac":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_ANY

def _probe_camera(index: int, backend: int, warmup: int = 3) -> bool:
    if not _CV2:
        return False
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return False
    for _ in range(warmup):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return False
    return bool(np.mean(frame) > 8)

def _detect_camera_index() -> int:
    backend = _cv2_backend()
    print("[Vision] 🔍 Buscando cámara...")
    for idx in range(6):
        if _probe_camera(idx, backend):
            print(f"[Vision] ✅ Cámara encontrada en índice {idx}")
            _save_config_key("camera_index", idx)
            return idx
        print(f"[Vision] ⚠️  Índice {idx}: sin frame útil")
    print("[Vision] ⚠️  Sin cámara — usando índice 0")
    _save_config_key("camera_index", 0)
    return 0

def _get_camera_index() -> int:
    cfg = _load_config()
    if "camera_index" in cfg:
        return int(cfg["camera_index"])
    return _detect_camera_index()

def _capture_camera() -> tuple[bytes, str]:
    # Intentar frame del bus de cámara compartido (UI preview) — 3 intentos
    for attempt in range(3):
        try:
            from actions.camera_bus import get_frame
            fb, fm = get_frame(max_age=2.0)
            if fb:
                print(f"[Vision] 📷 Frame del preview UI: {len(fb):,} bytes")
                return fb, fm
        except Exception:
            pass
        if attempt < 2:
            time.sleep(0.1)

    if not _CV2:
        raise RuntimeError("OpenCV no instalado. Ejecuta: pip install opencv-python")

    index   = _get_camera_index()
    backend = _cv2_backend()
    cap     = cv2.VideoCapture(index, backend)

    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir la cámara índice {index}.")

    # Warmup frames para que la cámara se estabilice
    for _ in range(8):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError("La cámara no devolvió ningún frame.")

    if _PIL:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(rgb)
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q)

        # Share captured frame back to bus for other consumers
        try:
            from actions.camera_bus import put_frame
            put_frame(buf.getvalue())
        except Exception:
            pass

        return buf.getvalue(), "image/jpeg"

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_Q])

    try:
        from actions.camera_bus import put_frame
        put_frame(buf.tobytes())
    except Exception:
        pass

    return buf.tobytes(), "image/jpeg"


# ── Main entry point ───────────────────────────────────────────────────────────
def screen_process(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Capture screen or camera, analyse with Gemini, return Spanish text.
    The caller (main NEXO) speaks the returned text — no separate audio stream.
    """
    params    = parameters or {}
    user_text = (params.get("text") or params.get("user_text") or "").strip()
    angle     = params.get("angle", "screen").lower().strip()

    if not user_text:
        user_text = "¿Qué ves en la imagen?"

    print(f"[Vision] ▶  angle={angle!r}  pregunta='{user_text[:80]}'")

    # ── Signal UI ──────────────────────────────────────────────────────────────
    if player:
        player.write_log("Vision: 📷 Analizando...")
        try:
            player.set_state("THINKING")
        except Exception:
            pass

    # ── Capture ────────────────────────────────────────────────────────────────
    try:
        if angle == "camera":
            image_bytes, mime_type = _capture_camera()
            print(f"[Vision] 📷 Captura cámara: {len(image_bytes):,} bytes")
        else:
            image_bytes, mime_type = _capture_screen()
            print(f"[Vision] 🖥️  Captura pantalla: {len(image_bytes):,} bytes")
    except Exception as e:
        msg = f"No pude capturar la imagen: {e}"
        print(f"[Vision] ❌ {msg}")
        return msg

    # ── Analyse with Gemini generate_content (fast, reliable) ─────────────────
    try:
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"},
        )

        b64_data = base64.b64encode(image_bytes).decode("ascii")

        t0 = time.perf_counter()
        resp = client.models.generate_content(
            model=_VISION_MODEL,
            contents=[
                gtypes.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                gtypes.Part.from_text(
                    text=f"{_VISION_SYSTEM}\n\nPregunta: {user_text}"
                ),
            ],
        )
        elapsed = time.perf_counter() - t0

        result_text = (resp.text or "").strip()
        print(f"[Vision] ✅ Análisis en {elapsed:.2f}s — {result_text[:80]}")

        if player:
            player.write_log(f"Vision: {result_text}")
            try:
                player.set_state("LISTENING")
            except Exception:
                pass

        return result_text

    except Exception as e:
        msg = f"Error al analizar la imagen: {e}"
        print(f"[Vision] ❌ {msg}")
        return msg


# ── Compat stub (warmup no longer needed but kept for imports) ─────────────────
def warmup_session(player=None) -> None:
    pass


# ── CLI test ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[TEST] screen_processor.py")
    print("=" * 52)
    mode = input("angle — screen / camera (default: camera): ").strip().lower() or "camera"
    q    = input("Pregunta (Enter = default): ").strip() or "¿Qué ves en la imagen?"

    t0  = time.perf_counter()
    res = screen_process({"angle": mode, "text": q})
    print(f"\nRespuesta ({time.perf_counter()-t0:.2f}s):\n{res}")
