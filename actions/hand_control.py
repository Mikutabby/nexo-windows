"""
NEXO — Hand Gesture Control  (MediaPipe Tasks API, mediapipe >= 0.10)
=======================================================================
Gestos:
  • Dedo índice quieto 0.5 s  → CLICK IZQUIERDO simple
  • Dedo índice quieto 1.5 s  → DOBLE CLICK  (acumulado)
  • Todos los dedos cerrados  → DRAG
  • Abrir la mano             → soltar drag
  • Mano fuera del encuadre   → cursor Windows restaurado

FIXES CRÍTICOS vs versiones anteriores:
  1. mouse_event con argtypes explícitos — 100% fiable en 32 y 64-bit.
  2. El dwell rastrea la posición SUAVIZADA EMA del índice, NO la raw ni
     píxeles de pantalla.  La EMA filtra el temblor natural de la mano →
     el dwell ya no se resetea por micro-vibraciones.
  3. Detección de puño vía distancia 2D punta→nudillo (MCP), invariante a la
     orientación.  Antes: tip.y > pip.y falla si la mano está horizontal.
  4. Los clics se ejecutan en _ClickWorker (hilo dedicado) → no bloquean la
     cámara ni los timestamps de MediaPipe.
"""

from __future__ import annotations
import ctypes
import ctypes.wintypes
import math
import queue
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

# ═══════════════════════════════════════════════════════════════════════════════
# Win32 — cursor y clics
# ═══════════════════════════════════════════════════════════════════════════════
_user32 = ctypes.windll.user32

# Definir argtypes explícitamente — garantiza comportamiento correcto en 32 y 64-bit
try:
    _user32.mouse_event.argtypes = [
        ctypes.c_uint,    # dwFlags
        ctypes.c_uint,    # dx
        ctypes.c_uint,    # dy
        ctypes.c_uint,    # dwData
        ctypes.c_size_t,  # dwExtraInfo (ULONG_PTR: 32b en x86, 64b en x64)
    ]
    _user32.mouse_event.restype = None
except Exception:
    pass


def _get_screen_size() -> tuple[int, int]:
    try:
        return _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)
    except Exception:
        return 1920, 1080


def _get_cursor_pos() -> tuple[int, int]:
    pt = ctypes.wintypes.POINT()
    try:
        _user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        w, h = _get_screen_size()
        return w // 2, h // 2


def _move_cursor(x: float, y: float) -> None:
    try:
        _user32.SetCursorPos(int(x), int(y))
    except Exception:
        pass


# mouse_event — simple, probado, funciona desde cualquier hilo
_ME_LDOWN = 0x0002
_ME_LUP   = 0x0004


def _me_down() -> None:
    _user32.mouse_event(_ME_LDOWN, 0, 0, 0, 0)


def _me_up() -> None:
    _user32.mouse_event(_ME_LUP, 0, 0, 0, 0)


# ═══════════════════════════════════════════════════════════════════════════════
# Hilo dedicado para clics  — NO bloquea el loop de cámara
# ═══════════════════════════════════════════════════════════════════════════════
class _ClickWorker:
    """
    Ejecuta clics con sus time.sleep() en un hilo separado.
    La cámara encola 'single' o 'double'; el worker los ejecuta.
    """

    def __init__(self) -> None:
        self._q    : queue.SimpleQueue[str] = queue.SimpleQueue()
        self._alive = True
        self._t     = threading.Thread(target=self._run, daemon=True,
                                       name="NEXOClickWorker")
        self._t.start()

    def _run(self) -> None:
        while self._alive:
            try:
                action = self._q.get(timeout=0.1)
            except Exception:
                continue
            try:
                if action == "single":
                    _me_down()
                    time.sleep(0.06)
                    _me_up()
                    print("[Hand] ✅ Click simple ejecutado")
                elif action == "double":
                    _me_down(); time.sleep(0.06); _me_up()
                    time.sleep(0.07)
                    _me_down(); time.sleep(0.06); _me_up()
                    print("[Hand] ✅ Doble click ejecutado")
            except Exception as e:
                print(f"[Hand] ClickWorker error: {e}")

    def single(self) -> None:
        self._q.put("single")
        print("[Hand] ⏩ Click simple encolado")

    def double(self) -> None:
        self._q.put("double")
        print("[Hand] ⏩ Doble click encolado")

    def shutdown(self) -> None:
        self._alive = False


# ═══════════════════════════════════════════════════════════════════════════════
# Cursor visibility
# ═══════════════════════════════════════════════════════════════════════════════
_cursor_hidden   = False
_cursor_vis_lock = threading.Lock()


