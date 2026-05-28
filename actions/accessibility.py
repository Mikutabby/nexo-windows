"""
accessibility.py — Modulo de Accesibilidad Universal para NEXO v2
===================================================================
Disenado para personas con discapacidad motriz, cognitiva, visual o auditiva.

Funcionalidades activas:
  - task_simplify:   Descompone instrucciones complejas en pasos simples (Gemini)
  - emotional_regulate: Analiza tono de voz y sugiere pausas/regulacion
  - routine_gamify:   Seguimiento de rutinas diarias con gamificacion
  - eye_tracking:     Control de interfaz mediante seguimiento ocular (OpenCV)
  - micro_movement:   Deteccion de movimientos de cabeza (OpenCV)
  - config:           Ver o cambiar configuracion de accesibilidad
"""
from __future__ import annotations

import json, os, time, math, threading
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Callable
from collections import deque

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
ACC_CFG_PATH = CONFIG_DIR / "accessibility_config.json"
ROUTINE_PATH = CONFIG_DIR / "routine_tracker.json"

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "eye_tracking_enabled": False,
    "eye_tracking_camera_index": 0,
    "eye_tracking_sensitivity": 0.5,
    "task_simplification_enabled": True,
    "emotional_regulation_enabled": False,
    "routine_gamification_enabled": False,
    "micro_movement_enabled": False,
    "micro_movement_camera_index": 0,
    "speech_error_threshold": 0.5,
    "visual_feedback_enabled": True,
    "haptic_feedback_enabled": False,
    "auto_learn_routines": False,
    "high_contrast_mode": False,
    "font_size_scale": 1.0,
    "camera_active": False,
}

def _load_cfg() -> dict:
    try:
        return json.loads(ACC_CFG_PATH.read_text("utf-8"))
    except Exception:
        return {}

def _save_cfg(cfg: dict):
    ACC_CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged = {**DEFAULT_CONFIG, **cfg}
    ACC_CFG_PATH.write_text(json.dumps(merged, indent=2), encoding="utf-8")

def _get(key: str, default=None):
    cfg = _load_cfg()
    return cfg.get(key, DEFAULT_CONFIG.get(key, default))

# ── Helper para Gemini ─────────────────────────────────────────────────────────

def _gemini_client():
    try:
        from google import genai as _genai
        api_key = _get_gemini_key()
        return _genai.Client(api_key=api_key) if api_key else None
    except Exception:
        return None

def _get_gemini_key() -> str:
    try:
        api = json.loads((CONFIG_DIR / "api_keys.json").read_text("utf-8"))
        return api.get("gemini_api_key", "")
    except Exception:
        return ""

# ── 1. Task Simplifier ─────────────────────────────────────────────────────────

def task_simplify(text: str, format: str = "steps") -> str:
    """Descompone una instruccion o texto complejo en pasos simples."""
    if not _get("task_simplification_enabled", True):
        return text

    prompt_map = {
        "steps": "Descompone la siguiente instruccion en pasos simples, numerados y claros. Cada paso debe empezar con un verbo en infinitivo.",
        "summary": "Resume el siguiente texto en 3-5 puntos clave. Usa lenguaje claro y sencillo.",
        "explain": "Explica el siguiente concepto como si tuviera 12 anos. Usa ejemplos cotidianos.",
    }
    prompt = prompt_map.get(format, prompt_map["steps"])
    
    client = _gemini_client()
    if not client:
        return "Error: No hay API key de Gemini configurada."
    
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"{prompt}\n\n{text[:8000]}"
        )
        return response.text.strip()
    except Exception as e:
        return f"Error al simplificar: {e}"

# ── Shared frame buffer (for UI camera preview) ───────────────────────────────

_latest_eye_frame   = None   # numpy BGR frame or None — set only from tracker threads
_latest_micro_frame = None   # numpy BGR frame or None
_frame_lock = threading.Lock()


def get_latest_camera_frame(mode: str = "eye"):
    """Return latest annotated frame (numpy BGR) for UI display, or None."""
    with _frame_lock:
        if mode == "eye":
            return _latest_eye_frame
        return _latest_micro_frame


# ── 2. Eye Tracking (OpenCV) ────────────────────────────────────────────────────