def _hide_windows_cursor() -> None:
    """No-op — cursor siempre visible (eliminado por solicitud del usuario)."""
    pass


def _show_windows_cursor() -> None:
    """No-op — cursor siempre visible (eliminado por solicitud del usuario)."""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# MediaPipe
# ═══════════════════════════════════════════════════════════════════════════════
_MODEL_URL  = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)
_MODEL_PATH = (
    Path(__file__).resolve().parent.parent / "assets" / "hand_landmarker.task"
)

try:
    import mediapipe as mp
    from mediapipe.tasks import python as _mp_python
    from mediapipe.tasks.python import vision as _mp_vision
    _HAS_MP = True
except (ImportError, AttributeError, ModuleNotFoundError):
    _HAS_MP = False


def _ensure_model() -> bool:
    if _MODEL_PATH.exists() and _MODEL_PATH.stat().st_size > 1_000_000:
        return True
    try:
        _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        print("[Hand] Descargando modelo MediaPipe (~8 MB)…")
        urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
        return True
    except Exception as e:
        print(f"[Hand] No se pudo descargar el modelo: {e}")
        _MODEL_PATH.unlink(missing_ok=True)
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Constantes
# ═══════════════════════════════════════════════════════════════════════════════
_DEAD_ZONE       = 0.004   # velocidad normalizada mínima para mover cursor
_MAX_DELTA       = 0.10    # clamp por frame
_NO_HAND_FRAMES  = 12      # frames sin mano → restaurar cursor Windows

# Puño: 4 dedos (sin pulgar) cerrados.
# Con 3 (señalar), otros dedos doblados = 3 → falso puño. 4 lo evita.
_FIST_DEBOUNCE   = 5
# Umbral de fracción de la mano: si punta < 55% de escala de la mano desde MCP = cerrado
_FIST_RATIO      = 0.55

# Dwell: usa posición SUAVIZADA EMA del índice (self._sx, self._sy), NO raw ni píxeles.
# La EMA promedia micro-temblores → el dwell no se resetea por vibración natural de la mano.
# Radio 6% del frame = ~38px en cámara 640px. Más forgiving que raw.
_DWELL_RAW_RADIUS = 0.06   # 6% del ancho/alto del frame (tolerancia tremor)

_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (0,9),(9,10),(10,11),(11,12),
    (0,13),(13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20),
    (5,9),(9,13),(13,17),
]


# ═══════════════════════════════════════════════════════════════════════════════
# Configuración
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class HandControlConfig:
    sensitivity      : float = 5.0
    smoothing        : float = 6.0
    dwell_secs_single: float = 0.5   # segundos quieto → click simple
    dwell_secs       : float = 1.5   # segundos quieto → doble click
    dwell_radius     : float = 35.0  # (no usado para dwell, solo referencia visual)

    def ema_alpha(self) -> float:
        return 0.08 + (self.smoothing - 1) / 9.0 * 0.64

    def speed_factor(self) -> float:
        return 1.0 + (self.sensitivity - 1) / 9.0 * 6.0


# ═══════════════════════════════════════════════════════════════════════════════
# Aceleración no-lineal
# ═══════════════════════════════════════════════════════════════════════════════
def _nonlinear_move(vx: float, vy: float, speed: float) -> tuple[float, float]:
    mag = (vx * vx + vy * vy) ** 0.5
    if mag < 1e-10:
        return 0.0, 0.0
    eff = speed * 0.18 * mag + speed * 5.5 * mag * mag
    s   = eff / mag
    return vx * s, vy * s


# ═══════════════════════════════════════════════════════════════════════════════
# Motor
# ═══════════════════════════════════════════════════════════════════════════════
class HandControlEngine:
    """
    Control de cursor con la mano vía MediaPipe HandLandmarker (VIDEO mode).
    Callbacks invocados desde el hilo de cámara — conecta a Qt signals.
    """

    def __init__(
        self,
        on_cursor: Callable[[float, float], None],
        on_fist  : Callable[[bool], None],
        config   : HandControlConfig | None = None,
        min_detection_confidence: float = 0.60,
        min_tracking_confidence : float = 0.50,
    ) -> None:
        if not _HAS_MP:
            raise ImportError("mediapipe no instalado — pip install mediapipe")
        if not _ensure_model():
            raise RuntimeError("No se pudo obtener el modelo de MediaPipe.")

        self._cfg       = config or HandControlConfig()
        self._on_cursor = on_cursor
        self._on_fist   = on_fist
        self._clicker   = _ClickWorker()

        self._sw, self._sh = _get_screen_size()

        # Cursor
        self._cx = float(self._sw // 2)
        self._cy = float(self._sh // 2)
        self._vx = 0.0
        self._vy = 0.0
        self._sx = 0.5   # posición suavizada del índice (overlay visual)
        self._sy = 0.5
        self._prev_raw_x = 0.5
        self._prev_raw_y = 0.5

        # Puño
        self._fist_state  = False
        self._fist_buf    = False
        self._fist_cnt    = 0
        self._is_dragging = False

        # Dwell — anclado en posición RAW de la mano, no en píxeles de pantalla
        self._dwell_rx     = 0.5   # raw x del índice cuando empezó el dwell
        self._dwell_ry     = 0.5   # raw y del índice cuando empezó el dwell
        self._dwell_t0     = 0.0
        self._single_fired = False
        self._dwell_fired  = False
        self._dwell_pct    = 0.0

        # Presencia
        self._no_hand_cnt  = 0
        self._hand_visible = False
        self._first_hand   = True

        self._active = False
        self._lock   = threading.Lock()
        self._t0     = time.perf_counter()

        opts = _mp_vision.HandLandmarkerOptions(
            base_options=_mp_python.BaseOptions(
                model_asset_path=str(_MODEL_PATH)),
            running_mode=_mp_vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=min_detection_confidence,
            min_hand_presence_confidence=0.45,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._landmarker = _mp_vision.HandLandmarker.create_from_options(opts)

    # ── Config ────────────────────────────────────────────────────────────────
    def update_config(self, config: HandControlConfig) -> None:
        with self._lock:
            self._cfg = config

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def _reset_dwell(self, raw_x: float, raw_y: float) -> None:
        self._dwell_rx     = raw_x
        self._dwell_ry     = raw_y
        self._dwell_t0     = time.perf_counter()
        self._single_fired = False
        self._dwell_fired  = False
        self._dwell_pct    = 0.0

    def start(self) -> None:
        ox, oy = _get_cursor_pos()
        self._cx = float(ox)
        self._cy = float(oy)
        self._vx = self._vy = 0.0

        self._fist_state  = False
        self._fist_buf    = False
        self._fist_cnt    = 0
        self._is_dragging = False

        self._reset_dwell(0.5, 0.5)
        self._no_hand_cnt  = 0
        self._hand_visible = False
        self._first_hand   = True
        self._active       = True
        print("[Hand] ✅ Control activo — índice=mover  quieto=click/doble  puño=drag")

    def stop(self) -> None:
        self._active = False
        if self._is_dragging:
            _me_up()
        self._is_dragging = False
        self._on_fist(False)
        _show_windows_cursor()
        self._clicker.shutdown()
        with self._lock:
            if self._landmarker is not None:
                try:
                    self._landmarker.close()
                except Exception:
                    pass
                self._landmarker = None

    # ── Puño robusto — distancia 2D punta→MCP, invariante a orientación ───────
    def _is_fist(self, lm) -> bool:
        """
        Detecta puño comparando la distancia 2D de cada punta al nudillo base (MCP).
        Funciona independientemente de la orientación de la mano.
        Referencia de escala: distancia muñeca (0) → nudillo medio (9).
        """
        wrist = lm[0]; mid_mcp = lm[9]
        scale = ((wrist.x - mid_mcp.x) ** 2 +
                 (wrist.y - mid_mcp.y) ** 2) ** 0.5
        if scale < 1e-6:
            return False

        # (punta, MCP base) para los 4 dedos sin pulgar
        pairs = [(8, 5), (12, 9), (16, 13), (20, 17)]
        curled = 0
        for tip_i, mcp_i in pairs:
            tip = lm[tip_i]; mcp = lm[mcp_i]
            dist = ((tip.x - mcp.x) ** 2 + (tip.y - mcp.y) ** 2) ** 0.5
            if dist < scale * _FIST_RATIO:
                curled += 1
        return curled >= 4   # TODOS cerrados

    # ── Frame ─────────────────────────────────────────────────────────────────
    def process_frame(self, frame_bgr: np.ndarray) -> np.ndarray:
        if not self._active or self._landmarker is None:
            return frame_bgr

        import cv2

        # Espejo horizontal → movimiento natural de trackpad
        frame = cv2.flip(frame_bgr, 1)
        rgb   = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        ts_ms = int((time.perf_counter() - self._t0) * 1000)

        try:
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        except Exception as e:
            print(f"[Hand] mp.Image: {e}")
            return frame

        with self._lock:
            if self._landmarker is None:
                return frame
            result = self._landmarker.detect_for_video(mp_img, ts_ms)
            cfg    = self._cfg

        # ── SIN MANO ──────────────────────────────────────────────────────────
        if not result.hand_landmarks:
            self._no_hand_cnt += 1
            if self._no_hand_cnt >= _NO_HAND_FRAMES and self._hand_visible:
                self._hand_visible = False
                _show_windows_cursor()
                if self._is_dragging:
                    _me_up()
                    self._is_dragging = False
                    self._on_fist(False)
                self._fist_state = False
                self._fist_buf   = False
                self._fist_cnt   = 0
                self._first_hand = True
                self._reset_dwell(0.5, 0.5)
            self._on_cursor(self._cx / self._sw, self._cy / self._sh)
            return frame

        # ── MANO DETECTADA ────────────────────────────────────────────────────
        self._no_hand_cnt = 0
        lm = result.hand_landmarks[0]

        if not self._hand_visible:
            self._hand_visible = True
            _hide_windows_cursor()
            raw_x, raw_y = lm[8].x, lm[8].y
            # En el primer frame la posición suavizada aún no existe → usar raw
            self._reset_dwell(raw_x, raw_y)
            self._sx = raw_x; self._sy = raw_y  # inicializar EMA

        alpha = cfg.ema_alpha()
        speed = cfg.speed_factor()
        raw_x, raw_y = lm[8].x, lm[8].y

        # ── Movimiento ────────────────────────────────────────────────────────
        if self._first_hand:
            self._sx = raw_x; self._sy = raw_y
            self._prev_raw_x = raw_x; self._prev_raw_y = raw_y
            self._vx = self._vy = 0.0
            self._reset_dwell(raw_x, raw_y)
            self._first_hand = False
        else:
            self._sx = alpha * raw_x + (1.0 - alpha) * self._sx
            self._sy = alpha * raw_y + (1.0 - alpha) * self._sy

            dx = max(-_MAX_DELTA, min(_MAX_DELTA, raw_x - self._prev_raw_x))
            dy = max(-_MAX_DELTA, min(_MAX_DELTA, raw_y - self._prev_raw_y))
            self._vx = alpha * dx + (1.0 - alpha) * self._vx
            self._vy = alpha * dy + (1.0 - alpha) * self._vy

            if (self._vx ** 2 + self._vy ** 2) ** 0.5 < _DEAD_ZONE:
                self._vx = self._vy = 0.0

            # Dwell-lock: solo congela cursor en el último 15% de cada etapa
            d_s = cfg.dwell_secs_single
            d_d = cfg.dwell_secs
            sr  = (d_s / d_d) if d_d > 0 else 0.33

            lock = (not self._fist_state) and (
                (not self._single_fired and 0 < d_s and
                 sr * 0.85 < self._dwell_pct < sr + 0.04)
                or
                (self._single_fired and not self._dwell_fired and
                 self._dwell_pct > 0.83)
            )

            if not lock and (self._vx != 0.0 or self._vy != 0.0):
                nx, ny = _nonlinear_move(self._vx, self._vy, speed)
                self._cx = max(0.0, min(float(self._sw - 1),
                                        self._cx + nx * self._sw))
                self._cy = max(0.0, min(float(self._sh - 1),
                                        self._cy + ny * self._sh))
                _move_cursor(self._cx, self._cy)

        self._prev_raw_x = raw_x
        self._prev_raw_y = raw_y
        self._on_cursor(self._cx / self._sw, self._cy / self._sh)

        # ── Puño (debounce) ───────────────────────────────────────────────────
        raw_fist = self._is_fist(lm)

        if raw_fist == self._fist_buf:
            self._fist_cnt += 1
        else:
            self._fist_buf = raw_fist
            self._fist_cnt = 1

        if self._fist_cnt >= _FIST_DEBOUNCE:
            prev             = self._fist_state
            self._fist_state = self._fist_buf

            if self._fist_state and not prev:
                _me_down()
                self._is_dragging  = True
                self._on_fist(True)
                self._single_fired = True
                self._dwell_fired  = True
                self._dwell_pct    = 0.0
                print("[Hand] 🤜 Drag iniciado")

            elif not self._fist_state and prev:
                _me_up()
                self._is_dragging  = False
                self._on_fist(False)
                self._reset_dwell(self._sx, self._sy)  # anclar en posición suavizada
                print("[Hand] 🖐 Drag terminado")

        # ── Dwell (posición SUAVIZADA EMA — filtra temblor natural de la mano) ──
        self._dwell_pct = 0.0
        d_s = cfg.dwell_secs_single
        d_d = cfg.dwell_secs

        if not self._fist_state and d_d > 0:
            # Usar posición suavizada (self._sx/sy) en lugar de raw para comparar.
            # La EMA ya absorbió los micro-temblores → el ancla es estable.
            smooth_dist = ((self._sx - self._dwell_rx) ** 2 +
                           (self._sy - self._dwell_ry) ** 2) ** 0.5

            if smooth_dist > _DWELL_RAW_RADIUS:
                # La mano se desplazó: resetear ancla al punto suavizado actual
                self._reset_dwell(self._sx, self._sy)

            elapsed         = time.perf_counter() - self._dwell_t0
            self._dwell_pct = min(1.0, elapsed / d_d)

            # Etapa 1 — click simple
            if d_s > 0 and elapsed >= d_s and not self._single_fired:
                self._single_fired = True
                self._clicker.single()

            # Etapa 2 — doble click
            if elapsed >= d_d and not self._dwell_fired:
                self._dwell_fired = True
                self._clicker.double()

        # ── Overlay visual ────────────────────────────────────────────────────
        h, w = frame.shape[:2]
        pts  = [(int(lm[i].x * w), int(lm[i].y * h)) for i in range(21)]

        sk = (30, 60, 230) if self._fist_state else (0, 110, 150)
        for a, b in _CONNECTIONS:
            cv2.line(frame, pts[a], pts[b], sk, 1, cv2.LINE_AA)
        for pt in pts:
            cv2.circle(frame, pt, 3, (0, 200, 255), -1, cv2.LINE_AA)

        cx_ov = int(self._sx * w)
        cy_ov = int(self._sy * h)

        if self._fist_state:
            dot = (30, 60, 255)
        elif self._single_fired and not self._dwell_fired:
            dot = (50, 240, 80)
        elif self._dwell_pct > 0.2:
            dot = (0, 200, 120)
        else:
            dot = (0, 212, 255)

        cv2.circle(frame, (cx_ov, cy_ov), 10, dot,          -1, cv2.LINE_AA)
        cv2.circle(frame, (cx_ov, cy_ov), 13, (255,255,255),  1, cv2.LINE_AA)

        # Arco de progreso
        if self._dwell_pct > 0.0 and not self._fist_state:
            sweep = int(self._dwell_pct * 360)
            if self._dwell_fired:
                arc = (0, 255, 220)
            elif self._single_fired:
                arc = (50, 255, 80)
            else:
                arc = (0, 200, 255)
            cv2.ellipse(frame, (cx_ov, cy_ov), (18, 18),
                        -90, 0, sweep, arc, 2, cv2.LINE_AA)

            # Marca blanca donde dispara el click simple
            if d_s > 0 and d_d > 0:
                ang = math.radians(-90.0 + (d_s / d_d) * 360.0)
                mx  = int(cx_ov + 18 * math.cos(ang))
                my  = int(cy_ov + 18 * math.sin(ang))
                cv2.circle(frame, (mx, my), 4, (255, 255, 180), -1, cv2.LINE_AA)

        # HUD
        cv2.rectangle(frame, (0, 0), (w, 28), (4, 13, 21), -1)
        if self._is_dragging:
            hud = "ARRASTRANDO — abre la mano para soltar"
            hc  = (80, 160, 255)
        elif self._dwell_fired:
            hud = "DOBLE CLICK!"
            hc  = (0, 255, 200)
        elif self._single_fired and not self._dwell_fired:
            pct = int(self._dwell_pct * 100)
            hud = f"CLICK! — Quieto para DOBLE CLICK  ({pct}%)"
            hc  = (50, 255, 80)
        elif self._dwell_pct > 0.05:
            pct = int(self._dwell_pct * 100)
            sp  = int((d_s / d_d * 100) if d_d > 0 else 33)
            hud = f"Quieto... {pct}%   [click={sp}%  doble=100%]"
            hc  = (0, 220, 100)
        else:
            hud = (f"Índice=mover  Puño=drag  "
                   f"{d_s:.1f}s=click  {d_d:.1f}s=doble")
            hc  = (0, 212, 255)
        cv2.putText(frame, hud, (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, hc, 1, cv2.LINE_AA)

        return frame