class EyeTracker:
    """Seguimiento ocular con control real del cursor via pyautogui."""

    # Dead-zone around face center (normalized fraction of frame).
    # Smaller = more sensitive; 0.04 keeps cursor still only for tiny jitter.
    DEADZONE = 0.04

    def __init__(self, camera_index: int = 0, sensitivity: float = 0.5):
        self.camera_index  = camera_index
        self.sensitivity   = sensitivity
        self.running       = False
        self.thread        = None
        self.current_position = (0.5, 0.5)
        self.callback      = None
        self._cap          = None
        self._face_cascade = None
        self._cursor_control = True   # actually move the cursor

    def _init_camera(self) -> bool:
        """Open camera WITHOUT DirectShow (CAP_DSHOW causes hard crashes on some systems)."""
        try:
            import cv2
            self._cv2 = cv2
            # Use default backend (MSMF on Windows) — safer than CAP_DSHOW
            self._cap = cv2.VideoCapture(self.camera_index)
            if not self._cap.isOpened():
                print("[EyeTracker] No se pudo abrir la camara")
                return False
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._face_cascade = cv2.CascadeClassifier(cascade_path)
            if self._face_cascade.empty():
                print("[EyeTracker] Clasificador Haar no disponible")
                return False
            # Load eye cascade for blink detection (optional — won't fail if missing)
            eye_path = cv2.data.haarcascades + "haarcascade_eye.xml"
            self._eye_cascade = cv2.CascadeClassifier(eye_path)
            if self._eye_cascade.empty():
                print("[EyeTracker] haarcascade_eye.xml no disponible — blink deshabilitado")
                self._eye_cascade = None
            print("[EyeTracker] Camara inicializada")
            return True
        except ImportError:
            print("[EyeTracker] OpenCV no instalado — pip install opencv-python")
            return False
        except Exception as e:
            print(f"[EyeTracker] Error init: {e}")
            return False

    def start(self, callback: Callable[[float, float], None] = None):
        if self.running:
            return "Seguimiento ocular ya activo."
        self.callback = callback
        # Init camera happens inside the background thread — prevents blocking Qt main thread
        self.running = True
        self.thread = threading.Thread(target=self._track_loop, daemon=True)
        self.thread.start()
        _save_cfg({"eye_tracking_enabled": True, "camera_active": True})
        return "✅ Seguimiento ocular iniciado. Mirá a la cámara — el cursor seguirá tu rostro."

    def stop(self):
        self.running = False
        if self._cap:
            self._cap.release()
            self._cap = None
        global _latest_eye_frame
        with _frame_lock:
            _latest_eye_frame = None
        _save_cfg({"eye_tracking_enabled": False, "camera_active": False})
        return "⏹ Seguimiento ocular detenido."

    def _track_loop(self):
        global _latest_eye_frame
        # Everything inside a try/except — crash here stays contained to thread
        try:
            import cv2
        except ImportError:
            print("[EyeTracker] OpenCV no disponible — thread terminado")
            self.running = False
            return

        # Init camera inside thread (won't block Qt main thread)
        if not self._init_camera():
            self.running = False
            return

        # pyautogui — optional, non-crashing
        _has_pag = False
        _pag = None
        _sw, _sh = 1920, 1080
        try:
            import pyautogui as _pag
            _pag.FAILSAFE = False
            _sw, _sh = _pag.size()
            _has_pag = True
        except Exception:
            pass

        # ctypes fallback for cursor move (safer than pyautogui on some setups)
        _has_ctypes = False
        try:
            import ctypes as _ct
            _has_ctypes = True
        except Exception:
            pass

        def _move_cursor(tx: int, ty: int):
            if _has_ctypes:
                try:
                    _ct.windll.user32.SetCursorPos(tx, ty)
                except Exception:
                    pass
            elif _has_pag:
                try:
                    _pag.moveTo(tx, ty)   # no duration — instant, non-blocking
                except Exception:
                    pass

        # Small buffer = less lag, snappier tracking
        _buf_x: deque = deque(maxlen=3)
        _buf_y: deque = deque(maxlen=3)

        # Blink detection state
        _no_eye_frames   = 0      # consecutive frames with no eye detected inside face
        _was_blinking    = False  # True while eyes are hidden
        _blink_cooldown  = 0.0   # time.time() of last blink-click (prevent double-fire)

        _consecutive_fail = 0
        while self.running and self._cap:
            try:
                ret, frame = self._cap.read()
                if not ret:
                    _consecutive_fail += 1
                    if _consecutive_fail >= 10:
                        print("[EyeTracker] Camara con fallas consecutivas — deteniendo")
                        self.running = False
                        break
                    time.sleep(0.1)
                    continue
                _consecutive_fail = 0

                display = frame.copy()
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self._face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))

                if len(faces) > 0:
                    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                    cx_n = (x + w / 2) / frame.shape[1]
                    cy_n = (y + h / 2) / frame.shape[0]

                    _buf_x.append(cx_n)
                    _buf_y.append(cy_n)
                    sm_x = sum(_buf_x) / len(_buf_x)
                    sm_y = sum(_buf_y) / len(_buf_y)

                    # Fast lerp — high alpha = responsive tracking
                    alpha = 0.3 + self.sensitivity * 0.5  # e.g. 0.5 → alpha=0.55
                    px_c, py_c = self.current_position
                    self.current_position = (
                        px_c * (1 - alpha) + sm_x * alpha,
                        py_c * (1 - alpha) + sm_y * alpha,
                    )

                    if self.callback:
                        try:
                            self.callback(self.current_position[0], self.current_position[1])
                        except Exception:
                            pass

                    if self._cursor_control:
                        cp_x, cp_y = self.current_position
                        dx_c = abs(cp_x - 0.5)
                        dy_c = abs(cp_y - 0.5)
                        # Only move cursor when face moves outside the dead-zone
                        if dx_c > self.DEADZONE or dy_c > self.DEADZONE:
                            # Amplify deviation: small head movement → big cursor movement
                            amp = 1.0 + self.sensitivity * 2.5   # 0.5→2.25×
                            amp_x = max(0.0, min(1.0, 0.5 + (cp_x - 0.5) * amp))
                            amp_y = max(0.0, min(1.0, 0.5 + (cp_y - 0.5) * amp))
                            tx = max(0, min(_sw - 1, int((1.0 - amp_x) * _sw)))
                            ty = max(0, min(_sh - 1, int(amp_y * _sh)))
                            _move_cursor(tx, ty)

                    # ── Blink detection (eye cascade within face ROI) ──
                    _blink_clicked = False
                    if _has_ctypes and self._eye_cascade is not None:
                        face_gray = gray[y:y + h, x:x + w]
                        # Detect eyes inside face region (upper half only → less false hits)
                        upper_half = face_gray[:h // 2, :]
                        eyes_found = self._eye_cascade.detectMultiScale(
                            upper_half, scaleFactor=1.1, minNeighbors=4,
                            minSize=(int(w * 0.12), int(w * 0.12))
                        )
                        now_t = time.time()
                        if len(eyes_found) == 0:
                            # No eyes detected — could be a blink
                            if not _was_blinking:
                                _was_blinking = True
                            _no_eye_frames += 1
                        else:
                            if _was_blinking and 2 <= _no_eye_frames <= 7:
                                # Short disappearance = quick blink → left click
                                if now_t - _blink_cooldown > 0.8:
                                    try:
                                        _ct.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                                        _ct.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                                        _blink_cooldown = now_t
                                        _blink_clicked = True
                                        print("[EyeTracker] 👁 Pestañeo → clic")
                                    except Exception:
                                        pass
                            _was_blinking = False
                            _no_eye_frames = 0

                    # Annotate
                    cv2.rectangle(display, (x, y), (x + w, y + h), (0, 212, 255), 2)
                    cxp = x + w // 2
                    cyp = y + h // 2
                    cv2.line(display, (cxp - 15, cyp), (cxp + 15, cyp), (0, 255, 150), 2)
                    cv2.line(display, (cxp, cyp - 15), (cxp, cyp + 15), (0, 255, 150), 2)
                    blink_label = "  👁 CLICK!" if _blink_clicked else ""
                    cv2.putText(display,
                                f"Cursor {int((1-self.current_position[0])*100)}% {int(self.current_position[1]*100)}%{blink_label}",
                                (8, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 212, 255), 2)
                else:
                    # Face lost → reset blink state
                    _was_blinking = False
                    _no_eye_frames = 0
                    cv2.putText(display, "Rostro no detectado", (8, 58),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80, 80, 255), 2)

                cv2.rectangle(display, (0, 0), (display.shape[1], 40), (4, 13, 21), -1)
                cv2.putText(display, "NEXO Eye Tracking", (8, 28),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 212, 255), 2)

                with _frame_lock:
                    _latest_eye_frame = display

            except Exception as _loop_err:
                print(f"[EyeTracker] Loop error: {_loop_err}")
                time.sleep(0.1)

            time.sleep(0.033)   # ~30 FPS

        # Cleanup
        try:
            if self._cap:
                self._cap.release()
                self._cap = None
        except Exception:
            pass
        self.running = False

    def get_position(self) -> tuple:
        return self.current_position


_eye_tracker: Optional[EyeTracker] = None

def _get_eye_tracker() -> EyeTracker:
    global _eye_tracker
    if _eye_tracker is None:
        _eye_tracker = EyeTracker(
            camera_index=_get("eye_tracking_camera_index", 0),
            sensitivity=_get("eye_tracking_sensitivity", 0.5),
        )
    return _eye_tracker


# ── 3. Micro-Movement Detector (OpenCV) ────────────────────────────────────────

def _default_gesture_action(gesture: str):
    """
    Translate head gesture into a mouse/keyboard action.
    Cursor control (face-to-cursor) runs inside the detect loop itself;
    these discrete gestures handle clicking and scrolling.
    """
    import ctypes as _ct
    _u32 = _ct.windll.user32
    try:
        if gesture == "nod_down":
            # Slow downward nod → left click
            _u32.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
            _u32.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP
            print("[MicroMovement] 🖱 Nod-click → clic izquierdo")
        elif gesture == "nod_up":
            # Upward nod → right click
            _u32.mouse_event(0x0008, 0, 0, 0, 0)   # RIGHTDOWN
            _u32.mouse_event(0x0010, 0, 0, 0, 0)   # RIGHTUP
            print("[MicroMovement] 🖱 Nod-up → clic derecho")
        elif gesture == "tilt_left":
            # Tilt left → scroll up
            _u32.mouse_event(0x0800, 0, 0, _ct.c_ulong(120), 0)  # WHEEL UP
            print("[MicroMovement] ↑ Scroll arriba")
        elif gesture == "tilt_right":
            # Tilt right → scroll down
            _u32.mouse_event(0x0800, 0, 0, _ct.c_ulong(0xFFFFFF88), 0)  # WHEEL DOWN
            print("[MicroMovement] ↓ Scroll abajo")
    except Exception as e:
        print(f"[MicroMovement] Error gesto: {e}")


class MicroMovementDetector:
    """Detector de gestos de cabeza con acciones reales de teclado."""

    GESTURES = {
        "nod_down":  "Confirmar / Enter",
        "nod_up":    "Cancelar / Escape",
        "tilt_left": "Anterior / Flecha Izq",
        "tilt_right":"Siguiente / Flecha Der",
    }

    def __init__(self, camera_index: int = 0, sensitivity: float = 0.5):
        self.camera_index      = camera_index
        self.sensitivity       = sensitivity
        self.running           = False
        self.thread            = None
        self.callback          = None
        self._cap              = None
        self._face_cascade     = None
        self._previous_pos     = None
        self._movement_buffer  = deque(maxlen=15)
        self._last_gesture_time = 0
        self._last_gesture_name = ""

    def _init_camera(self) -> bool:
        try:
            import cv2
            self._cv2 = cv2
            # No CAP_DSHOW — it can cause hard crashes on some Windows setups
            self._cap = cv2.VideoCapture(self.camera_index)
            if not self._cap.isOpened():
                return False
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._face_cascade = cv2.CascadeClassifier(cascade_path)
            return self._cap.isOpened()
        except Exception as e:
            print(f"[MicroMovement] Error init: {e}")
            return False

    def start(self, callback: Callable[[str], None] = None):
        if self.running:
            return "Detector de movimientos ya activo."
        self.callback = callback or _default_gesture_action
        # Init camera in background thread — won't block Qt main thread
        self.running = True
        self.thread = threading.Thread(target=self._detect_loop, daemon=True)
        self.thread.start()
        _save_cfg({"micro_movement_enabled": True, "camera_active": True})
        return (
            "✅ Control por gestos de cabeza iniciado.\n"
            "Gestos: asentir=Enter  •  levantar=Escape  •  girar izq=← der=→"
        )

    def stop(self):
        self.running = False
        if self._cap:
            self._cap.release()
            self._cap = None
        global _latest_micro_frame
        with _frame_lock:
            _latest_micro_frame = None
        _save_cfg({"micro_movement_enabled": False, "camera_active": False})
        return "⏹ Detector de gestos detenido."

    def _detect_loop(self):
        global _latest_micro_frame
        try:
            import cv2
        except ImportError:
            print("[MicroMovement] OpenCV no disponible")
            self.running = False
            return

        if not self._init_camera():
            print("[MicroMovement] No se pudo abrir camara")
            self.running = False
            return

        # ── Win32 cursor helpers (no external dep) ─────────────────────────────
        import ctypes as _ct
        _u32 = _ct.windll.user32
        try:
            _sw = _u32.GetSystemMetrics(0)
            _sh = _u32.GetSystemMetrics(1)
        except Exception:
            _sw, _sh = 1920, 1080

        def _move_cursor_raw(nx: float, ny: float):
            """Move OS cursor from normalized face coords."""
            # Amplify deviation from center so small head movement = big cursor shift
            amp  = 1.0 + self.sensitivity * 2.5   # 0.5 → 2.25×
            ax   = max(0.0, min(1.0, 0.5 + (nx - 0.5) * amp))
            ay   = max(0.0, min(1.0, 0.5 + (ny - 0.5) * amp))
            # Mirror X (face looking right = frame left = cursor right)
            tx   = max(0, min(_sw - 1, int((1.0 - ax) * _sw)))
            ty   = max(0, min(_sh - 1, int(ay * _sh)))
            try:
                _u32.SetCursorPos(tx, ty)
            except Exception:
                pass

        # Smoothed face center for cursor
        _buf_cx: "deque[float]" = deque(maxlen=4)
        _buf_cy: "deque[float]" = deque(maxlen=4)
        _smooth_cx = 0.5
        _smooth_cy = 0.5
        _CURSOR_DEADZONE = 0.035   # normalized — don't move cursor for tiny jitter

        # Dwell-click state
        _DWELL_SECS   = 1.4
        _DWELL_RADIUS = 0.04
        _dwell_cx     = 0.5
        _dwell_cy     = 0.5
        _dwell_t0     = time.time()
        _dwell_fired  = False

        # Gesture label displayed on frame
        _gesture_display = ""
        _gesture_clear_at = 0.0

        _consecutive_fail = 0
        while self.running and self._cap:
            try:
                ret, frame = self._cap.read()
                if not ret:
                    _consecutive_fail += 1
                    if _consecutive_fail >= 10:
                        print("[MicroMovement] Camara con fallas consecutivas — deteniendo")
                        self.running = False
                        break
                    time.sleep(0.1)
                    continue
                _consecutive_fail = 0

                display = frame.copy()
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self._face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))

                if len(faces) > 0:
                    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                    cx_raw = (x + w / 2) / frame.shape[1]
                    cy_raw = (y + h / 2) / frame.shape[0]

                    # ── Smooth cursor position ─────────────────────────────────
                    _buf_cx.append(cx_raw)
                    _buf_cy.append(cy_raw)
                    raw_cx = sum(_buf_cx) / len(_buf_cx)
                    raw_cy = sum(_buf_cy) / len(_buf_cy)
                    _alpha_c = 0.3 + self.sensitivity * 0.4
                    _smooth_cx = _smooth_cx * (1 - _alpha_c) + raw_cx * _alpha_c
                    _smooth_cy = _smooth_cy * (1 - _alpha_c) + raw_cy * _alpha_c

                    # Move cursor only when outside dead-zone
                    if (abs(_smooth_cx - 0.5) > _CURSOR_DEADZONE
                            or abs(_smooth_cy - 0.5) > _CURSOR_DEADZONE):
                        _move_cursor_raw(_smooth_cx, _smooth_cy)

                    # ── Dwell-click ────────────────────────────────────────────
                    _now = time.time()
                    if (abs(_smooth_cx - _dwell_cx) > _DWELL_RADIUS
                            or abs(_smooth_cy - _dwell_cy) > _DWELL_RADIUS):
                        _dwell_cx    = _smooth_cx
                        _dwell_cy    = _smooth_cy
                        _dwell_t0    = _now
                        _dwell_fired = False
                    else:
                        _elapsed = _now - _dwell_t0
                        if _elapsed >= _DWELL_SECS and not _dwell_fired:
                            try:
                                _u32.mouse_event(0x0002, 0, 0, 0, 0)
                                _u32.mouse_event(0x0004, 0, 0, 0, 0)
                                _dwell_fired = True
                                _gesture_display = "👆 DWELL CLICK"
                                _gesture_clear_at = _now + 1.0
                                print("[MicroMovement] 👆 Dwell-click por gesto")
                            except Exception:
                                pass

                    # ── Discrete gesture detection (for scrolling / right-click) ─
                    if self._previous_pos is not None:
                        dx = cx_raw - self._previous_pos[0]
                        dy = cy_raw - self._previous_pos[1]
                        self._movement_buffer.append((dx, dy))

                        if len(self._movement_buffer) >= 8:
                            n = 8
                            avg_dx = sum(d[0] for d in list(self._movement_buffer)[-n:]) / n
                            avg_dy = sum(d[1] for d in list(self._movement_buffer)[-n:]) / n
                            thr    = 0.020 * (1.1 - self.sensitivity)
                            now    = time.time()

                            if now - self._last_gesture_time > 0.8:
                                gesture = ""
                                if avg_dy > thr * 1.5:
                                    gesture = "nod_down"      # fast nod → click
                                elif avg_dy < -thr * 1.5:
                                    gesture = "nod_up"        # fast look-up → right-click
                                elif avg_dx < -thr * 1.8:
                                    gesture = "tilt_left"     # tilt → scroll up
                                elif avg_dx > thr * 1.8:
                                    gesture = "tilt_right"    # tilt → scroll down

                                if gesture:
                                    self._last_gesture_time = now
                                    self._last_gesture_name = gesture
                                    _gesture_display = self.GESTURES.get(gesture, gesture)
                                    _gesture_clear_at = now + 1.5
                                    self._movement_buffer.clear()
                                    # Reset dwell so gesture doesn't trigger dwell-click
                                    _dwell_t0    = now + 0.5
                                    _dwell_fired = False
                                    if self.callback:
                                        threading.Thread(
                                            target=self.callback, args=(gesture,), daemon=True
                                        ).start()

                    self._previous_pos = (cx_raw, cy_raw)

                    # Draw face box + crosshair
                    cv2.rectangle(display, (x, y), (x + w, y + h), (0, 212, 255), 2)
                    cxp, cyp = x + w // 2, y + h // 2
                    cv2.line(display, (cxp - 15, cyp), (cxp + 15, cyp), (0, 255, 150), 2)
                    cv2.line(display, (cxp, cyp - 15), (cxp, cyp + 15), (0, 255, 150), 2)

                    # Draw dwell progress arc over face
                    _now2 = time.time()
                    if not _dwell_fired and (_now2 - _dwell_t0) > 0.1:
                        _pct = min(1.0, (_now2 - _dwell_t0) / _DWELL_SECS)
                        sweep = int(_pct * 360)
                        col   = (0, 255, 100) if _pct < 0.9 else (0, 255, 255)
                        cv2.ellipse(display, (cxp, cyp), (w // 2 + 6, h // 2 + 6),
                                    -90, 0, sweep, col, 2, cv2.LINE_AA)
                else:
                    # Face lost → reset buffers
                    _buf_cx.clear(); _buf_cy.clear()
                    self._previous_pos = None

                # Gesture label overlay
                if time.time() < _gesture_clear_at and _gesture_display:
                    cv2.rectangle(display, (0, display.shape[0] - 36),
                                  (display.shape[1], display.shape[0]), (0, 212, 255), -1)
                    cv2.putText(display, _gesture_display, (8, display.shape[0] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (4, 13, 21), 2)

                cv2.rectangle(display, (0, 0), (display.shape[1], 28), (4, 13, 21), -1)
                cv2.putText(display,
                            "NEXO Head Control  |  Nod=click  Tilt=scroll",
                            (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 212, 255), 1)

                with _frame_lock:
                    _latest_micro_frame = display

            except Exception as _loop_err:
                print(f"[MicroMovement] Loop error: {_loop_err}")
                time.sleep(0.1)

            time.sleep(0.04)   # ~25 FPS

        # Cleanup
        try:
            if self._cap:
                self._cap.release()
                self._cap = None
        except Exception:
            pass
        self.running = False


_micro_detector: Optional[MicroMovementDetector] = None

def _get_micro_detector() -> MicroMovementDetector:
    global _micro_detector
    if _micro_detector is None:
        _micro_detector = MicroMovementDetector(
            camera_index=_get("micro_movement_camera_index", 0),
            sensitivity=_get("eye_tracking_sensitivity", 0.5),
        )
    return _micro_detector

# ── 4. Emotional Regulator ─────────────────────────────────────────────────────

def emotional_regulate(params: dict) -> str:
    """Analiza y sugiere regulacion emocional"""
    action = params.get("action", "status")
    
    if action == "status":
        enabled = _get("emotional_regulation_enabled", False)
        return f"Regulacion emocional: {'activa' if enabled else 'inactiva'}."
    
    if action == "intervene":
        level = float(params.get("stress_level", 0.5))
        if level < 0.3:
            return "Niveles normales. Continuo monitoreando."
        if level < 0.6:
            return "Sugiero una pausa. Respira profundamente."
        return "Nivel elevado detectado. Detente y respira. Puedo ayudarte con:\n- Ejercicios de respiracion\n- Atenuar luces\n- Poner musica relax"
    
    if action == "suggest_calming":
        return (
            "Ejercicio 4-7-8:\n"
            "1. Inhala por 4 segundos\n"
            "2. Sostiene 7 segundos\n"
            "3. Exhala 8 segundos\n"
            "4. Repite 4 veces"
        )
    
    return "Comandos: status, intervene, suggest_calming"

# ── 5. Routine Gamifier ───────────────────────────────────────────────────────

def _load_routines() -> dict:
    try:
        return json.loads(ROUTINE_PATH.read_text("utf-8"))
    except Exception:
        return {"routines": [], "streak": 0, "last_date": ""}

def _save_routines(data: dict):
    ROUTINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ROUTINE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

def routine_gamify(params: dict) -> str:
    """Gestiona rutinas diarias con gamificacion"""
    action = params.get("action", "list")
    data = _load_routines()
    routines = data.get("routines", [])
    streak = data.get("streak", 0)
    today = date.today().isoformat()
    
    if action == "add":
        name = params.get("name", "").strip()
        if not name:
            return "Specify el nombre: routine add name='nombre'"
        routines.append({"name": name, "completed_dates": [], "created": today})
        _save_routines({**data, "routines": routines, "streak": streak})
        return "Rutina '{}' agregada. Di 'completar {}' cuando la hagas.".format(name, name)
    
    if action == "complete":
        name = params.get("name", "").strip()
        if not name:
            return "Que rutina completaste?"
        found = False
        for r in routines:
            if r["name"].lower() == name.lower():
                if today not in r["completed_dates"]:
                    r["completed_dates"].append(today)
                    last = data.get("last_date", "")
                    if last and last != today:
                        streak += 1
                    data["streak"] = streak
                    data["last_date"] = today
                found = True
                break
        if not found:
            return "No existe '{}'. Agregala primero.".format(name)
        
        _save_routines(data)
        msg = "'{}' completada! Racha: {} dias.".format(name, streak)
        if streak >= 7:
            msg += " Una semana!"
        return msg
    
    if action == "list":
        if not routines:
            return "Sin rutinas. Agrega: agregar rutina mi rutina"
        lines = ["Racha: {} dias".format(streak)]
        for r in routines:
            done = "[OK]" if today in r.get("completed_dates", []) else "[--]"
            lines.append("  {} {}".format(done, r['name']))
        return "\n".join(lines)
    
    if action == "progress":
        lines = ["Progreso - Racha: {} dias".format(streak)]
        for r in routines:
            total = len(r.get("completed_dates", []))
            lines.append("  {}: {} completados".format(r['name'], total))
        return "\n".join(lines)
    
    return "routine actions: add, complete, list, progress"

# ── 6. Eye Tracking Command ───────────────────────────────────────────────────

def eye_tracking(params: dict) -> str:
    """Controla el seguimiento ocular"""
    action = params.get("action", "status")
    tracker = _get_eye_tracker()
    
    if action == "status":
        running = tracker.running
        if running:
            px, py = tracker.get_position()
            return f"Seguimiento activo. Posicion: ({px:.1%}, {py:.1%})"
        return "Seguimiento ocular inactivo."
    
    if action == "start":
        return tracker.start()
    
    if action == "stop":
        return tracker.stop()
    
    if action == "sensitivity":
        level = params.get("level")
        if level is not None:
            try:
                level = float(level)
                level = max(0.1, min(1.0, level))
                tracker.sensitivity = level
                _save_cfg({"eye_tracking_sensitivity": level})
                return f"Sensibilidad: {level:.1f}"
            except:
                pass
        return f"Sensibilidad actual: {tracker.sensitivity:.1f}"
    
    return "eye_tracking: start | stop | status | sensitivity level=0.5"

# ── 7. Micro Movement Command ─────────────────────────────────────────────────

def micro_movement(params: dict) -> str:
    """Controla la deteccion de micromovimientos"""
    action = params.get("action", "status")
    detector = _get_micro_detector()
    
    if action == "status":
        return f"Detector: {'activo' if detector.running else 'inactivo'}"
    
    if action == "start":
        return detector.start()
    
    if action == "stop":
        return detector.stop()
    
    if action == "gestures":
        lines = ["Gestos disponibles:"]
        for g, m in MicroMovementDetector.GESTURES.items():
            lines.append(f"  {g}: {m}")
        return "\n".join(lines)
    
    return "micro_movement: start | stop | status | gestures"

# ── 8. Speech Config ─────────────────────────────────────────────────────────

def speech_config(params: dict) -> str:
    """Configura tolerancia de voz"""
    action = params.get("action", "status")
    
    if action == "status":
        thresh = _get("speech_error_threshold", 0.5)
        return f"Tolerancia: {thresh:.1f} (0.1=estricta, 1.0=tolerante)"
    
    if action == "set":
        level = params.get("level")
        if level is not None:
            try:
                level = max(0.1, min(1.0, float(level)))
                _save_cfg({"speech_error_threshold": level})
                return f"Tolerancia: {level:.1f}"
            except:
                pass
        return "speech_config set level=0.5"
    
    return "speech_config: status | set level=0.5"

# ── 9. Feedback Config ─────────────────────────────────────────────────────────

def feedback_config(params: dict) -> str:
    """Configura feedback visual/haptico"""
    action = params.get("action", "status")
    
    if action == "status":
        cfg = _load_cfg()
        return (
            f"Visual: {'on' if cfg.get('visual_feedback_enabled') else 'off'}\n"
            f"Alto contraste: {'on' if cfg.get('high_contrast_mode') else 'off'}\n"
            f"Fuente: {cfg.get('font_size_scale', 1.0)}x"
        )
    
    return "feedback: status"

# ── Main entry point ───────────────────────────────────────────────────────────

def accessibility(parameters: dict, player=None) -> str:
    """Punto de entrada principal del modulo de accesibilidad"""
    action = parameters.get("action", "config").lower()
    
    if action == "task_simplify" or action == "simplify":
        text = parameters.get("text", "") or parameters.get("input", "")
        if not text:
            return "Provide text to simplify: accessibility action='task_simplify' text='tu texto'"
        return task_simplify(text, parameters.get("format", "steps"))
    
    if action in ("emotional", "emotion"):
        return emotional_regulate(parameters)
    
    if action in ("routine", "rutina"):
        return routine_gamify(parameters)
    
    if action in ("eye_tracking", "eye", "ocular"):
        return eye_tracking(parameters)
    
    if action in ("micro_movement", "micro", "movimiento"):
        return micro_movement(parameters)
    
    if action in ("speech_config", "voice"):
        return speech_config(parameters)
    
    if action in ("feedback", "visual"):
        return feedback_config(parameters)
    
    if action == "config":
        sub = parameters.get("setting", "").lower()
        if sub == "view" or sub == "status":
            cfg = {**DEFAULT_CONFIG, **_load_cfg()}
            lines = ["=== Configuracion de Accesibilidad ==="]
            for k, v in cfg.items():
                icon = "✓" if v else "✗"
                lines.append(f"  {icon} {k}: {v}")
            return "\n".join(lines)
        
        if sub == "enable_eye":
            return _get_eye_tracker().start()
        
        if sub == "enable_micro":
            return _get_micro_detector().start()
        
        if sub == "disable_eye":
            return _get_eye_tracker().stop()
        
        if sub == "disable_micro":
            return _get_micro_detector().stop()
        
        return (
            "Comandos de accesibilidad:\n"
            "  task_simplify text='...' — Simplificar instrucciones\n"
            "  emotional — Regulacion emocional\n"
            "  routine add/complete/list — Rutinas gamificadas\n"
            "  eye_tracking start/stop — Seguimiento ocular\n"
            "  micro_movement start/stop — Movimientos de cabeza\n"
            "  speech_config set level=0.5 — Tolerancia de voz\n"
            "  config view — Ver configuracion\n"
            "  config enable_eye — Activar seguimiento ocular\n"
            "  config enable_micro — Activar detector de movimientos"
        )
    
    # ── Extended disability features ─────────────────────────────────────
    if action in ("deaf_mode", "visual_only", "modo_silencioso"):
        return _deaf_mode(parameters)

    if action in ("magnify", "zoom", "ampliar_pantalla"):
        return _magnify(parameters)

    if action in ("colorblind", "daltonismo", "color_filter"):
        return _colorblind_assist(parameters)

    if action in ("sticky_keys", "teclas_pegajosas"):
        return _toggle_sticky_keys(parameters)

    if action in ("dwell_click", "clic_dwell", "clic_morada"):
        return _dwell_click_config(parameters)

    if action in ("reading_mode", "modo_lectura", "leer"):
        return _reading_mode(parameters)

    if action in ("focus_mode", "modo_foco", "sin_distracciones"):
        return _focus_mode(parameters)

    if action in ("switch_access", "acceso_switch", "escaneo"):
        return _switch_access(parameters)

    if action in ("captions", "subtitulos", "closed_captions"):
        return _captions(parameters)

    if action in ("voice_speed", "velocidad_voz", "tts_speed"):
        return _voice_speed(parameters)

    return f"Accion '{action}' no reconocida."


# ── Extended Disability Features ───────────────────────────────────────────────

_DEAF_MODE_ACTIVE = False

def _deaf_mode(params: dict) -> str:
    """Toggle visual-only (deaf/HOH) mode: disables audio, shows text only."""
    global _DEAF_MODE_ACTIVE
    action = params.get("action", params.get("enable", None))
    if action is True or str(action).lower() in ("on", "true", "enable", "start", "activar"):
        _DEAF_MODE_ACTIVE = True
        cfg = _load_cfg()
        cfg["deaf_mode"] = True
        _save_cfg(cfg)
        # Try to mute system audio via NEXO player ref
        try:
            import ctypes
            # Display a large notification window
            pass
        except Exception:
            pass
        return (
            "✅ Modo visual activado (para sordos/hipoacúsicos).\n"
            "NEXO responderá solo con texto. No habrá salida de audio.\n"
            "Para desactivar: 'modo auditivo' o accessibility action='deaf_mode' enable=False"
        )
    else:
        _DEAF_MODE_ACTIVE = False
        cfg = _load_cfg()
        cfg["deaf_mode"] = False
        _save_cfg(cfg)
        return "🔊 Modo auditivo restaurado. NEXO responderá con voz y texto."

def is_deaf_mode() -> bool:
    """Check if deaf/visual-only mode is active."""
    return _load_cfg().get("deaf_mode", False)


def _magnify(params: dict) -> str:
    """Open/close system magnifier or zoom."""
    import platform, subprocess
    action = params.get("action", "toggle")
    system = platform.system()
    level  = params.get("level", 200)  # zoom %

    if system == "Windows":
        if action in ("start", "open", "activar", "abrir"):
            subprocess.Popen(["magnify.exe"])
            return f"🔍 Lupa de Windows abierta."
        elif action in ("stop", "close", "cerrar"):
            subprocess.run(["taskkill", "/IM", "magnify.exe", "/F"],
                           capture_output=True)
            return "Lupa cerrada."
        else:
            subprocess.Popen(["magnify.exe"])
            return "🔍 Lupa abierta. Usa Win++ para aumentar zoom, Win+- para reducir."
    elif system == "Darwin":
        # macOS: toggle accessibility zoom
        subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.universalaccess"])
        return "🔍 Preferencias de accesibilidad abiertas. Activa 'Zoom' en Zoom del teclado."
    else:
        # Linux: try xdotool or just guide
        try:
            subprocess.Popen(["xmag"])
            return "🔍 Zoom activado."
        except Exception:
            return "🔍 Usa Ctrl++ para zoom en la mayoría de apps Linux."


def _colorblind_assist(params: dict) -> str:
    """Colorblind assistance — describe colors, enable magnifier tint, or open OS color filters."""
    import platform
    action = params.get("action", "info")

    if action == "info":
        return (
            "🎨 Asistencia para daltonismo:\n"
            "  • 'activar filtro' — abre filtros de color del SO\n"
            "  • 'describir color #RRGGBB' — describe el color\n"
            "  • Tipos soportados: deuteranopía (rojo-verde), protanopía (rojo), tritanopía (azul)"
        )

    if action in ("describe", "describir"):
        color = params.get("color", "").strip()
        if color.startswith("#") and len(color) == 7:
            try:
                r = int(color[1:3], 16)
                g = int(color[3:5], 16)
                b = int(color[5:7], 16)
                # Simple description
                names = []
                if r > 200 and g < 100 and b < 100:   names.append("rojo intenso")
                elif r > 200 and g > 200 and b < 100: names.append("amarillo")
                elif r < 100 and g > 150 and b < 100: names.append("verde")
                elif r < 100 and g < 100 and b > 200: names.append("azul")
                elif r > 200 and g > 200 and b > 200: names.append("blanco")
                elif r < 50 and g < 50 and b < 50:    names.append("negro")
                elif r > 150 and g > 100 and b > 50:  names.append("naranja o marrón")
                else:                                   names.append("color mixto")
                return f"🎨 {color} → {', '.join(names)} (R={r}, G={g}, B={b})"
            except Exception:
                return "Color inválido. Usa formato #RRGGBB"
        return "Proporciona un color en formato #RRGGBB"

    if action in ("filter", "filtro", "activar"):
        import platform
        if platform.system() == "Windows":
            import subprocess
            subprocess.Popen(
                ["ms-settings:easeofaccess-colorfilter"],
                shell=True
            )
            return "🎨 Abriendo Filtros de Color de Windows (Configuración → Accesibilidad)."
        elif platform.system() == "Darwin":
            import subprocess
            subprocess.Popen(["open",
                "x-apple.systempreferences:com.apple.preference.universalaccess"])
            return "🎨 Abriendo preferencias de accesibilidad macOS."
        else:
            return "🎨 En Linux: instala 'xcalib' o usa las opciones de accesibilidad de tu DE."

    return "colorblind: info | describe color=#RRGGBB | filter"


def _toggle_sticky_keys(params: dict) -> str:
    """Toggle Sticky Keys in Windows (helps motor-impaired users)."""
    import platform, subprocess
    if platform.system() == "Windows":
        action = params.get("action", "open")
        if action in ("open", "abrir", "settings"):
            subprocess.Popen(["ms-settings:easeofaccess-keyboard"], shell=True)
            return "⌨️ Abriendo configuración de teclado accesible (Teclas especiales, Teclas filtro, etc.)"
        # Toggle via reg (StickyKeys)
        try:
            enable = action in ("on", "enable", "activar")
            val = "1" if enable else "0"
            subprocess.run(
                ["reg", "add",
                 "HKCU\\Control Panel\\Accessibility\\StickyKeys",
                 "/v", "Flags", "/t", "REG_SZ",
                 "/d", "510" if enable else "506", "/f"],
                capture_output=True, creationflags=0x08000000,
            )
            return f"⌨️ Teclas pegajosas: {'activadas' if enable else 'desactivadas'}."
        except Exception as e:
            return f"Error: {e}"
    return "⌨️ Teclas pegajosas disponibles en Windows. Usa F8 para activar/desactivar."


def _dwell_click_config(params: dict) -> str:
    """Configure dwell-click (click by hovering) for motor-impaired users."""
    import platform, subprocess
    action = params.get("action", "open")
    if platform.system() == "Windows":
        if action in ("open", "settings", "configurar"):
            subprocess.Popen(["ms-settings:easeofaccess-mouse"], shell=True)
            return "🖱️ Abriendo configuración de ratón accesible en Windows."
        delay = params.get("delay", 1.5)
        return (
            f"🖱️ Clic por permanencia:\n"
            f"  Tiempo actual: {delay}s\n"
            "  Para cambiar: abre Configuración → Accesibilidad → Ratón\n"
            "  O instala 'Dwell Clicker' de Microsoft."
        )
    elif platform.system() == "Darwin":
        subprocess.Popen(["open",
            "x-apple.systempreferences:com.apple.preference.universalaccess"])
        return "🖱️ Abriendo preferencias de accesibilidad macOS para control del puntero."
    return "🖱️ Dwell click: configura en la accesibilidad de tu sistema operativo."


def _reading_mode(params: dict) -> str:
    """Reading/dyslexia assistance mode."""
    action = params.get("action", "info")
    if action == "info":
        return (
            "📖 Modo lectura asistida:\n"
            "  • El texto de NEXO se mostrará de forma más clara\n"
            "  • Respuestas más cortas y directas\n"
            "  • Palabras clave resaltadas\n"
            "Activa con: 'modo lectura on'"
        )
    enable = action in ("on", "enable", "activar", "start")
    cfg = _load_cfg()
    cfg["reading_mode"] = enable
    _save_cfg(cfg)
    if enable:
        return (
            "📖 Modo lectura activado.\n"
            "NEXO usará frases más cortas, vocabulario simple y estructura clara."
        )
    return "📖 Modo lectura desactivado."

def is_reading_mode() -> bool:
    return _load_cfg().get("reading_mode", False)


def _focus_mode(params: dict) -> str:
    """Focus/distraction-free mode for ADHD/cognitive users."""
    import platform, subprocess
    action = params.get("action", "start")
    if action in ("start", "on", "activar"):
        # Windows: enable Focus Assist
        if platform.system() == "Windows":
            try:
                subprocess.Popen(["ms-settings:quiethours"], shell=True)
            except Exception:
                pass
        cfg = _load_cfg()
        cfg["focus_mode"] = True
        _save_cfg(cfg)
        return (
            "🎯 Modo foco activado.\n"
            "• Notificaciones reducidas\n"
            "• NEXO responderá de forma más concisa\n"
            "• Usa 'modo foco off' para desactivar"
        )
    cfg = _load_cfg()
    cfg["focus_mode"] = False
    _save_cfg(cfg)
    return "🎯 Modo foco desactivado."

def is_focus_mode() -> bool:
    return _load_cfg().get("focus_mode", False)


def _switch_access(params: dict) -> str:
    """Switch access / keyboard scanning for severe motor impairment."""
    action = params.get("action", "info")
    if action == "info":
        return (
            "♿ Acceso por switch (escaneo):\n"
            "  NEXO puede controlarse completamente por voz.\n"
            "  Para control por teclado switch:\n"
            "  • Windows: Configuración → Accesibilidad → Teclado en pantalla\n"
            "  • macOS: Preferencias → Accesibilidad → Switch Control\n"
            "  • Linux: GNOME Accesibilidad → Teclado en pantalla"
        )
    import platform, subprocess
    if platform.system() == "Windows":
        if action in ("keyboard", "teclado", "pantalla"):
            subprocess.Popen(["osk.exe"])
            return "⌨️ Teclado en pantalla abierto."
        subprocess.Popen(["ms-settings:easeofaccess-keyboard"], shell=True)
        return "♿ Abriendo opciones de accesibilidad de teclado."
    elif platform.system() == "Darwin":
        subprocess.Popen(["open",
            "x-apple.systempreferences:com.apple.preference.universalaccess"])
        return "♿ Abriendo Switch Control en preferencias de accesibilidad."
    return "♿ Configura el control por switch en la accesibilidad de tu sistema."


def _captions(params: dict) -> str:
    """Closed captions / subtitle settings for deaf/HOH users."""
    import platform, subprocess
    action = params.get("action", "open")
    if platform.system() == "Windows":
        if action in ("open", "settings", "configurar"):
            subprocess.Popen(["ms-settings:easeofaccess-closedcaptioning"], shell=True)
            return "📝 Abriendo configuración de subtítulos cerrados en Windows."
        if action in ("live", "live_captions", "en_vivo"):
            # Windows 11 Live Captions
            try:
                subprocess.Popen(["livecaptions.exe"])
                return "📝 Live Captions iniciado (requiere Windows 11 22H2+)."
            except FileNotFoundError:
                return "📝 Live Captions no disponible. Requiere Windows 11 22H2+."
    elif platform.system() == "Darwin":
        subprocess.Popen(["open",
            "x-apple.systempreferences:com.apple.preference.universalaccess"])
        return "📝 Abriendo preferencias de subtítulos macOS."
    return (
        "📝 Subtítulos/Captions:\n"
        "  'subtitulos settings' — configurar\n"
        "  'subtitulos live' — Live Captions (Win 11)\n"
        "  NEXO siempre muestra texto en la pantalla principal."
    )


def _voice_speed(params: dict) -> str:
    """Adjust TTS/voice speed for cognitive accessibility."""
    action = params.get("action", "status")
    cfg = _load_cfg()
    current = cfg.get("voice_speed", 1.15)

    if action in ("status", "ver"):
        speeds = {0.75: "muy lenta", 1.0: "normal", 1.15: "rápida (NEXO default)", 1.3: "muy rápida"}
        desc = min(speeds, key=lambda k: abs(k - current))
        return f"🔊 Velocidad de voz: {current}x ({speeds[desc]})"

    speed_map = {
        "slow": 0.85, "lento": 0.85, "lenta": 0.85,
        "normal": 1.0, "medium": 1.0,
        "fast": 1.15, "rápido": 1.15, "rapido": 1.15,
        "faster": 1.3, "muy_rapido": 1.3,
    }
    level = params.get("level", action)
    try:
        speed = float(level) if str(level).replace(".","").isdigit() else speed_map.get(str(level).lower(), current)
        speed = max(0.5, min(2.0, speed))
        cfg["voice_speed"] = speed
        _save_cfg(cfg)
        return f"🔊 Velocidad de voz ajustada a {speed}x. Efectivo al reconectar NEXO."
    except Exception as e:
        return f"Error: {e}. Usa: voice_speed level=0.85 (lento) | 1.0 (normal) | 1.3 (rápido)"