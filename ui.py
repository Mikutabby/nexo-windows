"""
NEXO UI v5.0 — Full Screen Redesign
- Orb fills the entire screen; dashboard hidden by default
- Widgets hidden at startup, NEXO shows/hides them on demand
- Orb shrinks to bottom-left corner when a widget appears
- Real-time transcription in white, below the neural network
- Interactive orb: left-click repels, right-click/drag attracts
- Camera widget with real cv2 capture
- No gradients on widget bars — pure black header, white text
- Smoother morphing: interpolated formation transitions
- Many new particle formations (tornado, crystallize, breathe, etc.)
"""
from __future__ import annotations

import json
import math
import os
import platform
import random
import re
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime as _dt
from pathlib import Path

try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _BA_TZ = _ZoneInfo("America/Argentina/Buenos_Aires")
except Exception:
    from datetime import timezone as _tz, timedelta as _td
    _BA_TZ = _tz(_td(hours=-3))


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _load_tz_from_config():
    """Load timezone from api_keys.json config."""
    global _BA_TZ
    try:
        api_fp = _base_dir() / "config" / "api_keys.json"
        if api_fp.exists():
            d = json.loads(api_fp.read_text(encoding="utf-8"))
            tz_name = d.get("timezone", "")
            if tz_name:
                try:
                    _BA_TZ = _ZoneInfo(tz_name)
                    print(f"[UI TZ] Timezone loaded: {tz_name}")
                except Exception as e:
                    print(f"[UI TZ] Failed to load '{tz_name}': {e}")
                    import zoneinfo as _zi
                    available = _zi.available_timezones()
                    tz_lower = tz_name.lower()
                    for known in available:
                        if known.lower() == tz_lower:
                            _BA_TZ = _ZoneInfo(known)
                            print(f"[UI TZ] Matched '{tz_name}' → '{known}'")
                            break
                    else:
                        parts = tz_name.replace("\\", "/").split("/")
                        short = parts[-1].lower() if parts else ""
                        for known in available:
                            if known.lower().endswith("/" + short):
                                _BA_TZ = _ZoneInfo(known)
                                print(f"[UI TZ] Partial match '{tz_name}' → '{known}'")
                                break
    except Exception as e:
        print(f"[UI TZ] Error reading config: {e}")


# Call on module load
_load_tz_from_config()

import psutil

from PyQt6.QtCore import (
    QEasingCurve, QPointF, QPropertyAnimation, QParallelAnimationGroup,
    QRect, QRectF, Qt, QTimer, pyqtSignal, QSize, QPoint,
    QSequentialAnimationGroup,
)
from PyQt6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QAction,
    QFont, QIcon, QImage, QKeySequence, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap, QRadialGradient, QShortcut,
    QCursor, QMouseEvent,
)
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QSlider,
    QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QPushButton, QScrollArea, QSizePolicy,
    QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget, QGraphicsDropShadowEffect,
    QStackedWidget, QSplashScreen, QStyle,
)

try:
    from sounds import start_thinking_sound, stop_thinking_sound
except Exception:
    def start_thinking_sound(): pass
    def stop_thinking_sound(): pass

# ── Google Maps embedded browser ─────────────────────────────
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtCore import QUrl
    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"
TODO_FILE  = CONFIG_DIR / "todos.json"
NOTES_FILE = CONFIG_DIR / "notes.txt"

_OS        = platform.system()
_DEFAULT_W = 1440
_DEFAULT_H = 860
_MIN_W     = 960
_MIN_H     = 620

TRANS_H    = 90    # Transcript strip height (below orb)
INPUT_H    = 80    # Input bar height (bottom of window)
HEADER_H   = 40    # Header bar height
MINI_W     = 210   # Mini orb width
MINI_H     = 210   # Mini orb height

# Accessibility camera state
_eye_tracking_active = False
_micro_movement_active = False


# ═══════════════════════════════════════════════════════════
# THEMES — color palettes
# ═══════════════════════════════════════════════════════════
THEMES: dict[str, dict] = {
    "cyan": {                          # default NEXO
        "PRI": "#00d4ff", "PRI_DIM": "#005f77", "PRI_GHO": "#001820",
        "BORDER": "#0d2540", "BORDER_A": "#1a5070",
        "TEXT": "#7aeeff", "TEXT_DIM": "#2e6070", "TEXT_MED": "#4aaccf",
        "BG": "#050c14", "GRID": "#0a1620", "PANEL": "#070f18",
        "MUTED_C": "#ff3366",
    },
    "green": {                         # Matrix green
        "PRI": "#00ff88", "PRI_DIM": "#006633", "PRI_GHO": "#001a0a",
        "BORDER": "#0a2a18", "BORDER_A": "#155a30",
        "TEXT": "#7affcc", "TEXT_DIM": "#1f5535", "TEXT_MED": "#3aaa77",
        "BG": "#040e08", "GRID": "#081a10", "PANEL": "#061208",
        "MUTED_C": "#ff3366",
    },
    "red": {                           # Red Alert
        "PRI": "#ff3b30", "PRI_DIM": "#7a1a15", "PRI_GHO": "#1a0000",
        "BORDER": "#3a0a0a", "BORDER_A": "#6a1515",
        "TEXT": "#ffaaaa", "TEXT_DIM": "#5a2020", "TEXT_MED": "#cc5555",
        "BG": "#0e0404", "GRID": "#1a0808", "PANEL": "#120505",
        "MUTED_C": "#ff8800",
    },
    "purple": {                        # Quantum Purple
        "PRI": "#a855f7", "PRI_DIM": "#5b21b6", "PRI_GHO": "#150030",
        "BORDER": "#2d1b69", "BORDER_A": "#4c1d95",
        "TEXT": "#c084fc", "TEXT_DIM": "#3b2062", "TEXT_MED": "#8b5cf6",
        "BG": "#07030f", "GRID": "#0f0618", "PANEL": "#0a0412",
        "MUTED_C": "#f43f5e",
    },
    "gold": {                          # Amber Gold
        "PRI": "#f59e0b", "PRI_DIM": "#78350f", "PRI_GHO": "#1a0e00",
        "BORDER": "#292524", "BORDER_A": "#57534e",
        "TEXT": "#fde68a", "TEXT_DIM": "#57430c", "TEXT_MED": "#d97706",
        "BG": "#0c0a00", "GRID": "#1a1400", "PANEL": "#100c00",
        "MUTED_C": "#ef4444",
    },
    "white": {                         # Platino / Light
        "PRI": "#e2e8f0", "PRI_DIM": "#64748b", "PRI_GHO": "#0f172a",
        "BORDER": "#1e293b", "BORDER_A": "#334155",
        "TEXT": "#cbd5e1", "TEXT_DIM": "#475569", "TEXT_MED": "#94a3b8",
        "BG": "#050a14", "GRID": "#0c1626", "PANEL": "#080f1e",
        "MUTED_C": "#f43f5e",
    },
}

THEME_LABELS = {
    "cyan":   ("NEXO Cyan",   "#00d4ff"),
    "green":  ("Matrix Green",  "#00ff88"),
    "red":    ("Red Alert",     "#ff3b30"),
    "purple": ("Quantum Purple","#a855f7"),
    "gold":   ("Amber Gold",    "#f59e0b"),
    "white":  ("Platino",       "#e2e8f0"),
}

def _load_theme() -> str:
    """Read theme from config and apply to C class. Returns theme name."""
    try:
        from pathlib import Path as _P
        cfg_path = _P(__file__).resolve().parent / "config" / "api_keys.json"
        cfg = json.loads(cfg_path.read_text("utf-8"))
        name = cfg.get("nexo_theme", "cyan")
    except Exception:
        name = "cyan"
    if name not in THEMES:
        name = "cyan"
    t = THEMES[name]
    for attr, val in t.items():
        setattr(C, attr, val)
    return name

def _save_theme(name: str):
    """Persist theme name to api_keys.json."""
    try:
        from pathlib import Path as _P
        cfg_path = _P(__file__).resolve().parent / "config" / "api_keys.json"
        cfg = json.loads(cfg_path.read_text("utf-8"))
        cfg["nexo_theme"] = name
        cfg_path.write_text(json.dumps(cfg, indent=4, ensure_ascii=False), "utf-8")
    except Exception:
        pass

def _apply_theme_stylesheet(app: "QApplication", name: str):
    """Apply a comprehensive global Qt stylesheet for the active theme.
    Covers scrollbars, tooltips, dialogs, inputs, combos, checkboxes, tabs, etc.
    Custom-painted widgets (ParticleOrb, WidgetHeader…) already read C.* attrs
    directly in paintEvent so they update automatically on the next frame.
    """
    if name not in THEMES:
        name = "cyan"
    t     = THEMES[name]
    pri   = t["PRI"]
    bg    = t["BG"]
    panel = t["PANEL"]
    bdr   = t["BORDER"]
    bdr_a = t["BORDER_A"]
    txt   = t["TEXT"]
    dim   = t["TEXT_DIM"]
    med   = t["TEXT_MED"]
    app.setStyleSheet(f"""
        /* ── Scrollbars ─────────────────────────────────────────── */
        QScrollBar:vertical   {{ background:{bg}; width:8px; border:none; margin:0; }}
        QScrollBar:horizontal {{ background:{bg}; height:8px; border:none; margin:0; }}
        QScrollBar::handle:vertical   {{ background:{bdr}; border-radius:3px; min-height:20px; }}
        QScrollBar::handle:horizontal {{ background:{bdr}; border-radius:3px; min-width:20px; }}
        QScrollBar::handle:vertical:hover   {{ background:{bdr_a}; }}
        QScrollBar::handle:horizontal:hover {{ background:{bdr_a}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height:0; width:0; border:none; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}

        /* ── Tooltips ────────────────────────────────────────────── */
        QToolTip {{ background:{bg}; color:{txt}; border:1px solid {pri};
                   padding:5px 8px; border-radius:4px; opacity:230; }}

        /* ── Dialogs & generic containers ───────────────────────── */
        QDialog  {{ background:{bg}; }}
        QGroupBox {{
            border:1px solid {bdr}; border-radius:6px;
            margin-top:14px; padding-top:10px; color:{med}; font-weight:600;
        }}
        QGroupBox::title {{
            subcontrol-origin:margin; subcontrol-position:top left;
            left:10px; top:3px; color:{med};
        }}

        /* ── Text inputs ─────────────────────────────────────────── */
        QLineEdit {{
            background:{panel}; color:{txt}; border:1px solid {bdr};
            border-radius:5px; padding:5px 10px;
            selection-background-color:{bdr_a}; selection-color:{txt};
        }}
        QLineEdit:focus  {{ border:1px solid {pri}; }}
        QLineEdit:hover  {{ border:1px solid {bdr_a}; }}
        QTextEdit, QPlainTextEdit {{
            background:{panel}; color:{txt}; border:1px solid {bdr};
            border-radius:5px; padding:4px;
            selection-background-color:{bdr_a}; selection-color:{txt};
        }}
        QTextEdit:focus, QPlainTextEdit:focus {{ border:1px solid {pri}; }}

        /* ── Combo boxes ─────────────────────────────────────────── */
        QComboBox {{
            background:{panel}; color:{txt}; border:1px solid {bdr};
            border-radius:5px; padding:4px 8px; min-height:24px;
        }}
        QComboBox:hover  {{ border:1px solid {bdr_a}; }}
        QComboBox:focus  {{ border:1px solid {pri}; }}
        QComboBox::drop-down {{ border:none; width:20px; }}
        QComboBox::down-arrow {{ border:none; image:none; width:0; height:0; }}
        QComboBox QAbstractItemView {{
            background:{panel}; color:{txt}; border:1px solid {bdr};
            selection-background-color:{bdr_a}; outline:none;
        }}

        /* ── Spin boxes ──────────────────────────────────────────── */
        QSpinBox, QDoubleSpinBox {{
            background:{panel}; color:{txt}; border:1px solid {bdr};
            border-radius:5px; padding:3px 8px;
        }}
        QSpinBox:focus, QDoubleSpinBox:focus {{ border:1px solid {pri}; }}
        QSpinBox::up-button, QSpinBox::down-button,
        QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
            background:{bdr}; border:none; width:16px;
        }}

        /* ── Check boxes ─────────────────────────────────────────── */
        QCheckBox {{ color:{txt}; spacing:7px; background:transparent; }}
        QCheckBox::indicator {{
            width:16px; height:16px; border:1px solid {bdr_a};
            border-radius:4px; background:{panel};
        }}
        QCheckBox::indicator:checked  {{ background:{pri}; border:1px solid {pri}; }}
        QCheckBox::indicator:hover    {{ border:1px solid {pri}; }}

        /* ── Radio buttons ───────────────────────────────────────── */
        QRadioButton {{ color:{txt}; spacing:7px; background:transparent; }}
        QRadioButton::indicator {{
            width:14px; height:14px; border:1px solid {bdr_a};
            border-radius:7px; background:{panel};
        }}
        QRadioButton::indicator:checked {{ background:{pri}; border:2px solid {pri}; }}

        /* ── Sliders ─────────────────────────────────────────────── */
        QSlider::groove:horizontal {{
            background:{bdr}; height:4px; border-radius:2px; border:none;
        }}
        QSlider::handle:horizontal {{
            background:{pri}; width:14px; height:14px;
            border-radius:7px; margin:-5px 0; border:none;
        }}
        QSlider::handle:horizontal:hover {{ background:{bdr_a}; }}
        QSlider::sub-page:horizontal     {{ background:{pri}; border-radius:2px; opacity:80; }}

        /* ── Tab widget ──────────────────────────────────────────── */
        QTabWidget::pane {{
            background:{panel}; border:1px solid {bdr}; border-radius:4px;
        }}
        QTabBar::tab {{
            background:{bg}; color:{dim}; padding:7px 16px;
            border:1px solid {bdr}; border-bottom:none;
            border-radius:4px 4px 0 0; margin-right:2px;
        }}
        QTabBar::tab:selected {{
            background:{panel}; color:{txt}; border-bottom:1px solid {panel};
        }}
        QTabBar::tab:hover {{ color:{txt}; }}

        /* ── Progress bars ───────────────────────────────────────── */
        QProgressBar {{
            background:{panel}; border:1px solid {bdr}; border-radius:4px;
            color:transparent; height:6px;
        }}
        QProgressBar::chunk {{ background:{pri}; border-radius:3px; }}

        /* ── Scroll areas ────────────────────────────────────────── */
        QScrollArea {{ background:{bg}; border:none; }}
        QScrollArea > QWidget > QWidget {{ background:{bg}; }}

        /* ── Labels (fallback — won't override explicit setStyleSheet) */
        QLabel {{ color:{txt}; background:transparent; }}

        /* ── Menu bar / menus ────────────────────────────────────── */
        QMenuBar {{ background:{bg}; color:{txt}; }}
        QMenuBar::item:selected {{ background:{bdr}; }}
        QMenu {{
            background:{panel}; color:{txt}; border:1px solid {bdr};
            border-radius:4px;
        }}
        QMenu::item:selected {{ background:{bdr_a}; color:{txt}; }}
        QMenu::separator {{ height:1px; background:{bdr}; margin:4px 0; }}

        /* ── Message boxes ───────────────────────────────────────── */
        QMessageBox {{ background:{bg}; color:{txt}; }}
        QMessageBox QLabel {{ color:{txt}; }}
    """)
    # Rebuild ParticleOrb neutral-state colors from new theme
    try:
        _refresh_orb_colors()
    except Exception:
        pass
    # Force every visible widget to repaint (picks up new C.* attribute values)
    try:
        for w in app.allWidgets():
            try:
                w.update()
            except Exception:
                pass
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
# COLORS  (no gradients anywhere)
# ═══════════════════════════════════════════════════════════
class C:
    BG       = "#050c14"
    GRID     = "#0a1620"
    PANEL    = "#070f18"
    BORDER   = "#0d2540"
    BORDER_A = "#1a5070"
    PRI      = "#00d4ff"
    PRI_DIM  = "#005f77"
    PRI_GHO  = "#001820"
    ACC      = "#ff6600"
    ACC2     = "#ffcc00"
    GREEN    = "#00ff88"
    GREEN_D  = "#00aa55"
    RED      = "#ff3355"
    PURPLE   = "#7030ff"
    PINK     = "#ff38c8"
    TEXT     = "#7aeeff"
    TEXT_DIM = "#2e6070"
    TEXT_MED = "#4aaccf"
    WHITE    = "#ffffff"
    DARK     = "#030a10"
    MUTED_C  = "#ff3366"
    HDR_BG   = "#000000"   # Widget header — pure black, no gradient

# Apply saved theme immediately (mutates C attrs before any widget is built)
_load_theme()


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h)
    c.setAlpha(a)
    return c


# ═══════════════════════════════════════════════════════════
# PARTICLE
# ═══════════════════════════════════════════════════════════
class Particle:
    TRAIL_LEN = 14

    def __init__(self, x: float, y: float, idx: int):
        self.x     = x
        self.y     = y
        self.tx    = x
        self.ty    = y
        self.vx    = 0.0
        self.vy    = 0.0
        self.idx   = idx
        self.size  = random.uniform(1.0, 2.8)
        self.phase = random.uniform(0.0, math.pi * 2)
        self.speed = random.uniform(0.12, 0.28)
        self.trail: deque[tuple[float, float]] = deque(maxlen=self.TRAIL_LEN)

    def update(self, tick: int, noise: float = 1.5):
        nx = math.sin(tick * 0.017 + self.phase) * noise
        ny = math.cos(tick * 0.013 + self.phase * 1.37) * noise
        dx = (self.tx + nx) - self.x
        dy = (self.ty + ny) - self.y
        self.vx = self.vx * 0.86 + dx * self.speed * 0.12
        self.vy = self.vy * 0.86 + dy * self.speed * 0.12
        self.trail.append((self.x, self.y))
        self.x += self.vx
        self.y += self.vy


# ── State → RGB color ──────────────────────────────────────
# NOTE: LISTENING / IDLE / INITIATING / SPEAKING / BREATHING are rebuilt
# automatically from the active theme (C.PRI) via _refresh_orb_colors().
# Identity states (MUSIC, GAMING, ALERT…) keep fixed recognisable hues.
_STATE_RGB = {
    "LISTENING":   (0,   212, 255),   # ← theme-overwritten at startup
    "IDLE":        (0,   180, 255),   # ← theme-overwritten
    "INITIATING":  (0,   100, 180),   # ← theme-overwritten
    "THINKING":    (60,  130, 255),
    "SPEAKING":    (120, 240, 255),   # ← theme-overwritten
    "PROCESSING":  (130,  70, 255),
    "MUTED":       (40,   60,  80),
    "MUSIC":       (255,  45, 200),
    "PLAYING":     (255,  45, 200),
    "GAMING":      (255,  75,  20),
    "GAME":        (255,  75,  20),
    "WORK":        (255, 200,   0),
    "WORKING":     (255, 200,   0),
    "ALERT":       (255,  60,  60),
    "SUCCESS":     (0,   255, 136),
    "SEARCHING":   (80,  200, 255),
    "LOADING":     (40,  120, 255),
    "BREATHING":   (0,   212, 255),   # ← theme-overwritten
}


def _refresh_orb_colors():
    """Rebuild _STATE_RGB neutral states from the current theme (C.PRI / C.PRI_DIM).
    Called after every theme change so the ParticleOrb picks up new colors
    on its next tick without any widget recreation.
    """
    def _h(hex_str: str) -> tuple[int, int, int]:
        h = hex_str.lstrip("#")
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except Exception:
            return (0, 212, 255)

    pr, pg, pb = _h(C.PRI)
    dr, dg, db = _h(C.PRI_DIM)
    # Lerp helpers
    def _dim(v: int, f: float) -> int:
        return max(0, min(255, int(v * f)))

    _STATE_RGB.update({
        "LISTENING":  (pr, pg, pb),
        "IDLE":       (_dim(pr, 0.84), _dim(pg, 0.84), _dim(pb, 0.84)),
        "INITIATING": (dr, dg, db),
        "SPEAKING":   (min(255, pr + 40), min(255, pg + 20), min(255, pb)),
        "BREATHING":  (pr, pg, pb),
    })
_DYNAMIC = {
    "THINKING", "SPEAKING", "PROCESSING", "MUSIC", "PLAYING",
    "GAMING", "GAME", "WORK", "WORKING", "SEARCHING", "LOADING",
    "ALERT", "BREATHING",
}


# ═══════════════════════════════════════════════════════════
# PARTICLE ORB  — interactive neural network
# ═══════════════════════════════════════════════════════════
class ParticleOrb(QWidget):
    """Full-screen morphing particle intelligence sphere.
    Left-click repels particles, right-click/drag attracts them."""

    N               = 150
    _MORPH_DURATION = 25   # ticks for smooth formation morphing

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(80, 80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

        self._state   = "INITIATING"
        self._tick    = 0
        self._audio   = 0.0
        self._blink   = True
        self._btick   = 0
        self._cx      = 0.0
        self._cy      = 0.0
        self._R       = 0.0
        self._particles: list[Particle] = []
        self._static_tgts: list[tuple] | None = None
        self._prev_tgts:   list[tuple] | None = None
        self._transition_ticks = 0
        self.speaking = False

        # Smooth color interpolation between states
        self._cur_r   = 0.0
        self._cur_g   = 212.0
        self._cur_b   = 255.0
        self._col_spd = 0.15   # interpolation speed per tick

        # Mouse interaction
        self._mx      = 0.0
        self._my      = 0.0
        self._mforce  = 0.0    # decays naturally
        self._mattract = False

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)   # ~60fps active, drops to ~30fps when idle

    def _ensure(self):
        W, H = self.width(), self.height()
        if W < 20 or H < 20:
            return          # window minimized — skip
        self._cx = W / 2.0
        self._cy = H / 2.0
        self._R  = min(W, H) * 0.38
        if not self._particles:
            for i in range(self.N):
                a = random.uniform(0, math.pi * 2)
                r = random.uniform(0, self._R * 0.08)
                self._particles.append(
                    Particle(self._cx + r * math.cos(a),
                             self._cy + r * math.sin(a), i)
                )

    # ── Mouse interaction ────────────────────────────────
    def mousePressEvent(self, event: QMouseEvent):
        pos = event.position()
        self._mx = pos.x()
        self._my = pos.y()
        self._mforce = 1.0
        self._mattract = (event.button() == Qt.MouseButton.RightButton)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position()
        self._mx = pos.x()
        self._my = pos.y()
        if event.buttons() & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton):
            self._mforce = min(1.0, self._mforce + 0.08)
            self._mattract = bool(event.buttons() & Qt.MouseButton.RightButton)

    def mouseReleaseEvent(self, event: QMouseEvent):
        pass   # force decays naturally

    # ── Formations ──────────────────────────────────────
    def _f_sphere(self) -> list[tuple]:
        g = math.pi * (3 - math.sqrt(5))
        pts = []
        for i in range(self.N):
            y  = 1 - (i / (self.N - 1)) * 2
            r  = math.sqrt(max(0.0, 1 - y * y))
            th = g * i
            x  = r * math.cos(th)
            z  = r * math.sin(th)
            d  = (z + 1.65) / 2.65
            pts.append((self._cx + x * self._R * d,
                        self._cy + y * self._R * 0.88 * d))
        return pts

    def _f_vortex(self) -> list[tuple]:
        """Thinking: triple-arm inward spiral."""
        rot = self._tick * 0.042
        pts = []
        for i in range(self.N):
            t   = i / self.N
            arm = i % 3
            a   = t * 10 * math.pi + rot + arm * (math.pi * 2 / 3)
            r   = self._R * (0.05 + 0.92 * (t ** 0.5)) * 0.88
            pts.append((self._cx + r * math.cos(a),
                        self._cy + r * math.sin(a) * 0.62))
        return pts

    def _f_rings(self) -> list[tuple]:
        """Speaking: audio-reactive expanding rings."""
        RINGS = 7
        per   = max(1, self.N // RINGS)
        al    = self._audio
        rot   = self._tick * 0.008
        pulse = math.sin(self._tick * 0.05) * 0.12
        pts   = []
        for i in range(self.N):
            ring = min(i // per, RINGS - 1)
            pos  = i % per
            a    = (pos / per) * 2 * math.pi + ring * 0.6 + rot
            r    = self._R * (ring + 1) / RINGS * (0.65 + 0.38 * al + pulse)
            pts.append((self._cx + r * math.cos(a),
                        self._cy + r * math.sin(a) * 0.78))
        return pts

    def _f_helix(self) -> list[tuple]:
        """Processing: DNA triple helix."""
        rot = self._tick * 0.022
        pts = []
        for i in range(self.N):
            t     = i / self.N
            y     = (t - 0.5) * self._R * 2.1
            phase = t * 6 * math.pi + rot
            strand = i % 3
            s     = strand * (math.pi * 2 / 3)
            x     = self._R * 0.35 * math.cos(phase + s)
            pts.append((self._cx + x, self._cy + y))
        return pts

    def _f_collapse(self) -> list[tuple]:
        """Muted: compressed sphere."""
        g   = math.pi * (3 - math.sqrt(5))
        pts = []
        for i in range(self.N):
            a = g * i
            r = self._R * 0.07 * (i / self.N)
            pts.append((self._cx + r * math.cos(a),
                        self._cy + r * math.sin(a)))
        return pts

    def _f_grid(self) -> list[tuple]:
        """Work: hexagonal lattice."""
        COLS = int(math.sqrt(self.N * 1.7)) + 1
        ROWS = (self.N + COLS - 1) // COLS
        gw   = self._R * 1.75 / COLS
        gh   = gw * 0.88
        ox   = self._cx - COLS * gw / 2
        oy   = self._cy - ROWS * gh / 2
        pts  = []
        for i in range(self.N):
            row = i // COLS
            col = i % COLS
            hx  = (row % 2) * gw * 0.5
            pts.append((ox + col * gw + hx, oy + row * gh))
        return pts

    def _f_bars(self) -> list[tuple]:
        """Music: bouncing equalizer bars."""
        BARS = 14
        per  = max(1, self.N // BARS)
        bw   = self._R * 1.75 / BARS
        pts  = []
        for i in range(self.N):
            b   = min(i // per, BARS - 1)
            pos = i % per
            x   = self._cx + (b - BARS / 2 + 0.5) * bw
            h   = self._R * 0.88 * abs(
                math.sin(self._tick * 0.07 + b * 0.8))
            y   = self._cy + h * (1 - 2 * pos / per)
            pts.append((x, y))
        return pts

    def _f_star(self) -> list[tuple]:
        """Gaming: aggressive 8-pointed burst."""
        ARMS = 8
        per  = max(1, self.N // ARMS)
        rot  = self._tick * 0.022
        pts  = []
        for i in range(self.N):
            arm = i // per
            pos = i % per
            t   = pos / per
            a   = (arm / ARMS) * 2 * math.pi + rot + math.sin(t * 6) * 0.28
            r   = self._R * (0.08 + 0.92 * t)
            pts.append((self._cx + r * math.cos(a),
                        self._cy + r * math.sin(a) * 0.88))
        return pts

    def _f_nebula(self) -> list[tuple]:
        """Initiating: expanding nebula."""
        g   = math.pi * (3 - math.sqrt(5))
        pts = []
        for i in range(self.N):
            t     = i / self.N
            a     = g * i
            r     = self._R * (0.06 + 0.74 * (math.sin(t * math.pi)) ** 1.5)
            swirl = t * 4 * math.pi * math.sin(self._tick * 0.014)
            pts.append((self._cx + r * math.cos(a + swirl),
                        self._cy + r * math.sin(a + swirl) * 0.85))
        return pts

    def _f_pulse(self) -> list[tuple]:
        """Alert: urgent pulsing sphere."""
        g    = math.pi * (3 - math.sqrt(5))
        amp  = 0.85 + 0.22 * math.sin(self._tick * 0.20)
        pts  = []
        for i in range(self.N):
            y  = 1 - (i / (self.N - 1)) * 2
            r  = math.sqrt(max(0.0, 1 - y * y))
            th = g * i
            x  = r * math.cos(th)
            z  = r * math.sin(th)
            d  = (z + 1.65) / 2.65
            pts.append((self._cx + x * self._R * d * amp,
                        self._cy + y * self._R * 0.88 * d * amp))
        return pts

    def _f_wave(self) -> list[tuple]:
        """Searching: flowing wave scan."""
        LINES = 9
        per   = max(1, self.N // LINES)
        scan  = (self._tick * 0.04) % (math.pi * 2)
        pts   = []
        for i in range(self.N):
            line = min(i // per, LINES - 1)
            pos  = i % per
            t    = pos / per
            x    = self._cx + (t - 0.5) * self._R * 1.8
            y    = self._cy + (line - LINES / 2 + 0.5) * self._R * 0.22
            y   += math.sin(t * math.pi * 3 + scan + line * 0.7) * self._R * 0.12
            pts.append((x, y))
        return pts

    def _f_orbit(self) -> list[tuple]:
        """Loading: multi-plane orbital rings."""
        RINGS = 5
        per   = max(1, self.N // RINGS)
        pts   = []
        for i in range(self.N):
            ring = min(i // per, RINGS - 1)
            pos  = i % per
            spd  = 0.025 + ring * 0.012
            a    = (pos / per) * 2 * math.pi + self._tick * spd
            r    = self._R * (0.22 + ring * 0.16)
            tilt = 0.25 + ring * 0.18
            pts.append((self._cx + r * math.cos(a),
                        self._cy + r * math.sin(a) * tilt))
        return pts

    def _f_success(self) -> list[tuple]:
        """Success: blooming flower."""
        PETALS = 8
        per    = max(1, self.N // PETALS)
        rot    = self._tick * 0.010
        pts    = []
        for i in range(self.N):
            pet = min(i // per, PETALS - 1)
            pos = i % per
            t   = pos / per
            a   = (pet / PETALS) * 2 * math.pi + rot
            r   = self._R * 0.85 * math.sin(t * math.pi)
            pts.append((self._cx + r * math.cos(a),
                        self._cy + r * math.sin(a) * 0.9))
        return pts

    # ── NEW FORMATIONS ───────────────────────────────────
    def _f_tornado(self) -> list[tuple]:
        """Tornado: tightening upward cyclone."""
        rot = self._tick * 0.055
        pts = []
        for i in range(self.N):
            t = i / self.N
            y = (t - 0.5) * self._R * 2.0
            taper = 0.08 + (1 - t) * 0.90   # wide at bottom, tight at top
            a = t * 14 * math.pi + rot
            r = self._R * taper
            pts.append((self._cx + r * math.cos(a),
                        self._cy + y))
        return pts

    def _f_crystallize(self) -> list[tuple]:
        """Crystallize: geometric snowflake arms."""
        ARMS = 6
        per  = max(1, self.N // ARMS)
        rot  = self._tick * 0.005
        pts  = []
        for i in range(self.N):
            arm = i // per
            pos = i % per
            t   = pos / per
            a   = (arm / ARMS) * 2 * math.pi + rot
            # Sub-branches
            sub = math.sin(t * math.pi * 4) * self._R * 0.18
            r   = self._R * t * 0.92
            bx  = self._cx + r * math.cos(a) + sub * math.cos(a + math.pi/2)
            by  = self._cy + r * math.sin(a) + sub * math.sin(a + math.pi/2)
            pts.append((bx, by))
        return pts

    def _f_breathing(self) -> list[tuple]:
        """Breathing: slow inhale/exhale sphere."""
        g     = math.pi * (3 - math.sqrt(5))
        scale = 0.65 + 0.35 * (0.5 + 0.5 * math.sin(self._tick * 0.025))
        pts   = []
        for i in range(self.N):
            y  = 1 - (i / (self.N - 1)) * 2
            r  = math.sqrt(max(0.0, 1 - y * y))
            th = g * i
            x  = r * math.cos(th)
            z  = r * math.sin(th)
            d  = (z + 1.65) / 2.65
            pts.append((self._cx + x * self._R * d * scale,
                        self._cy + y * self._R * 0.88 * d * scale))
        return pts

    def _f_comet(self) -> list[tuple]:
        """Idle: single comet sweeping orbit."""
        rot  = self._tick * 0.018
        TAIL = self.N
        pts  = []
        for i in range(TAIL):
            t   = i / TAIL
            a   = rot - t * 1.8
            r   = self._R * (0.50 + 0.40 * math.cos(t * math.pi))
            ell = 0.55
            pts.append((self._cx + r * math.cos(a),
                        self._cy + r * math.sin(a) * ell))
        return pts

    def _f_matrix(self) -> list[tuple]:
        """Processing alt: falling columns."""
        COLS = 12
        per  = max(1, self.N // COLS)
        cw   = self._R * 1.80 / COLS
        pts  = []
        for i in range(self.N):
            col  = i // per
            pos  = i % per
            x    = self._cx + (col - COLS / 2 + 0.5) * cw
            spd  = 0.04 + (col % 3) * 0.015
            y    = self._cy + self._R * ((pos / per + self._tick * spd) % 2 - 1)
            pts.append((x, y))
        return pts

    def _targets(self) -> list[tuple]:
        s = self._state
        if   s == "THINKING":               return self._f_vortex()
        elif s == "SPEAKING":               return self._f_rings()
        elif s == "PROCESSING":             return self._f_helix()
        elif s == "MUTED":                  return self._f_collapse()
        elif s in ("WORK", "WORKING"):      return self._f_grid()
        elif s in ("MUSIC", "PLAYING"):     return self._f_bars()
        elif s in ("GAMING", "GAME"):       return self._f_star()
        elif s == "INITIATING":             return self._f_nebula()
        elif s == "ALERT":                  return self._f_pulse()
        elif s == "SEARCHING":              return self._f_wave()
        elif s == "LOADING":                return self._f_orbit()
        elif s == "SUCCESS":                return self._f_success()
        elif s == "IDLE":                   return self._f_comet()
        elif s == "BREATHING":              return self._f_breathing()
        else:                               return self._f_sphere()   # LISTENING

    def _targets_morphed(self) -> list[tuple]:
        """Smoothly interpolate between previous and current formation."""
        new_tgts = self._targets()
        if (self._transition_ticks > 0
                and self._prev_tgts
                and len(self._prev_tgts) == len(new_tgts)):
            self._transition_ticks -= 1
            t = 1.0 - (self._transition_ticks / self._MORPH_DURATION)
            # Smoothstep easing
            t = t * t * (3.0 - 2.0 * t)
            return [
                (p[0] * (1 - t) + n[0] * t,
                 p[1] * (1 - t) + n[1] * t)
                for p, n in zip(self._prev_tgts, new_tgts)
            ]
        return new_tgts

    def _step(self):
        if not self.isVisible():
            return
        if self.width() < 20 or self.height() < 20:
            return          # minimized — don't render
        self._ensure()
        self._tick += 1

        # Smooth colour transition towards current-state target
        tr, tg, tb = _STATE_RGB.get(self._state, (0, 212, 255))
        self._cur_r += (tr - self._cur_r) * self._col_spd
        self._cur_g += (tg - self._cur_g) * self._col_spd
        self._cur_b += (tb - self._cur_b) * self._col_spd

        self._btick += 1
        if self._btick >= 26:
            self._blink = not self._blink
            self._btick = 0

        # Compute targets with morph interpolation
        if self._state in _DYNAMIC or self._transition_ticks > 0:
            tgts = self._targets_morphed()
        else:
            if self._static_tgts is None:
                self._static_tgts = self._targets()
            tgts = self._static_tgts

        for i, p in enumerate(self._particles):
            if i < len(tgts):
                p.tx, p.ty = tgts[i]

        noise = {
            "THINKING":   0.5,  "SPEAKING": 1.0 + self._audio * 3.5,
            "LISTENING":  2.6,  "MUTED":    0.10,
            "PROCESSING": 0.40, "GAMING":   1.8,  "GAME": 1.8,
            "MUSIC":      0.85, "PLAYING":  0.85,
            "WORK":       0.22, "WORKING":  0.22,
            "INITIATING": 1.4,  "ALERT":    2.0,
            "SEARCHING":  1.0,  "LOADING":  0.50,
            "SUCCESS":    0.9,  "IDLE":     0.4,
            "BREATHING":  0.3,
        }.get(self._state, 2.0)

        # Apply mouse force (repel / attract)
        if self._mforce > 0.01:
            self._mforce *= 0.94
            for p in self._particles:
                dx = self._mx - p.x
                dy = self._my - p.y
                d  = math.hypot(dx, dy) + 1.0
                f  = self._mforce * 90.0 / (d * d * 0.006 + 60.0)
                if self._mattract:
                    p.vx += (dx / d) * f
                    p.vy += (dy / d) * f
                else:
                    p.vx -= (dx / d) * f
                    p.vy -= (dy / d) * f

        for p in self._particles:
            p.update(self._tick, noise)

        self.update()

        # Adaptive FPS: 60fps when active, 30fps when idle
        is_dynamic = self._state in _DYNAMIC or self._mforce > 0.01 or self._transition_ticks > 0
        target_ms = 16 if is_dynamic else 33
        if self._tmr.interval() != target_ms:
            self._tmr.setInterval(target_ms)

    def set_state(self, state: str):
        new = state.upper()
        if new == self._state:
            return
        # Capture current particle positions as morph source
        self._prev_tgts = [(p.x, p.y) for p in self._particles] if self._particles else None
        self._prev_state = self._state
        self._state = new
        self._static_tgts = None
        self._transition_ticks = self._MORPH_DURATION

    def set_audio(self, level: float):
        self._audio = max(0.0, min(1.0, level))

    def _rgb(self) -> tuple[int, int, int]:
        return (int(self._cur_r), int(self._cur_g), int(self._cur_b))

    def _label_txt(self) -> str:
        mp = {
            "LISTENING":   ("●", "ESCUCHANDO"),
            "THINKING":    ("◈", "PENSANDO"),
            "SPEAKING":    ("◉", "HABLANDO"),
            "PROCESSING":  ("▷", "PROCESANDO"),
            "MUTED":       ("⊘", "SILENCIADO"),
            "INITIATING":  ("◈", "INICIANDO"),
            "MUSIC":       ("♪", "MÚSICA"),
            "PLAYING":     ("♪", "MÚSICA"),
            "GAMING":      ("▶", "JUEGO"),
            "GAME":        ("▶", "JUEGO"),
            "WORK":        ("◆", "TRABAJO"),
            "WORKING":     ("◆", "TRABAJO"),
            "ALERT":       ("⚠", "ALERTA"),
            "SEARCHING":   ("◎", "BUSCANDO"),
            "LOADING":     ("○", "CARGANDO"),
            "SUCCESS":     ("✓", "LISTO"),
            "IDLE":        ("○", "EN ESPERA"),
            "BREATHING":   ("●", "DESCANSANDO"),
        }
        sym, lbl = mp.get(self._state, ("●", self._state))
        sym = sym if self._blink else "○"
        return f"{sym}  {lbl}"

    def paintEvent(self, _):
        if not self._particles:
            return

        p      = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H   = self.width(), self.height()
        cx, cy = self._cx or W / 2, self._cy or H / 2
        R      = self._R or min(W, H) * 0.38
        cr, cg, cb = self._rgb()
        al = self._audio

        # Background
        p.fillRect(self.rect(), QColor(5, 12, 20))

        # Center glow
        gr = R * (1.20 + al * 0.30)
        glow = QRadialGradient(cx, cy, gr)
        glow.setColorAt(0.0, QColor(cr, cg, cb, int(22 + al * 38)))
        glow.setColorAt(0.55, QColor(cr, cg, cb, int(7 + al * 14)))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - gr, cy - gr, gr * 2, gr * 2))

        # Connection lines — shorter range when idle to reduce draw calls
        state = self._state
        MAX_D = 82.0 if state in _DYNAMIC else 55.0
        step  = 1 if state in _DYNAMIC else 2   # skip every other particle when idle
        parts = self._particles
        for i in range(0, len(parts), step):
            pi = parts[i]
            for j in range(i + 1, min(i + 20, len(parts))):
                pj = parts[j]
                d  = math.hypot(pi.x - pj.x, pi.y - pj.y)
                if d < MAX_D:
                    t_  = 1 - d / MAX_D
                    a_  = int(t_ ** 1.7 * 72)
                    pw  = 0.22 + t_ * 0.9
                    p.setPen(QPen(QColor(cr, cg, cb, a_), pw))
                    p.drawLine(QPointF(pi.x, pi.y), QPointF(pj.x, pj.y))

        # Trails & cores
        p.setPen(Qt.PenStyle.NoPen)
        for part in parts:
            trail = list(part.trail)
            n = len(trail)
            for k in range(1, n):
                t_  = k / n
                a_  = int(t_ ** 1.3 * 100)
                pw  = 0.22 + t_ * 1.7
                p.setPen(QPen(QColor(cr, cg, cb, a_), pw))
                p.drawLine(QPointF(trail[k - 1][0], trail[k - 1][1]),
                           QPointF(trail[k][0],     trail[k][1]))

            s  = part.size * (1.0 + al * 0.5)
            rg = QRadialGradient(part.x, part.y, s * 2.6)
            rg.setColorAt(0.0, QColor(215, 248, 255, 230))
            rg.setColorAt(0.35, QColor(cr, cg, cb, 190))
            rg.setColorAt(1.0,  QColor(cr, cg, cb, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(rg))
            p.drawEllipse(QPointF(part.x, part.y), s * 2.6, s * 2.6)

        # Waveform bar (only at normal size)
        if W > 180:
            wy  = cy + R * 0.88
            NB  = 28
            bw  = 7
            wx0 = (W - NB * bw) / 2
            for bi in range(NB):
                if self._state == "MUTED":
                    h_, col_ = 2, QColor(50, 70, 90, 70)
                elif self._state == "SPEAKING":
                    env = abs(math.sin(self._tick * 0.065))
                    h_  = max(2, int(3 + (9 + al * 20) * abs(
                        math.sin(self._tick * 0.10 + bi * 0.52)) * env))
                    col_ = QColor(cr, cg, cb, 210 if h_ > 9 else 130)
                elif self._state in ("MUSIC", "PLAYING"):
                    h_   = max(2, int(5 + 14 * abs(math.sin(self._tick * 0.09 + bi * 0.62))))
                    col_ = QColor(cr, cg, cb, 210)
                elif self._state in ("THINKING", "PROCESSING", "LOADING"):
                    h_   = max(2, int(2 + 5 * abs(math.sin(self._tick * 0.05 + bi * 0.48))))
                    col_ = QColor(cr, cg, cb, 140)
                else:
                    h_   = max(1, int(2 + 1.5 * math.sin(self._tick * 0.04 + bi * 0.48)))
                    col_ = QColor(cr, cg, cb, 80)
                p.fillRect(QRectF(wx0 + bi * bw, wy + 18 - h_, bw - 2, h_), col_)

        # State label
        lbl = self._label_txt()
        ly  = cy + R * 0.93
        if W > 130:
            font = QFont("Segoe UI", 9 if W > 180 else 7, QFont.Weight.Bold)
            p.setFont(font)
            p.setPen(QPen(QColor(0, 0, 0, 130), 1))
            p.drawText(QRectF(1, ly + 1, W, 26), Qt.AlignmentFlag.AlignCenter, lbl)
            p.setPen(QPen(QColor(cr, cg, cb, 230), 1))
            p.drawText(QRectF(0, ly, W, 26), Qt.AlignmentFlag.AlignCenter, lbl)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._cx = self.width() / 2.0
        self._cy = self.height() / 2.0
        self._R  = min(self.width(), self.height()) * 0.38
        self._static_tgts = None


# ═══════════════════════════════════════════════════════════
# DRAGGABLE WIDGET BASE  — pure black header, white text
# ═══════════════════════════════════════════════════════════
class DraggableWidget(QFrame):
    closed = pyqtSignal(object)

    def __init__(self, title: str, icon: str, accent: str = C.PRI,
                 closeable: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("DraggableWidget")
        self._accent   = accent
        self._drag_pos = None

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.setGraphicsEffect(shadow)

        # Widget body — no gradient
        self.setStyleSheet(f"""
            QFrame#DraggableWidget {{
                background: #070f18;
                border: 1px solid {C.BORDER};
                border-radius: 20px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header — pure black, white text, NO gradient
        self._hdr = QWidget()
        self._hdr.setFixedHeight(40)
        self._hdr.setCursor(Qt.CursorShape.SizeAllCursor)
        self._hdr.setStyleSheet(f"""
            background: {C.HDR_BG};
            border-top-left-radius: 20px;
            border-top-right-radius: 20px;
            border-bottom: 1px solid {C.BORDER};
        """)
        hl = QHBoxLayout(self._hdr)
        hl.setContentsMargins(14, 0, 10, 0)
        hl.setSpacing(7)

        dot = QLabel("●")
        dot.setFont(QFont("Segoe UI", 7))
        dot.setStyleSheet(f"color: {accent}; background: transparent; border: none;")
        hl.addWidget(dot)

        ico = QLabel(icon)
        ico.setFont(QFont("Segoe UI Emoji" if _OS == "Windows" else "Arial", 12))
        ico.setStyleSheet(f"color: {accent}; background: transparent; border: none;")
        hl.addWidget(ico)

        tl = QLabel(title)
        tl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        tl.setStyleSheet(
            "color: #ffffff; background: transparent; border: none; letter-spacing: 2px;"
        )
        hl.addWidget(tl)
        hl.addStretch()

        dh = QLabel("⠿")
        dh.setFont(QFont("Segoe UI", 10))
        dh.setStyleSheet("color: #555555; background: transparent; border: none;")
        hl.addWidget(dh)

        if closeable:
            cb = QPushButton("✕")
            cb.setFixedSize(20, 20)
            cb.setFont(QFont("Segoe UI", 8))
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: #555555;
                    border: none; border-radius: 10px;
                }}
                QPushButton:hover {{
                    color: {C.RED}; background: rgba(255,51,85,0.18);
                }}
            """)
            cb.clicked.connect(self._on_close)
            hl.addWidget(cb)

        root.addWidget(self._hdr)

        self._body = QVBoxLayout()
        self._body.setContentsMargins(10, 6, 10, 10)
        self._body.setSpacing(5)
        root.addLayout(self._body, stretch=1)

    def _on_close(self):
        self.hide()
        self.closed.emit(self)

    def mousePressEvent(self, event: QMouseEvent):
        if (event.button() == Qt.MouseButton.LeftButton
                and self._hdr.geometry().contains(event.pos())):
            gp = event.globalPosition()
            self._drag_pos = QPoint(int(gp.x()) - self.x(), int(gp.y()) - self.y())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            gp = event.globalPosition()
            nx = int(gp.x()) - self._drag_pos.x()
            ny = int(gp.y()) - self._drag_pos.y()
            if self.parent():
                nx = max(0, min(nx, self.parent().width()  - self.width()))
                ny = max(0, min(ny, self.parent().height() - self.height()))
            self.move(nx, ny)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def show_animated(self):
        self.show()
        self.raise_()
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(150)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def hide_animated(self):
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(120)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self.hide)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


# ═══════════════════════════════════════════════════════════
# METRIC BAR
# ═══════════════════════════════════════════════════════════
class MetricBar(QWidget):
    def __init__(self, label: str, unit: str = "%", color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label  = label
        self._unit   = unit
        self._color  = color
        self._value  = 0.0
        self._text   = "0"
        self._anim   = 0.0
        self.setFixedHeight(30)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tmr = QTimer(self)
        tmr.timeout.connect(self._animate)
        tmr.start(24)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text.replace("\n", " ").split()[0] if text else "0"

    def _animate(self):
        self._anim += (self._value - self._anim) * 0.18
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        v    = self._anim
        col  = qcol(C.RED) if v > 85 else qcol(C.ACC) if v > 65 else qcol(self._color)

        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 0, W * 0.55, 20),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._label)

        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.setPen(QPen(col, 1))
        p.drawText(QRectF(W * 0.40, 0, W * 0.60, 20),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   self._text)

        by, bh = 24, 3
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol("#060f1a", 180)))
        p.drawRoundedRect(QRectF(0, by, W, bh), 1.5, 1.5)

        fw = W * (v / 100.0)
        if fw > 0.5:
            p.setBrush(QBrush(col))
            p.drawRoundedRect(QRectF(0, by, fw, bh), 1.5, 1.5)


# ═══════════════════════════════════════════════════════════
# DASHBOARD WIDGETS
# ═══════════════════════════════════════════════════════════

class ClockWidget(DraggableWidget):
    def __init__(self, parent=None):
        super().__init__("RELOJ", "◷", C.PRI, closeable=True, parent=parent)
        self.resize(200, 130)

        self._time = QLabel("00:00:00")
        self._time.setFont(QFont("Consolas", 22, QFont.Weight.Bold))
        self._time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._body.addWidget(self._time)

        self._date = QLabel("")
        self._date.setFont(QFont("Segoe UI", 9))
        self._date.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._date.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._body.addWidget(self._date)

        tmr = QTimer(self)
        tmr.timeout.connect(self._tick)
        tmr.start(1000)
        self._tick()

    def _tick(self):
        now  = _dt.now(_BA_TZ)
        dias = ["LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM"]
        self._time.setText(now.strftime("%H:%M:%S"))
        self._date.setText(f"{dias[now.weekday()]}  {now.strftime('%d/%m/%Y')}")


class SystemWidget(DraggableWidget):
    def __init__(self, parent=None):
        super().__init__("SISTEMA", "⚡", C.GREEN, closeable=True, parent=parent)
        self.resize(250, 205)
        self._gauges: dict[str, MetricBar] = {}
        for label, unit, color in [
            ("CPU",  "%",    C.PRI),
            ("RAM",  "%",    C.GREEN),
            ("NET",  "MB/s", C.ACC2),
            ("GPU",  "%",    C.PURPLE),
            ("TEMP", "°C",   C.ACC),
        ]:
            g = MetricBar(label, unit, color)
            self._gauges[label] = g
            self._body.addWidget(g)

        self._last_net   = psutil.net_io_counters()
        self._last_net_t = time.time()
        tmr = QTimer(self)
        tmr.timeout.connect(self._update)
        tmr.start(2000)
        self._update()

    def _update(self):
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = max(now - self._last_net_t, 0.001)
        net = ((nc.bytes_sent - self._last_net.bytes_sent) +
               (nc.bytes_recv - self._last_net.bytes_recv)) / dt / (1024 * 1024)
        self._last_net   = nc
        self._last_net_t = now

        gpu, temp = -1.0, -1.0
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=1)
            if r.returncode == 0:
                gpu = float(r.stdout.strip().split("\n")[0])
        except Exception:
            pass
        try:
            temps = psutil.sensors_temperatures()
            for name in ["coretemp", "k10temp", "cpu_thermal", "acpitz"]:
                if name in temps and temps[name]:
                    temp = temps[name][0].current
                    break
        except Exception:
            pass

        self._gauges["CPU"].set_value(cpu, f"{cpu:.0f}%")
        self._gauges["RAM"].set_value(mem, f"{mem:.0f}%")
        self._gauges["NET"].set_value(min(net * 10, 100), f"{net:.1f}")
        self._gauges["GPU"].set_value(gpu if gpu >= 0 else 0, f"{gpu:.0f}%" if gpu >= 0 else "N/A")
        self._gauges["TEMP"].set_value(
            min(temp, 100) if temp >= 0 else 0,
            f"{temp:.0f}°" if temp >= 0 else "N/A")


class WeatherWidget(DraggableWidget):
    def __init__(self, parent=None):
        super().__init__("CLIMA", "🌡", C.ACC2, closeable=True, parent=parent)
        self.resize(340, 310)

        # City + icon row
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self._icon_lbl = QLabel("🌤")
        self._icon_lbl.setFont(QFont("Segoe UI Emoji" if _OS == "Windows" else "Arial", 52))
        self._icon_lbl.setStyleSheet("color: #ffcc00; background: transparent;")
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setFixedWidth(72)
        top_row.addWidget(self._icon_lbl)

        right_col = QVBoxLayout()
        right_col.setSpacing(1)

        self._city_lbl = QLabel("—")
        self._city_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._city_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; letter-spacing: 3px;")
        right_col.addWidget(self._city_lbl)

        self._temp_lbl = QLabel("—")
        self._temp_lbl.setFont(QFont("Consolas", 38, QFont.Weight.Bold))
        self._temp_lbl.setStyleSheet("color: #ffcc00; background: transparent;")
        right_col.addWidget(self._temp_lbl)

        self._desc_lbl = QLabel("Sin datos")
        self._desc_lbl.setFont(QFont("Segoe UI", 10))
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        right_col.addWidget(self._desc_lbl)

        top_row.addLayout(right_col, stretch=1)
        self._body.addLayout(top_row)

        # Details row: feels, humidity, wind
        details_row = QHBoxLayout()
        details_row.setSpacing(6)
        self._detail_chips: list[tuple[QLabel, QLabel]] = []
        for icon_ch, key in [("🌡", "Sensación"), ("💧", "Humedad"), ("💨", "Viento")]:
            chip = QFrame()
            chip.setStyleSheet(f"QFrame {{background: rgba(0,20,40,180); border: 1px solid {C.BORDER}; border-radius: 10px;}}")
            chip_lay = QVBoxLayout(chip)
            chip_lay.setContentsMargins(8, 5, 8, 5)
            chip_lay.setSpacing(1)
            val_lbl = QLabel("—")
            val_lbl.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            val_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub_lbl = QLabel(f"{icon_ch} {key}")
            sub_lbl.setFont(QFont("Segoe UI", 7))
            sub_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip_lay.addWidget(val_lbl)
            chip_lay.addWidget(sub_lbl)
            details_row.addWidget(chip, stretch=1)
            self._detail_chips.append((val_lbl, sub_lbl))
        self._body.addLayout(details_row)

        # Forecast row (up to 4 days)
        forecast_frame = QFrame()
        forecast_frame.setStyleSheet(f"QFrame {{background: rgba(0,15,30,160); border: 1px solid {C.BORDER}; border-radius: 10px;}}")
        forecast_lay = QHBoxLayout(forecast_frame)
        forecast_lay.setContentsMargins(8, 6, 8, 6)
        forecast_lay.setSpacing(0)
        self._forecast_cols: list[tuple[QLabel, QLabel, QLabel]] = []
        for _ in range(4):
            col_w = QWidget()
            col_w.setStyleSheet("background: transparent;")
            col_lay = QVBoxLayout(col_w)
            col_lay.setContentsMargins(2, 0, 2, 0)
            col_lay.setSpacing(1)
            day_lbl = QLabel("—")
            day_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            day_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            day_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ico_lbl = QLabel("—")
            ico_lbl.setFont(QFont("Segoe UI Emoji" if _OS == "Windows" else "Arial", 14))
            ico_lbl.setStyleSheet("color: #ffcc00; background: transparent;")
            ico_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tmp_lbl = QLabel("—")
            tmp_lbl.setFont(QFont("Consolas", 7))
            tmp_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            tmp_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col_lay.addWidget(day_lbl)
            col_lay.addWidget(ico_lbl)
            col_lay.addWidget(tmp_lbl)
            forecast_lay.addWidget(col_w, stretch=1)
            self._forecast_cols.append((day_lbl, ico_lbl, tmp_lbl))
        self._body.addWidget(forecast_frame)

        self._hint = QLabel("Di: 'dame el clima de Buenos Aires'")
        self._hint.setFont(QFont("Segoe UI", 8))
        self._hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; font-style: italic;")
        self._hint.setWordWrap(True)
        self._body.addWidget(self._hint)

    def update_weather(self, city: str, temp: str, desc: str, icon: str = "🌤",
                       feels: str = "", humid: str = "", wind: str = "",
                       forecast: str = ""):
        self._city_lbl.setText(city.upper())
        self._temp_lbl.setText(temp)
        self._desc_lbl.setText(desc)
        self._icon_lbl.setText(icon)
        self._hint.hide()

        # Detail chips
        vals = [feels or "—", humid or "—", wind or "—"]
        for i, (val_lbl, _) in enumerate(self._detail_chips):
            val_lbl.setText(vals[i] if i < len(vals) else "—")

        # Forecast  format: "Lun:☀22°/14°,Mar:⛅20°/13°,..."
        if forecast:
            parts = forecast.split(",")
            for i, (dl, il, tl) in enumerate(self._forecast_cols):
                if i < len(parts):
                    seg = parts[i].strip()
                    # parse "Lun:☀22°/14°"
                    if ":" in seg:
                        day_part, rest = seg.split(":", 1)
                        # icon is one emoji char(s), then temps
                        # Find the slash for max/min
                        slash = rest.rfind("/")
                        if slash > 0:
                            mn = rest[slash + 1:]
                            # icon + max = rest[:slash]
                            ico_max = rest[:slash]
                            # last numeric token is max, rest is icon
                            import re
                            nums = re.findall(r'-?\d+°?', ico_max)
                            if nums:
                                mx = nums[-1]
                                # icon is everything before the number
                                ico_part = ico_max[:ico_max.rfind(nums[-1])].strip()
                            else:
                                mx = "?"
                                ico_part = ico_max
                            dl.setText(day_part.strip())
                            il.setText(ico_part or "🌤")
                            tl.setText(f"{mx}/{mn}")
                        else:
                            dl.setText(day_part.strip())
                            il.setText("")
                            tl.setText(rest)
                    else:
                        dl.setText(seg)
                        il.setText("")
                        tl.setText("")
                else:
                    dl.setText(""); il.setText(""); tl.setText("")


class TodoWidget(DraggableWidget):
    def __init__(self, parent=None):
        super().__init__("TAREAS", "✓", C.GREEN, closeable=True, parent=parent)
        self.resize(300, 280)
        self._todos: list[dict] = self._load()

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 4px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_A}; border-radius: 2px; min-height: 16px;
            }}
        """)
        self._list_w = QWidget()
        self._list_w.setStyleSheet("background: transparent;")
        self._list_lay = QVBoxLayout(self._list_w)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(5)
        self._list_lay.addStretch()
        self._scroll.setWidget(self._list_w)
        self._body.addWidget(self._scroll, stretch=1)

        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self._inp = QLineEdit()
        self._inp.setPlaceholderText("Nueva tarea…")
        self._inp.setFont(QFont("Segoe UI", 9))
        self._inp.setFixedHeight(30)
        self._inp.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(0,20,35,180); color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 15px;
                padding: 0 10px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.GREEN}; }}
        """)
        self._inp.returnPressed.connect(self._add_from_input)
        add_row.addWidget(self._inp, stretch=1)
        add_btn = QPushButton("+")
        add_btn.setFixedSize(30, 30)
        add_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0,255,136,0.08); color: {C.GREEN};
                border: 1px solid {C.GREEN_D}; border-radius: 15px;
            }}
            QPushButton:hover {{ background: rgba(0,255,136,0.18); }}
        """)
        add_btn.clicked.connect(self._add_from_input)
        add_row.addWidget(add_btn)
        self._body.addLayout(add_row)
        self._refresh()

    def _load(self) -> list[dict]:
        try:
            TODO_FILE.parent.mkdir(exist_ok=True)
            return json.loads(TODO_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self):
        try:
            TODO_FILE.write_text(json.dumps(self._todos, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _refresh(self):
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, todo in enumerate(self._todos):
            row = QHBoxLayout(); row.setSpacing(8)
            cb = QCheckBox()
            cb.setChecked(todo.get("done", False))
            cb.setStyleSheet(f"""
                QCheckBox::indicator {{
                    width: 14px; height: 14px;
                    border: 1px solid {C.BORDER_A}; border-radius: 7px;
                    background: transparent;
                }}
                QCheckBox::indicator:checked {{
                    background: {C.GREEN}; border: 1px solid {C.GREEN};
                }}
            """)
            idx = i
            cb.toggled.connect(lambda checked, k=idx: self._toggle(k, checked))
            lbl = QLabel(todo.get("text", ""))
            lbl.setFont(QFont("Segoe UI", 9))
            done  = todo.get("done", False)
            color = C.TEXT_DIM if done else C.WHITE
            td    = "text-decoration: line-through;" if done else ""
            lbl.setStyleSheet(f"color: {color}; background: transparent; {td}")
            lbl.setWordWrap(True)
            del_btn = QPushButton("✕")
            del_btn.setFixedSize(16, 16)
            del_btn.setFont(QFont("Segoe UI", 7))
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM}; border: none; border-radius: 8px;
                }}
                QPushButton:hover {{ color: {C.RED}; background: rgba(255,51,85,0.12); }}
            """)
            del_btn.clicked.connect(lambda _, k=idx: self._delete(k))
            row.addWidget(cb); row.addWidget(lbl, stretch=1); row.addWidget(del_btn)
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            container.setLayout(row)
            self._list_lay.insertWidget(self._list_lay.count() - 1, container)

    def _toggle(self, idx: int, checked: bool):
        if 0 <= idx < len(self._todos):
            self._todos[idx]["done"] = checked
            self._save(); self._refresh()

    def _delete(self, idx: int):
        if 0 <= idx < len(self._todos):
            self._todos.pop(idx)
            self._save(); self._refresh()

    def _add_from_input(self):
        txt = self._inp.text().strip()
        if txt:
            self.add_todo(txt); self._inp.clear()

    def add_todo(self, text: str):
        self._todos.append({"text": text, "done": False})
        self._save(); self._refresh()


class NotesWidget(DraggableWidget):
    def __init__(self, parent=None):
        super().__init__("NOTAS", "📝", C.ACC2, closeable=True, parent=parent)
        self.resize(280, 240)
        self._edit = QTextEdit()
        self._edit.setFont(QFont("Consolas", 9))
        self._edit.setPlaceholderText("Notas, ideas, snippets…")
        self._edit.setStyleSheet(f"""
            QTextEdit {{
                background: transparent; color: {C.TEXT}; border: none;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: transparent; width: 4px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_A}; border-radius: 2px;
            }}
        """)
        try:
            NOTES_FILE.parent.mkdir(exist_ok=True)
            if NOTES_FILE.exists():
                self._edit.setPlainText(NOTES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        self._edit.textChanged.connect(self._save)
        self._body.addWidget(self._edit, stretch=1)

    def _save(self):
        try:
            NOTES_FILE.write_text(self._edit.toPlainText(), encoding="utf-8")
        except Exception:
            pass


class SpotifyProgressBar(QWidget):
    """Animated progress bar for Spotify playback."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self._progress = 0.0   # 0.0 – 1.0
        self._anim_val = 0.0
        self._pulse_t  = 0
        tmr = QTimer(self)
        tmr.timeout.connect(self._tick)
        tmr.start(40)

    def set_progress(self, value: float):
        self._progress = max(0.0, min(1.0, value))

    def _tick(self):
        self._anim_val += (self._progress - self._anim_val) * 0.08
        self._pulse_t += 1
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        # Track
        p.setBrush(QBrush(qcol("#1a0a2e")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(0, 0, W, H), 3, 3)
        # Fill
        fw = W * self._anim_val
        if fw > 1:
            pulse = 0.85 + 0.15 * math.sin(self._pulse_t * 0.12)
            col = QColor(int(255 * pulse), int(45 * pulse), int(200 * pulse), 230)
            p.setBrush(QBrush(col))
            p.drawRoundedRect(QRectF(0, 0, fw, H), 3, 3)
            # Glow head
            if fw > 6:
                glow = QRadialGradient(fw, H / 2, 8)
                glow.setColorAt(0.0, QColor(255, 100, 230, 200))
                glow.setColorAt(1.0, QColor(0, 0, 0, 0))
                p.setBrush(QBrush(glow))
                p.drawEllipse(QPointF(fw, H / 2), 8, 8)


class SpotifyWidget(DraggableWidget):
    """Full Spotify player widget with controls, progress, and album art placeholder."""

    _update_sig = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__("SPOTIFY", "♪", C.PINK, closeable=True, parent=parent)
        self.resize(340, 290)
        self._sp_ref = None   # will be set to spotipy.Spotify lazily
        self._is_playing = False
        self._duration_ms = 0
        self._progress_ms = 0

        # ── Album art placeholder ──────────────────────────
        self._art_lbl = QLabel()
        self._art_lbl.setFixedSize(64, 64)
        self._art_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._art_lbl.setStyleSheet(f"""
            background: rgba(255,45,200,0.08);
            border: 1px solid rgba(255,45,200,0.25);
            border-radius: 12px;
            color: {C.PINK};
            font-size: 28px;
        """)
        self._art_lbl.setText("♫")

        # ── Song info ──────────────────────────────────────
        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        self._song = QLabel("Sin reproducción")
        self._song.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._song.setWordWrap(True)
        self._song.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        self._song.setMaximumHeight(48)
        info_col.addWidget(self._song)

        self._artist = QLabel("")
        self._artist.setFont(QFont("Segoe UI", 9))
        self._artist.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        info_col.addWidget(self._artist)

        self._album = QLabel("")
        self._album.setFont(QFont("Segoe UI", 8))
        self._album.setStyleSheet(f"color: rgba(255,45,200,0.6); background: transparent;")
        info_col.addWidget(self._album)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        top_row.addWidget(self._art_lbl)
        top_row.addLayout(info_col, stretch=1)
        self._body.addLayout(top_row)

        # ── Progress bar ───────────────────────────────────
        self._progress = SpotifyProgressBar()
        self._body.addWidget(self._progress)

        # Time labels
        time_row = QHBoxLayout()
        self._elapsed_lbl = QLabel("0:00")
        self._elapsed_lbl.setFont(QFont("Consolas", 7))
        self._elapsed_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._total_lbl = QLabel("0:00")
        self._total_lbl.setFont(QFont("Consolas", 7))
        self._total_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._total_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        time_row.addWidget(self._elapsed_lbl)
        time_row.addStretch()
        time_row.addWidget(self._total_lbl)
        self._body.addLayout(time_row)

        # ── Controls ───────────────────────────────────────
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)
        ctrl_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        def _ctrl_btn(label, size=36, font_size=16, cb=None):
            btn = QPushButton(label)
            btn.setFixedSize(size, size)
            btn.setFont(QFont("Segoe UI Emoji" if _OS == "Windows" else "Arial", font_size))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255,45,200,0.07); color: {C.PINK};
                    border: 1px solid rgba(255,45,200,0.2); border-radius: {size//2}px;
                }}
                QPushButton:hover {{
                    background: rgba(255,45,200,0.20); border: 1px solid {C.PINK};
                }}
                QPushButton:pressed {{ background: rgba(255,45,200,0.35); }}
            """)
            if cb:
                btn.clicked.connect(cb)
            return btn

        self._btn_prev = _ctrl_btn("⏮", cb=self._cmd_prev)
        self._btn_play = _ctrl_btn("⏸", size=44, font_size=18, cb=self._cmd_play_pause)
        self._btn_next = _ctrl_btn("⏭", cb=self._cmd_next)
        self._btn_shuffle = _ctrl_btn("🔀", size=30, font_size=11, cb=self._cmd_shuffle)
        self._btn_like = _ctrl_btn("♡", size=30, font_size=12, cb=self._cmd_like)

        ctrl_row.addWidget(self._btn_shuffle)
        ctrl_row.addWidget(self._btn_prev)
        ctrl_row.addWidget(self._btn_play)
        ctrl_row.addWidget(self._btn_next)
        ctrl_row.addWidget(self._btn_like)
        self._body.addLayout(ctrl_row)

        # Volume row
        vol_row = QHBoxLayout()
        vol_row.setSpacing(6)
        vol_lbl = QLabel("🔊")
        vol_lbl.setFont(QFont("Segoe UI Emoji" if _OS == "Windows" else "Arial", 10))
        vol_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        vol_row.addWidget(vol_lbl)
        # Simple vol buttons
        for pct, lbl in [(25, "▁"), (50, "▃"), (75, "▅"), (100, "▇")]:
            vb = QPushButton(lbl)
            vb.setFixedSize(24, 20)
            vb.setFont(QFont("Segoe UI", 9))
            vb.setCursor(Qt.CursorShape.PointingHandCursor)
            vb.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255,45,200,0.05); color: rgba(255,45,200,0.5);
                    border: none; border-radius: 4px;
                }}
                QPushButton:hover {{ color: {C.PINK}; background: rgba(255,45,200,0.15); }}
            """)
            vb.clicked.connect(lambda _, v=pct: self._cmd_volume(v))
            vol_row.addWidget(vb)
        vol_row.addStretch()
        self._body.addLayout(vol_row)

        self._hint = QLabel("Di: 'poneme algo de jazz'")
        self._hint.setFont(QFont("Segoe UI", 8))
        self._hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; font-style: italic;")
        self._body.addWidget(self._hint)

        # Progress ticker
        self._tick_tmr = QTimer(self)
        self._tick_tmr.timeout.connect(self._tick_progress)
        self._tick_tmr.start(1000)

        self._update_sig.connect(self._apply_update)

    # ── Progress ticker ────────────────────────────────────
    def _tick_progress(self):
        if self._is_playing and self._duration_ms > 0:
            self._progress_ms = min(self._progress_ms + 1000, self._duration_ms)
            self._progress.set_progress(self._progress_ms / self._duration_ms)
            self._elapsed_lbl.setText(self._fmt_ms(self._progress_ms))

    @staticmethod
    def _fmt_ms(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    # ── Control commands (run in thread so they don't block UI) ──
    def _nexo_cmd(self, action: str, **kwargs):
        """Send a spotify command via NEXO action system (non-blocking)."""
        def _run():
            try:
                from actions.spotify_control import spotify_control
                params = {"action": action, **kwargs}
                spotify_control(params)
            except Exception as e:
                print(f"[SpotifyWidget] cmd error: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def _cmd_play_pause(self):
        if self._is_playing:
            self._is_playing = False
            self._btn_play.setText("▶")
            self._nexo_cmd("pause")
        else:
            self._is_playing = True
            self._btn_play.setText("⏸")
            self._nexo_cmd("resume")

    def _cmd_prev(self):
        self._nexo_cmd("previous")

    def _cmd_next(self):
        self._nexo_cmd("next")

    def _cmd_shuffle(self):
        self._nexo_cmd("shuffle")

    def _cmd_like(self):
        self._btn_like.setText("♥")
        self._btn_like.setStyleSheet(self._btn_like.styleSheet().replace("color: {C.PINK}", "color: #ff6666;"))
        self._nexo_cmd("like")

    def _cmd_volume(self, pct: int):
        self._nexo_cmd("volume", value=pct)

    # ── Public update API ──────────────────────────────────
    def update_spotify(self, song: str, artist: str = "", album: str = "",
                       duration_ms: int = 0, progress_ms: int = 0,
                       is_playing: bool = True):
        self._update_sig.emit({
            "song": song, "artist": artist, "album": album,
            "duration_ms": duration_ms, "progress_ms": progress_ms,
            "is_playing": is_playing,
        })

    def _apply_update(self, d: dict):
        song       = d.get("song", "")
        artist     = d.get("artist", "")
        album      = d.get("album", "")
        dur        = int(d.get("duration_ms", 0))
        prog       = int(d.get("progress_ms", 0))
        playing    = bool(d.get("is_playing", True))

        self._song.setText(song or "Sin reproducción")
        self._artist.setText(artist)
        self._album.setText(album)
        self._hint.setVisible(not bool(song))

        self._is_playing   = playing
        self._duration_ms  = dur
        self._progress_ms  = prog
        self._btn_play.setText("⏸" if playing else "▶")

        if dur > 0:
            self._progress.set_progress(prog / dur)
            self._elapsed_lbl.setText(self._fmt_ms(prog))
            self._total_lbl.setText(self._fmt_ms(dur))
        else:
            self._progress.set_progress(0)
            self._elapsed_lbl.setText("0:00")
            self._total_lbl.setText("0:00")


# ── Camera widget with real cv2 capture + accessibility tracking ─────────────
class CameraWidget(DraggableWidget):
    _frame_sig       = pyqtSignal(object)        # (mode_str, rgb_array) or None
    _status_sig      = pyqtSignal(str, str)      # (label_text, stylesheet)
    _hand_cursor_sig = pyqtSignal(float, float)  # normalised (x, y)
    _hand_fist_sig   = pyqtSignal(bool)          # is_fist

    def __init__(self, parent=None):
        super().__init__("CÁMARA", "📷", C.PRI, closeable=True, parent=parent)
        self.resize(420, 390)
        self._cap    = None
        self._active = False
        self._thread = None
        self._lock   = threading.Lock()
        self._widget_started_eye     = False
        self._widget_started_gesture = False
        self._sys_hand_overlay_ref   = None   # set by main window after init

    def set_sys_hand_overlay(self, overlay) -> None:
        """Store a reference to SystemHandOverlay so _hand_start/_hand_stop can show/hide it."""
        self._sys_hand_overlay_ref = overlay

        # Mode status bar (top of body)
        self._cam_mode_bar = QLabel("⚫  Sin tracking activo")
        self._cam_mode_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_mode_bar.setFixedHeight(22)
        self._cam_mode_bar.setStyleSheet(
            "background:#0a1520; color:#455a64; font-size:9px; font-weight:bold;"
            "border-radius:4px 4px 0 0;"
        )
        self._body.addWidget(self._cam_mode_bar)

        # Camera feed label
        self._cam_lbl = QLabel("Iniciando cámara…")
        self._cam_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_lbl.setMinimumSize(388, 248)
        self._cam_lbl.setStyleSheet(
            f"background:#000; border-radius:0; color:{C.TEXT_DIM}; font-size:11px;"
        )
        self._body.addWidget(self._cam_lbl)

        # Tracking toggle buttons below the feed
        _btn_row = QHBoxLayout()
        _btn_row.setContentsMargins(4, 4, 4, 2)
        _btn_row.setSpacing(6)

        _eye_style_off = (f"QPushButton{{background:#071826;color:{C.PRI};"
                          f"border:1px solid {C.PRI};border-radius:4px;"
                          f"font-size:9px;font-weight:bold;}}"
                          f"QPushButton:hover{{background:{C.PRI};color:#000;}}")
        _eye_style_on  = ("QPushButton{background:#00e5ff;color:#000;"
                          "border:1px solid #00e5ff;border-radius:4px;"
                          "font-size:9px;font-weight:bold;}"
                          "QPushButton:hover{background:#00b8d4;color:#000;}")
        _gest_style_off = (f"QPushButton{{background:#071826;color:{C.PRI};"
                           f"border:1px solid {C.PRI};border-radius:4px;"
                           f"font-size:9px;font-weight:bold;}}"
                           f"QPushButton:hover{{background:{C.PRI};color:#000;}}")
        _gest_style_on  = ("QPushButton{background:#ff9800;color:#000;"
                           "border:1px solid #ff9800;border-radius:4px;"
                           "font-size:9px;font-weight:bold;}"
                           "QPushButton:hover{background:#f57c00;color:#000;}")

        self._eye_style_off  = _eye_style_off
        self._eye_style_on   = _eye_style_on
        self._gest_style_off = _gest_style_off
        self._gest_style_on  = _gest_style_on

        self._btn_cam_eye = QPushButton("👁  Eye Tracking")
        self._btn_cam_eye.setFixedHeight(26)
        self._btn_cam_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cam_eye.setStyleSheet(_eye_style_off)
        self._btn_cam_eye.clicked.connect(self._cam_toggle_eye)

        self._btn_cam_gesture = QPushButton("🤖  Gestos")
        self._btn_cam_gesture.setFixedHeight(26)
        self._btn_cam_gesture.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cam_gesture.setStyleSheet(_gest_style_off)
        self._btn_cam_gesture.clicked.connect(self._cam_toggle_gesture)

        # ── Hand gesture control button ────────────────────────
        self._hand_style_off = (
            f"QPushButton{{background:#071826;color:#00c853;"
            f"border:1px solid #00c853;border-radius:4px;"
            f"font-size:9px;font-weight:bold;}}"
            f"QPushButton:hover{{background:#00c853;color:#000;}}"
        )
        self._btn_hand = QPushButton("✋  Control de Mano")
        self._btn_hand.setFixedHeight(26)
        self._btn_hand.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_hand.setStyleSheet(self._hand_style_off)
        self._btn_hand.setToolTip(
            "Gestos:\n"
            "  • Mover el índice    → mueve el cursor\n"
            "  • Puño cerrado       → arrastar (drag)\n"
            "  • Abrir el puño      → soltar el drag\n"
            "  • Quieto 1.5 s       → doble click automático\n"
            "\n"
            "  Al sacar la mano del encuadre el cursor\n"
            "  de Windows vuelve para uso normal."
        )
        self._btn_hand.clicked.connect(self._cam_toggle_hand)
        self._hand_active  = False
        self._hand_engine  = None
        self._hand_overlay = None

        _btn_row.addWidget(self._btn_cam_eye)
        _btn_row.addWidget(self._btn_cam_gesture)
        _btn_row.addWidget(self._btn_hand)
        _btn_row.addStretch()
        self._body.addLayout(_btn_row)

        # ── Hand control sensitivity settings row ──────────────────────────────
        _hand_cfg_row = QHBoxLayout()
        _hand_cfg_row.setContentsMargins(6, 0, 6, 4)
        _hand_cfg_row.setSpacing(6)

        _sldr_style = (
            "QSlider::groove:horizontal{height:4px;background:#1a2a3a;border-radius:2px;}"
            "QSlider::handle:horizontal{width:12px;height:12px;margin:-4px 0;"
            "background:#00c853;border-radius:6px;}"
            "QSlider::sub-page:horizontal{background:#00c853;border-radius:2px;}"
        )
        _lbl_style = "color:#607d8b;font-size:8px;font-weight:bold;"

        # Sensitivity
        _lbl_sens = QLabel("🐇 Velocidad")
        _lbl_sens.setStyleSheet(_lbl_style)
        self._sld_hand_sens = QSlider(Qt.Orientation.Horizontal)
        self._sld_hand_sens.setRange(1, 10)
        self._sld_hand_sens.setFixedWidth(70)
        self._sld_hand_sens.setStyleSheet(_sldr_style)
        self._sld_hand_sens.setToolTip("Velocidad del cursor (1=lento, 10=rápido)")
        self._sld_hand_sens.setCursor(Qt.CursorShape.PointingHandCursor)

        # Smoothing
        _lbl_smooth = QLabel("✨ Suavizado")
        _lbl_smooth.setStyleSheet(_lbl_style)
        self._sld_hand_smooth = QSlider(Qt.Orientation.Horizontal)
        self._sld_hand_smooth.setRange(1, 10)
        self._sld_hand_smooth.setFixedWidth(70)
        self._sld_hand_smooth.setStyleSheet(_sldr_style)
        self._sld_hand_smooth.setToolTip("Suavizado del movimiento (1=estable/lento, 10=directo/rápido)")
        self._sld_hand_smooth.setCursor(Qt.CursorShape.PointingHandCursor)

        # Load saved values (default 5)
        try:
            _hcfg = json.loads(API_FILE.read_text(encoding="utf-8"))
            self._sld_hand_sens.setValue(int(_hcfg.get("hand_sensitivity", 5)))
            self._sld_hand_smooth.setValue(int(_hcfg.get("hand_smoothing", 5)))
        except Exception:
            self._sld_hand_sens.setValue(5)
            self._sld_hand_smooth.setValue(5)

        self._sld_hand_sens.valueChanged.connect(self._on_hand_sens_changed)
        self._sld_hand_smooth.valueChanged.connect(self._on_hand_smooth_changed)

        _hand_cfg_row.addWidget(_lbl_sens)
        _hand_cfg_row.addWidget(self._sld_hand_sens)
        _hand_cfg_row.addSpacing(8)
        _hand_cfg_row.addWidget(_lbl_smooth)
        _hand_cfg_row.addWidget(self._sld_hand_smooth)
        _hand_cfg_row.addStretch()
        self._body.addLayout(_hand_cfg_row)

        self._frame_sig.connect(self._draw_frame)
        self._status_sig.connect(self._update_mode_bar)

        # QTimer: polls accessibility frame buffer at 20fps when tracking is active
        self._cam_poll_timer = QTimer(self)
        self._cam_poll_timer.setInterval(50)
        self._cam_poll_timer.timeout.connect(self._poll_tracking_frame)

    def _update_mode_bar(self, text: str, style: str):
        if hasattr(self, "_cam_mode_bar"):
            self._cam_mode_bar.setText(text)
            self._cam_mode_bar.setStyleSheet(style)

    # ── Tracking toggle helpers ───────────────────────────────────────────────

    def _cam_toggle_eye(self):
        try:
            from actions.accessibility import _get_eye_tracker, _get_micro_detector
            tracker = _get_eye_tracker()
            if tracker.running:
                tracker.stop()
                self._widget_started_eye = False
                self._btn_cam_eye.setText("👁  Eye Tracking")
                self._btn_cam_eye.setStyleSheet(self._eye_style_off)
                if not _get_micro_detector().running:
                    self._cam_poll_timer.stop()
                    self._start_raw_capture()
            else:
                msg = tracker.start()
                if "✅" in msg:
                    self._widget_started_eye = True
                    self._btn_cam_eye.setText("⏹  Detener Eye")
                    self._btn_cam_eye.setStyleSheet(self._eye_style_on)
                    self._stop_raw_capture()
                    self._cam_poll_timer.start()
                    self._cam_mode_bar.setText("⏳  Iniciando eye tracking…")
                    self._cam_mode_bar.setStyleSheet(
                        "background:#001a2e; color:#607d8b; font-size:9px;"
                        "font-weight:bold; border-radius:4px 4px 0 0;"
                    )
        except Exception as e:
            print(f"[CameraWidget] eye error: {e}")

    def _cam_toggle_gesture(self):
        try:
            from actions.accessibility import _get_micro_detector, _get_eye_tracker
            det = _get_micro_detector()
            if det.running:
                det.stop()
                self._widget_started_gesture = False
                self._btn_cam_gesture.setText("🤖  Gestos")
                self._btn_cam_gesture.setStyleSheet(self._gest_style_off)
                if not _get_eye_tracker().running:
                    self._cam_poll_timer.stop()
                    self._start_raw_capture()
            else:
                msg = det.start()
                if "✅" in msg:
                    self._widget_started_gesture = True
                    self._btn_cam_gesture.setText("⏹  Detener Gestos")
                    self._btn_cam_gesture.setStyleSheet(self._gest_style_on)
                    self._stop_raw_capture()
                    self._cam_poll_timer.start()
                    self._cam_mode_bar.setText("⏳  Iniciando gestos…")
                    self._cam_mode_bar.setStyleSheet(
                        "background:#1a0e00; color:#8a6000; font-size:9px;"
                        "font-weight:bold; border-radius:4px 4px 0 0;"
                    )
        except Exception as e:
            print(f"[CameraWidget] gesture error: {e}")

    def _poll_tracking_frame(self):
        """QTimer callback — pulls latest annotated frame from accessibility module."""
        try:
            from actions.accessibility import get_latest_camera_frame, _get_eye_tracker, _get_micro_detector
            import cv2
            et = _get_eye_tracker()
            md = _get_micro_detector()
            if et.running:
                frame = get_latest_camera_frame("eye")
                if frame is not None:
                    self._frame_sig.emit(("eye", cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
            elif md.running:
                frame = get_latest_camera_frame("micro")
                if frame is not None:
                    self._frame_sig.emit(("micro", cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
            else:
                # Tracking stopped externally — reset buttons and fall back to raw camera
                self._cam_poll_timer.stop()
                self._btn_cam_eye.setText("👁  Eye Tracking")
                self._btn_cam_eye.setStyleSheet(self._eye_style_off)
                self._btn_cam_gesture.setText("🤖  Gestos")
                self._btn_cam_gesture.setStyleSheet(self._gest_style_off)
                self._widget_started_eye = False
                self._widget_started_gesture = False
                self._start_raw_capture()
        except Exception:
            pass

    # ── Camera lifecycle ─────────────────────────────────────────────────────

    def start_camera(self):
        if self._active:
            return
        # If tracking already running, just hook into it — don't open our own camera
        try:
            from actions.accessibility import _get_eye_tracker, _get_micro_detector
            et = _get_eye_tracker()
            md = _get_micro_detector()
            if et.running:
                self._active = True
                self._btn_cam_eye.setText("⏹  Detener Eye")
                self._btn_cam_eye.setStyleSheet(self._eye_style_on)
                self._cam_poll_timer.start()
                return
            elif md.running:
                self._active = True
                self._btn_cam_gesture.setText("⏹  Detener Gestos")
                self._btn_cam_gesture.setStyleSheet(self._gest_style_on)
                self._cam_poll_timer.start()
                return
        except Exception:
            pass
        self._start_raw_capture()

    def _start_raw_capture(self):
        if self._active and self._thread and self._thread.is_alive():
            return
        self._active = True
        self._cam_lbl.setText("Abriendo cámara…")
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _stop_raw_capture(self):
        self._active = False
        with self._lock:
            if self._cap:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None

    def stop_camera(self):
        self._cam_poll_timer.stop()
        self._active = False
        with self._lock:
            if self._cap:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None
        self._cam_lbl.setText("Cámara apagada")
        self._cam_lbl.setPixmap(QPixmap())
        # Stop tracking if this widget started it
        try:
            from actions.accessibility import _get_eye_tracker, _get_micro_detector
            if self._widget_started_eye:
                _get_eye_tracker().stop()
                self._widget_started_eye = False
            if self._widget_started_gesture:
                _get_micro_detector().stop()
                self._widget_started_gesture = False
        except Exception:
            pass

    def _capture_loop(self):
        """Raw camera capture — used only when no accessibility tracking is active."""
        try:
            import cv2
            import io
            with self._lock:
                try:
                    cfg = json.loads(API_FILE.read_text(encoding="utf-8"))
                    cam_idx = int(cfg.get("camera_index", 0))
                except Exception:
                    cam_idx = 0
                # Never use CAP_DSHOW — it causes Windows SEH crashes
                self._cap = cv2.VideoCapture(cam_idx)
                if not self._cap.isOpened():
                    self._frame_sig.emit(None)
                    return
            _fail = 0
            while self._active:
                with self._lock:
                    if not self._cap:
                        break
                    ret, frame = self._cap.read()
                if ret:
                    _fail = 0

                    # ── Hand control engine (if active) ───────────────
                    if self._hand_active and self._hand_engine is not None:
                        try:
                            frame = self._hand_engine.process_frame(frame)
                        except Exception as _he:
                            print(f"[Hand] {_he}")

                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    self._frame_sig.emit(("hand" if self._hand_active else "raw", rgb))
                    try:
                        from PIL import Image as PILImage
                        pil_img = PILImage.fromarray(rgb)
                        buf = io.BytesIO()
                        pil_img.save(buf, format="JPEG", quality=70)
                        from actions.camera_bus import put_frame
                        put_frame(buf.getvalue())
                    except Exception:
                        pass
                else:
                    _fail += 1
                    if _fail >= 10:
                        self._frame_sig.emit(None)
                        break
                    time.sleep(0.1)
                    continue
                time.sleep(0.033)
        except Exception as e:
            print(f"[Camera] Error: {e}")
            self._frame_sig.emit(None)
        finally:
            with self._lock:
                if self._cap:
                    self._cap.release()
                    self._cap = None

    def _draw_frame(self, data):
        if data is None:
            self._cam_lbl.setText("No se pudo abrir la cámara.\nVerificá que esté conectada.")
            self._status_sig.emit(
                "❌  Error de cámara",
                "background:#1a0a0a; color:#ff4444; font-size:9px; font-weight:bold;"
                "border-radius:4px 4px 0 0;"
            )
            return
        mode, frame = data if isinstance(data, tuple) else ("raw", data)
        h, w, ch = frame.shape
        img    = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
        scaled = QPixmap.fromImage(img).scaled(
            self._cam_lbl.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._cam_lbl.setPixmap(scaled)

        if mode == "eye":
            self._status_sig.emit(
                "👁  EYE TRACKING ACTIVO  ●",
                "background:#001a2e; color:#00e5ff; font-size:9px; font-weight:bold;"
                "border-radius:4px 4px 0 0;"
            )
        elif mode == "micro":
            self._status_sig.emit(
                "🤖  CONTROL POR GESTOS ACTIVO  ●",
                "background:#1a0e00; color:#ff9800; font-size:9px; font-weight:bold;"
                "border-radius:4px 4px 0 0;"
            )
        elif mode == "hand":
            self._status_sig.emit(
                "✋  CONTROL DE MANO ACTIVO  ●",
                "background:#001a0a; color:#00c853; font-size:9px; font-weight:bold;"
                "border-radius:4px 4px 0 0;"
            )
        else:
            self._status_sig.emit(
                "📷  Cámara — sin tracking",
                "background:#0a1520; color:#00d4ff; font-size:9px; font-weight:bold;"
                "border-radius:4px 4px 0 0;"
            )

    # ── Hand gesture control ─────────────────────────────────────────────────

    def _cam_toggle_hand(self):
        """Toggle hand cursor control — MediaPipe Hands."""
        if getattr(self, "_hand_active", False):
            self._hand_stop()
        else:
            self._hand_start()

    def _hand_cfg(self):
        """Build HandControlConfig from current slider values."""
        from actions.hand_control import HandControlConfig
        return HandControlConfig(
            sensitivity=float(self._sld_hand_sens.value()),
            smoothing=float(self._sld_hand_smooth.value()),
        )

    def _on_hand_sens_changed(self, value: int):
        """Sensitivity slider moved — update running engine + save to config."""
        if getattr(self, "_hand_engine", None) is not None:
            self._hand_engine.update_config(self._hand_cfg())
        self._save_hand_cfg()

    def _on_hand_smooth_changed(self, value: int):
        """Smoothing slider moved — update running engine + save to config."""
        if getattr(self, "_hand_engine", None) is not None:
            self._hand_engine.update_config(self._hand_cfg())
        self._save_hand_cfg()

    def _save_hand_cfg(self):
        """Persist sensitivity + smoothing to api_keys.json."""
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8")) if API_FILE.exists() else {}
            d["hand_sensitivity"] = self._sld_hand_sens.value()
            d["hand_smoothing"]   = self._sld_hand_smooth.value()
            API_FILE.write_text(json.dumps(d, indent=4), encoding="utf-8")
        except Exception:
            pass

    def _hand_start(self):
        # ── ENTIRE body wrapped — any exception shows a message instead of crash ──
        try:
            from actions.hand_control import HandControlEngine

            # Build the hand engine with current sensitivity settings
            self._hand_engine = HandControlEngine(
                on_cursor=lambda x, y: self._hand_cursor_sig.emit(x, y),
                on_fist=lambda f:       self._hand_fist_sig.emit(f),
                config=self._hand_cfg(),
            )
            self._hand_engine.start()
            self._hand_active = True

            # Create overlay over the entire dashboard (in-window cursor dot)
            parent_widget = self.parent()
            if parent_widget is not None:
                self._hand_overlay = HandCursorOverlay(parent_widget)
                self._hand_cursor_sig.connect(self._hand_overlay.on_cursor)
                self._hand_fist_sig.connect(self._hand_overlay.on_fist)
                self._hand_overlay.resize(parent_widget.size())
                self._hand_overlay.raise_()
                self._hand_overlay.show()
            else:
                self._hand_overlay = None

            # Show full-screen system overlay (replaces Windows cursor globally)
            if self._sys_hand_overlay_ref is not None:
                self._sys_hand_overlay_ref.show()
                self._sys_hand_overlay_ref.raise_()

            # Restart raw capture so frames flow through hand engine
            self._stop_raw_capture()
            self._start_raw_capture()

            self._btn_hand.setText("⏹  Detener Mano")
            self._btn_hand.setStyleSheet(
                "QPushButton{background:#00c853;color:#000;border:1px solid #00c853;"
                "border-radius:4px;font-size:9px;font-weight:bold;}"
                "QPushButton:hover{background:#00e676;color:#000;}"
            )
            self._status_sig.emit(
                "✋  CONTROL DE MANO ACTIVO  ●",
                "background:#001a0a; color:#00c853; font-size:9px; font-weight:bold;"
                "border-radius:4px 4px 0 0;"
            )

        except (ImportError, ModuleNotFoundError):
            # mediapipe not installed — tell the user, do NOT crash
            self._hand_active  = False
            self._hand_engine  = None
            self._hand_overlay = None
            self._status_sig.emit(
                "❌  mediapipe no instalado — pip install mediapipe",
                "background:#1a0000; color:#ff4444; font-size:9px; font-weight:bold;"
                "border-radius:4px 4px 0 0;"
            )
        except Exception as _e:
            import traceback as _tb
            print(f"[Hand] Error al iniciar control de mano: {_e}")
            _tb.print_exc()
            self._hand_active  = False
            self._hand_engine  = None
            self._hand_overlay = None
            self._status_sig.emit(
                f"❌  Error: {str(_e)[:70]}",
                "background:#1a0000; color:#ff4444; font-size:9px; font-weight:bold;"
                "border-radius:4px 4px 0 0;"
            )

    def _hand_stop(self):
        self._hand_active = False
        if hasattr(self, "_hand_engine") and self._hand_engine:
            try:
                self._hand_cursor_sig.disconnect()
                self._hand_fist_sig.disconnect()
            except Exception:
                pass
            self._hand_engine.stop()
            self._hand_engine = None
        if hasattr(self, "_hand_overlay") and self._hand_overlay:
            self._hand_overlay.hide()
            self._hand_overlay.deleteLater()
            self._hand_overlay = None
        # Hide the system-wide overlay and restore Windows cursor
        if self._sys_hand_overlay_ref is not None:
            self._sys_hand_overlay_ref.hide()
        self._btn_hand.setText("✋  Control de Mano")
        self._btn_hand.setStyleSheet(self._hand_style_off)
        self._status_sig.emit(
            "📷  Cámara — sin tracking",
            "background:#0a1520; color:#00d4ff; font-size:9px; font-weight:bold;"
            "border-radius:4px 4px 0 0;"
        )

    def is_tracking_active(self) -> bool:
        """Returns True if any tracking mode (eye / gesture / hand) is running."""
        if getattr(self, "_hand_active", False):
            return True
        try:
            from actions.accessibility import _get_eye_tracker, _get_micro_detector
            if _get_eye_tracker().running or _get_micro_detector().running:
                return True
        except Exception:
            pass
        return False

    def _on_close(self):
        self._hand_stop()
        self.stop_camera()
        super()._on_close()


# ═══════════════════════════════════════════════════════════
# HAND CURSOR OVERLAY — transparent, covers the full dashboard
# ═══════════════════════════════════════════════════════════
class HandCursorOverlay(QWidget):
    """
    Transparent full-window overlay that renders a hand cursor dot.
    Does NOT capture mouse events — all clicks pass through to widgets below.
    When fist is detected, it drags the DraggableWidget under the cursor.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent;")

        self._cx = 0
        self._cy = 0
        self._is_fist   = False
        self._drag_w: "DraggableWidget | None" = None
        self._drag_off  = QPoint(0, 0)

    # ── Slots (called from Qt main thread via signal) ───────────────────────

    def on_cursor(self, nx: float, ny: float):
        # Map normalised camera coords → overlay coords
        # Mirror X (camera is already flipped horizontally in HandControlEngine)
        self._cx = int(nx * self.width())
        self._cy = int(ny * self.height())
        self.update()   # trigger paintEvent

        # Drag: move the grabbed widget
        if self._is_fist and self._drag_w is not None:
            p = self.parent()
            new_pos = QPoint(
                self._cx - self._drag_off.x(),
                self._cy - self._drag_off.y(),
            )
            max_x = (p.width()  - self._drag_w.width())  if p else 99999
            max_y = (p.height() - self._drag_w.height()) if p else 99999
            new_pos.setX(max(0, min(new_pos.x(), max_x)))
            new_pos.setY(max(0, min(new_pos.y(), max_y)))
            self._drag_w.move(new_pos)

    def on_fist(self, is_fist: bool):
        self._is_fist = is_fist
        if is_fist:
            # Find a DraggableWidget under the cursor
            global_pos = self.mapToGlobal(QPoint(self._cx, self._cy))
            w = QApplication.widgetAt(global_pos)
            # Walk up widget tree to find a DraggableWidget
            while w is not None:
                if isinstance(w, DraggableWidget):
                    break
                w = w.parent() if callable(getattr(w, "parent", None)) else None
            if isinstance(w, DraggableWidget):
                self._drag_w   = w
                local = w.mapFromGlobal(global_pos)
                self._drag_off = QPoint(local.x(), local.y())
            else:
                self._drag_w = None
        else:
            self._drag_w = None
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def paintEvent(self, event):
        # Sin cursor personalizado — solo se ve el cursor de Windows.
        # El overlay existe para detectar drag (fist gesture) pero no dibuja nada.
        pass


# ═══════════════════════════════════════════════════════════
# SYSTEM CAMERA FLOATER — always-on-top compact overlay
# shown when NEXO hides to tray but tracking is active
# ═══════════════════════════════════════════════════════════
class SystemCameraFloater(QWidget):
    """
    Standalone borderless always-on-top window that mirrors the CameraWidget
    feed while NEXO is minimized to tray.

    Shows the camera feed + the 3 accessibility tracking toggle buttons so the
    user can start/stop Eye Tracking, Head Gesture control, and Hand Control
    without restoring the full NEXO window.

    All three modes control the OS mouse cursor system-wide:
      • Eye tracking  — face center drives cursor, blink = click
      • Head gestures — face position drives cursor, nod = click, tilt = scroll
      • Hand control  — index tip drives cursor, fist = drag, dwell = click
    """

    # Button styles — off/on for each mode
    _EYE_OFF  = ("QPushButton{background:#071826;color:#00e5ff;border:1px solid #00e5ff;"
                 "border-radius:5px;font-size:8px;font-weight:bold;}"
                 "QPushButton:hover{background:#00e5ff;color:#000;}")
    _EYE_ON   = ("QPushButton{background:#00e5ff;color:#000;border:1px solid #00e5ff;"
                 "border-radius:5px;font-size:8px;font-weight:bold;}"
                 "QPushButton:hover{background:#00b8d4;color:#000;}")
    _GEST_OFF = ("QPushButton{background:#071826;color:#ff9800;border:1px solid #ff9800;"
                 "border-radius:5px;font-size:8px;font-weight:bold;}"
                 "QPushButton:hover{background:#ff9800;color:#000;}")
    _GEST_ON  = ("QPushButton{background:#ff9800;color:#000;border:1px solid #ff9800;"
                 "border-radius:5px;font-size:8px;font-weight:bold;}"
                 "QPushButton:hover{background:#f57c00;color:#000;}")
    _HAND_OFF = ("QPushButton{background:#071826;color:#00c853;border:1px solid #00c853;"
                 "border-radius:5px;font-size:8px;font-weight:bold;}"
                 "QPushButton:hover{background:#00c853;color:#000;}")
    _HAND_ON  = ("QPushButton{background:#00c853;color:#000;border:1px solid #00c853;"
                 "border-radius:5px;font-size:8px;font-weight:bold;}"
                 "QPushButton:hover{background:#00e676;color:#000;}")

    def __init__(self, restore_callback, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._restore_cb  = restore_callback
        self._drag_pos    = None
        self._cam_widget  = None   # set via set_camera_widget()

        self._build_ui()
        # Default position: top-right corner, 20 px from edge
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.geometry()
            self.move(sg.right() - 260, 20)

    # ── Camera widget reference ───────────────────────────────────────────────

    def set_camera_widget(self, cam_widget):
        """Call this after the CameraWidget is created so buttons can control it."""
        self._cam_widget = cam_widget
        self._refresh_btn_states()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._container = QFrame()
        self._container.setObjectName("FloaterContainer")
        self._container.setStyleSheet(
            "#FloaterContainer {"
            "  background: #060e1a;"
            "  border: 1px solid #00d4ff55;"
            "  border-radius: 10px;"
            "}"
        )
        cl = QVBoxLayout(self._container)
        cl.setContentsMargins(6, 6, 6, 6)
        cl.setSpacing(4)

        # ── Title bar ──────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setSpacing(4)

        _dot = QLabel("●")
        _dot.setStyleSheet("color:#00d4ff; font-size:8px; background:transparent;")
        _title = QLabel("J.A.R.V.I.S  —  Accesibilidad")
        _title.setStyleSheet(
            "color:#00d4ff; font-size:9px; font-weight:bold; background:transparent;"
        )
        _restore_btn = QPushButton("⬆")
        _restore_btn.setFixedSize(20, 20)
        _restore_btn.setToolTip("Restaurar NEXO")
        _restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _restore_btn.setStyleSheet(
            "QPushButton{background:#0d2233;color:#00d4ff;border:1px solid #00d4ff55;"
            "border-radius:4px;font-size:9px;padding:0;}"
            "QPushButton:hover{background:#00d4ff;color:#000;}"
        )
        _restore_btn.clicked.connect(self._do_restore)

        _close_btn = QPushButton("✕")
        _close_btn.setFixedSize(20, 20)
        _close_btn.setToolTip("Ocultar (tracking sigue activo)")
        _close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _close_btn.setStyleSheet(
            "QPushButton{background:#1a0a0a;color:#ff5555;border:1px solid #ff555555;"
            "border-radius:4px;font-size:9px;padding:0;}"
            "QPushButton:hover{background:#ff4444;color:#fff;}"
        )
        _close_btn.clicked.connect(self.hide)

        title_row.addWidget(_dot)
        title_row.addWidget(_title)
        title_row.addStretch()
        title_row.addWidget(_restore_btn)
        title_row.addWidget(_close_btn)
        cl.addLayout(title_row)

        # ── Status bar ─────────────────────────────────────────────────────
        self._status_lbl = QLabel("⚫  Sin tracking activo")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setFixedHeight(18)
        self._status_lbl.setStyleSheet(
            "background:#0a1520; color:#455a64; font-size:8px;"
            "font-weight:bold; border-radius:4px;"
        )
        cl.addWidget(self._status_lbl)

        # ── Camera feed ─────────────────────────────────────────────────────
        self._cam_lbl = QLabel("Iniciando…")
        self._cam_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_lbl.setFixedSize(240, 154)
        self._cam_lbl.setStyleSheet(
            "background:#000; border-radius:6px; color:#455a64; font-size:9px;"
        )
        cl.addWidget(self._cam_lbl)

        # ── Tracking toggle buttons ─────────────────────────────────────────
        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.HLine)
        _sep.setStyleSheet("color:#0d2233;")
        cl.addWidget(_sep)

        _lbl = QLabel("Control del cursor (sistema completo):")
        _lbl.setStyleSheet("color:#1e4a6a; font-size:7px; background:transparent;")
        cl.addWidget(_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.setContentsMargins(0, 0, 0, 0)

        self._btn_eye  = QPushButton("👁  Eye")
        self._btn_eye.setFixedHeight(28)
        self._btn_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_eye.setToolTip(
            "Eye Tracking — cara al centro mueve el cursor\n"
            "Parpadeo = clic izquierdo"
        )
        self._btn_eye.setStyleSheet(self._EYE_OFF)
        self._btn_eye.clicked.connect(self._toggle_eye)

        self._btn_gest = QPushButton("🤖  Cabeza")
        self._btn_gest.setFixedHeight(28)
        self._btn_gest.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_gest.setToolTip(
            "Control por gestos de cabeza\n"
            "Posición de cara = cursor  |  Nod = clic  |  Tilt = scroll"
        )
        self._btn_gest.setStyleSheet(self._GEST_OFF)
        self._btn_gest.clicked.connect(self._toggle_gesture)

        self._btn_hand = QPushButton("✋  Mano")
        self._btn_hand.setFixedHeight(28)
        self._btn_hand.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_hand.setToolTip(
            "Control de mano (MediaPipe)\n"
            "Índice = cursor  |  Puño = arrastre  |  Quieto 1.2s = clic"
        )
        self._btn_hand.setStyleSheet(self._HAND_OFF)
        self._btn_hand.clicked.connect(self._toggle_hand)

        btn_row.addWidget(self._btn_eye)
        btn_row.addWidget(self._btn_gest)
        btn_row.addWidget(self._btn_hand)
        cl.addLayout(btn_row)

        # ── Hint ────────────────────────────────────────────────────────────
        _hint = QLabel("Arrastrá para mover  ·  doble-clic → restaurar NEXO")
        _hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _hint.setStyleSheet("color:#1e3a4a; font-size:7px; background:transparent;")
        cl.addWidget(_hint)

        root.addWidget(self._container)
        self.adjustSize()

    # ── Button state refresh ──────────────────────────────────────────────────

    def _refresh_btn_states(self):
        """Sync button styles with the actual tracking state."""
        if not self._cam_widget:
            return
        try:
            from actions.accessibility import _get_eye_tracker, _get_micro_detector
            eye_on  = _get_eye_tracker().running
            gest_on = _get_micro_detector().running
        except Exception:
            eye_on = gest_on = False
        hand_on = getattr(self._cam_widget, "_hand_active", False)

        self._btn_eye.setStyleSheet( self._EYE_ON  if eye_on  else self._EYE_OFF)
        self._btn_gest.setStyleSheet(self._GEST_ON if gest_on else self._GEST_OFF)
        self._btn_hand.setStyleSheet(self._HAND_ON if hand_on else self._HAND_OFF)

        self._btn_eye.setText( "⏹  Eye"    if eye_on  else "👁  Eye")
        self._btn_gest.setText("⏹  Cabeza" if gest_on else "🤖  Cabeza")
        self._btn_hand.setText("⏹  Mano"   if hand_on else "✋  Mano")

    # ── Toggle handlers ───────────────────────────────────────────────────────

    def _toggle_eye(self):
        if self._cam_widget:
            self._cam_widget._cam_toggle_eye()
            QTimer.singleShot(150, self._refresh_btn_states)

    def _toggle_gesture(self):
        if self._cam_widget:
            self._cam_widget._cam_toggle_gesture()
            QTimer.singleShot(150, self._refresh_btn_states)

    def _toggle_hand(self):
        if self._cam_widget:
            self._cam_widget._cam_toggle_hand()
            QTimer.singleShot(150, self._refresh_btn_states)

    # ── Public slots — connected to CameraWidget signals ─────────────────────

    def update_frame(self, data):
        """Receives frames from CameraWidget._frame_sig."""
        if not self.isVisible():
            return
        if data is None:
            self._cam_lbl.setText("Sin cámara")
            self._cam_lbl.setPixmap(QPixmap())
            return
        mode, frame = data if isinstance(data, tuple) else ("raw", data)
        h, w, ch = frame.shape
        img    = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
        scaled = QPixmap.fromImage(img).scaled(
            self._cam_lbl.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._cam_lbl.setPixmap(scaled)

    def update_status(self, text: str, style: str):
        """Receives status updates from CameraWidget._status_sig."""
        if not self.isVisible():
            return
        self._status_lbl.setText(text)
        compact = (
            style
            .replace("font-size:9px", "font-size:8px")
            .replace("border-radius:4px 4px 0 0", "border-radius:4px")
        )
        self._status_lbl.setStyleSheet(compact)
        # Keep button states in sync whenever status changes
        QTimer.singleShot(50, self._refresh_btn_states)

    # ── Restore ───────────────────────────────────────────────────────────────

    def _do_restore(self):
        self.hide()
        self._restore_cb()

    # ── Dragging ──────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and (
            event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._do_restore()


# ═══════════════════════════════════════════════════════════════════════════
# SYSTEM HAND OVERLAY — screen-wide always-on-top transparent cursor overlay
# used while NEXO is in tray so hand tracking is visible across the OS
# ═══════════════════════════════════════════════════════════════════════════
class SystemHandOverlay(QWidget):
    """
    Full-screen transparent always-on-top widget that paints the hand cursor
    dot when hand control is active and NEXO is minimized to tray.
    Mouse events pass through (WA_TransparentForMouseEvents).
    """

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self._cx      = 0
        self._cy      = 0
        self._is_fist = False

        # Cover primary screen
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())

    # ── Slots — connected to CameraWidget._hand_cursor_sig / _hand_fist_sig ──

    def on_cursor(self, nx: float, ny: float):
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.geometry()
            self._cx = int(nx * sg.width())  + sg.x()
            self._cy = int(ny * sg.height()) + sg.y()
        self.update()

    def on_fist(self, is_fist: bool):
        self._is_fist = is_fist
        self.update()

    def paintEvent(self, event):
        if self._cx == 0 and self._cy == 0:
            return
        # Coordenadas locales al widget (el widget cubre toda la pantalla)
        lx = self._cx - self.x()
        ly = self._cy - self.y()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._is_fist:
            fill   = QColor(255, 100, 20,  230)  # naranja = arrastrando
            ring   = QColor(255, 200, 150, 180)
        else:
            fill   = QColor(0,   212, 255, 230)  # azul NEXO = normal
            ring   = QColor(180, 240, 255, 160)

        # ── Cursor tipo flecha (la PUNTA en lx,ly) ─────────────────────────
        # Misma forma que el cursor de Windows pero con colores NEXO
        s = 1.6  # escala del cursor
        shadow = QPainterPath()
        shadow.moveTo(lx + 2,           ly + 2)
        shadow.lineTo(lx + 2,           ly + 22 * s + 2)
        shadow.lineTo(lx + 6 * s + 2,   ly + 16 * s + 2)
        shadow.lineTo(lx + 11 * s + 2,  ly + 23 * s + 2)
        shadow.lineTo(lx + 14 * s + 2,  ly + 21 * s + 2)
        shadow.lineTo(lx + 9 * s + 2,   ly + 14 * s + 2)
        shadow.lineTo(lx + 16 * s + 2,  ly + 14 * s + 2)
        shadow.closeSubpath()
        painter.setBrush(QBrush(QColor(0, 0, 0, 70)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(shadow)

        cursor = QPainterPath()
        cursor.moveTo(lx,          ly)
        cursor.lineTo(lx,          ly + 22 * s)
        cursor.lineTo(lx + 6 * s,  ly + 16 * s)
        cursor.lineTo(lx + 11 * s, ly + 23 * s)
        cursor.lineTo(lx + 14 * s, ly + 21 * s)
        cursor.lineTo(lx + 9 * s,  ly + 14 * s)
        cursor.lineTo(lx + 16 * s, ly + 14 * s)
        cursor.closeSubpath()
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
        painter.drawPath(cursor)

        # Punto blanco en la punta (indica el punto exacto de click)
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(lx, ly), 3, 3)

        # Anillo exterior sutil
        painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
        painter.setPen(QPen(ring, 1.2))
        painter.drawEllipse(QPoint(lx, ly), 20, 20)


# ═══════════════════════════════════════════════════════════
# GRID CANVAS  — dark animated dot grid background
# ═══════════════════════════════════════════════════════════
class GridCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._tick = 0
        tmr = QTimer(self)
        tmr.timeout.connect(self._step)
        tmr.start(33)

    def _step(self):
        self._tick += 1
        if self._tick % 3 == 0:
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), QColor(5, 12, 20))

        STEP  = 38
        pulse = 0.28 + 0.13 * math.sin(self._tick * 0.04)
        p.setPen(Qt.PenStyle.NoPen)
        for gx in range(0, W, STEP):
            for gy in range(0, H, STEP):
                d = QColor(12, 35, 60, int(pulse * 255))
                p.setBrush(QBrush(d))
                p.drawEllipse(QPointF(gx, gy), 1.0, 1.0)

        p.setPen(QPen(QColor(10, 24, 44, 28), 1))
        for gy in range(0, H, STEP):
            p.drawLine(0, gy, W, gy)


# ═══════════════════════════════════════════════════════════
# TRANSCRIPT / RESPONSE AREA
# ═══════════════════════════════════════════════════════════
class TranscriptArea(QWidget):
    """White streaming text below the orb."""
    _chunk = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: rgba(3,10,18,200); border-top: 1px solid rgba(13,37,66,0.5);")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 10, 24, 10)
        lay.setSpacing(0)

        self._lbl = QLabel("")
        self._lbl.setFont(QFont("Segoe UI", 13))
        self._lbl.setWordWrap(True)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._lbl.setStyleSheet("color: #ffffff; background: transparent;")
        self._lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(self._lbl)

        self._full = ""
        self._chunk.connect(self._on_chunk)

        self._eff = QGraphicsOpacityEffect(self._lbl)
        self._eff.setOpacity(1.0)
        self._lbl.setGraphicsEffect(self._eff)

    def append_text(self, chunk: str):
        self._chunk.emit(chunk)

    def _on_chunk(self, chunk: str):
        if chunk == "__clear__":
            self._full = ""
            self._lbl.setText("")
            anim = QPropertyAnimation(self._eff, b"opacity", self)
            anim.setDuration(80)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
            return
        if not self._full:
            self._eff.setOpacity(0.0)
            anim = QPropertyAnimation(self._eff, b"opacity", self)
            anim.setDuration(100)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        if self._full and chunk:
            _P = set('.,;:!?¿¡…\n')
            if not self._full[-1].isspace() and not chunk[0].isspace() and chunk[0] not in _P:
                chunk = " " + chunk
        self._full += chunk
        self._lbl.setText(self._full)

    def set_status(self, text: str):
        pass   # no status in transcript area


# ═══════════════════════════════════════════════════════════
# FILE DROP ZONE
# ═══════════════════════════════════════════════════════════
_FILE_ICONS = {
    "image": ("🖼", "#00d4ff"), "video": ("🎬", "#ff6b00"),
    "audio": ("🎵", "#cc44ff"), "pdf":   ("📄", "#ff4444"),
    "word":  ("📝", "#4488ff"), "excel": ("📊", "#44bb44"),
    "code":  ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "text":  ("📃", "#aaaaaa"), "data":  ("🔧", "#88ddff"),
    "unknown": ("📎", "#888888"),
}
_EXT_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],          "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],         "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}


def _cat(path: Path) -> str:
    return _EXT_CAT.get(path.suffix.lower().lstrip("."), "unknown")


def _fmtsz(sz: int) -> str:
    if sz < 1024:      return f"{sz} B"
    elif sz < 1024**2: return f"{sz/1024:.1f} KB"
    elif sz < 1024**3: return f"{sz/1024**2:.1f} MB"
    else:              return f"{sz/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)
        self._file: str | None = None
        self._hover = False
        self._drag  = False
        self._dash  = 0.0
        tmr = QTimer(self)
        tmr.timeout.connect(self._anim)
        tmr.start(40)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._cv = _DropCanvas(self)
        lay.addWidget(self._cv)

    def _anim(self):
        self._dash = (self._dash + 0.7) % 20
        self._cv.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag = True; self._cv.update()

    def dragLeaveEvent(self, e):
        self._drag = False; self._cv.update()

    def dropEvent(self, e: QDropEvent):
        self._drag = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._cv.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hover = True; self._cv.update()

    def leaveEvent(self, e):
        self._hover = False; self._cv.update()

    def current_file(self) -> str | None:
        return self._file

    def clear_file(self):
        self._file = None; self._cv.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona archivo", str(Path.home()), "All Files (*.*)")
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._file = path
        self._cv.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, z: FileDropZone):
        super().__init__(z); self._z = z

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 3
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)
        bg = qcol("#001824" if z._drag else ("#001018" if z._hover else C.PANEL))
        p.setBrush(QBrush(bg)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 10, 10)
        bc = (qcol(C.GREEN, 200) if z._file
              else qcol(C.PRI, 230) if z._drag
              else qcol(C.BORDER_A, 200) if z._hover
              else qcol(C.BORDER, 140))
        pen = QPen(bc, 1.2, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 10, 10)
        if z._file:
            path = Path(z._file)
            icon, ic = _FILE_ICONS.get(_cat(path), _FILE_ICONS["unknown"])
            p.setFont(QFont("Segoe UI Emoji" if _OS == "Windows" else "Arial", 12))
            p.setPen(QPen(qcol(ic), 1))
            p.drawText(QRectF(8, 0, 30, H), Qt.AlignmentFlag.AlignCenter, icon)
            p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            p.setPen(QPen(qcol(C.WHITE), 1))
            name = path.name if len(path.name) <= 30 else path.name[:27] + "…"
            p.drawText(QRectF(44, 0, W - 70, H),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
            p.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            p.setPen(QPen(qcol(C.RED, 170), 1))
            p.drawText(QRectF(W - 22, 0, 18, H), Qt.AlignmentFlag.AlignCenter, "✕")
        else:
            p.setFont(QFont("Segoe UI", 8))
            p.setPen(QPen(qcol(C.PRI_DIM if not z._hover else C.TEXT_MED), 1))
            p.drawText(QRectF(0, 0, W, H), Qt.AlignmentFlag.AlignCenter,
                       "📎  Arrastrá un archivo o hacé clic")

    def mousePressEvent(self, e):
        z = self._z
        if z._file and e.pos().x() > self.width() - 22:
            z.clear_file()
        else:
            z.mousePressEvent(e)


def _get_chrome_profiles() -> list[tuple[str, str]]:
    """Returns list of (display_label, dir_name) tuples from Chrome User Data."""
    profiles: list[tuple[str, str]] = []
    try:
        user_data = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
        if not user_data.exists():
            return [("Default", "Default")]
        for item in user_data.iterdir():
            if not item.is_dir():
                continue
            if item.name != "Default" and not item.name.startswith("Profile"):
                continue
            prefs_file = item / "Preferences"
            if not prefs_file.exists():
                continue
            try:
                prefs = json.loads(prefs_file.read_text("utf-8", errors="ignore"))
                name  = prefs.get("profile", {}).get("name", item.name)
                accounts = prefs.get("account_info", [])
                email = accounts[0].get("email", "") if accounts else ""
                label = f"{name}  ({email})" if email else name
                profiles.append((label, item.name))
            except Exception:
                profiles.append((item.name, item.name))
    except Exception:
        pass
    if not profiles:
        return [("Default", "Default")]
    return sorted(profiles, key=lambda x: (x[1] != "Default", x[1]))


# ═══════════════════════════════════════════════════════════
# CONSOLE DIALOG  — log viewer para modo sin consola
# ═══════════════════════════════════════════════════════════
class ConsoleDialog(QWidget):
    """Muestra nexo.log en tiempo real. Se abre desde el header."""
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40); shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 200))
        self.setGraphicsEffect(shadow)

        self.setStyleSheet(f"""
            ConsoleDialog {{
                background: #000d14;
                border: 1px solid {C.BORDER_A};
                border-radius: 20px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(8)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("▸  CONSOLA  /  nexo.log")
        title.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{C.PRI}; background:transparent; letter-spacing:2px;")
        hdr.addWidget(title)
        hdr.addStretch()

        clear_btn = QPushButton("🗑")
        clear_btn.setFixedSize(24, 24)
        clear_btn.setFont(QFont("Segoe UI Emoji", 10))
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setToolTip("Limpiar log")
        clear_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#444;border:none;border-radius:12px;}"
            "QPushButton:hover{color:#ff3355;background:rgba(255,51,85,0.15);}")
        clear_btn.clicked.connect(self._clear_log)
        hdr.addWidget(clear_btn)

        cb = QPushButton("✕")
        cb.setFixedSize(24, 24)
        cb.setFont(QFont("Segoe UI", 10))
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.setStyleSheet(
            "QPushButton{background:transparent;color:#444;border:none;border-radius:12px;}"
            "QPushButton:hover{color:#ff3355;background:rgba(255,51,85,0.15);}")
        cb.clicked.connect(self.hide)
        hdr.addWidget(cb)
        root.addLayout(hdr)

        # Log text area
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 8))
        self._log.setStyleSheet(f"""
            QTextEdit {{
                background: #000a10; color: #00cc88;
                border: 1px solid {C.BORDER}; border-radius: 10px;
                padding: 8px;
            }}
            QScrollBar:vertical {{ width: 4px; background: #000; }}
            QScrollBar::handle:vertical {{ background: #1a5070; border-radius: 2px; }}
        """)
        root.addWidget(self._log, stretch=1)

        # Auto-refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(1500)
        self._last_size = 0

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh()
        self._refresh_timer.start(1500)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._refresh_timer.stop()

    def _refresh(self):
        log_path = BASE_DIR / "nexo.log"
        if not log_path.exists():
            return
        try:
            sz = log_path.stat().st_size
            if sz == self._last_size:
                return
            self._last_size = sz
            text = log_path.read_text(encoding="utf-8", errors="replace")
            # Limit to last 500 lines
            lines = text.splitlines()
            if len(lines) > 500:
                lines = lines[-500:]
            self._log.setPlainText("\n".join(lines))
            sb = self._log.verticalScrollBar()
            sb.setValue(sb.maximum())
        except Exception:
            pass

    def _clear_log(self):
        log_path = BASE_DIR / "nexo.log"
        try:
            log_path.write_text("", encoding="utf-8")
            self._last_size = 0
            self._log.clear()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
# DEVICE SETTINGS DIALOG  — tabbed, full-featured panel
# ═══════════════════════════════════════════════════════════
_VOICES = [
    ("Charon", "Masculina", "Profunda y autoritaria  ✨ Recomendada"),
    ("Aoede",  "Femenina",  "Cálida y sofisticada"),
    ("Kore",   "Femenina",  "Suave y precisa"),
    ("Leda",   "Femenina",  "Natural y fluida"),
    ("Zephyr", "Femenina",  "Dinámica y expresiva"),
    ("Puck",   "Masculina", "Ágil y versátil"),
    ("Fenrir", "Masculina", "Grave y autoritaria"),
    ("Orus",   "Masculina", "Clásica y equilibrada"),
]

class DeviceSettingsDialog(QWidget):
    closed       = pyqtSignal()
    config_saved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._load_config()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(50)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 220))
        self.setGraphicsEffect(shadow)

        self.setStyleSheet(f"""
            DeviceSettingsDialog {{
                background: #000a14;
                border: 1px solid {C.BORDER_A};
                border-radius: 24px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ────────────────────────────────────────
        hdr_w = QWidget()
        hdr_w.setFixedHeight(52)
        hdr_w.setStyleSheet(
            f"background:#000d18; border-radius:24px 24px 0 0;"
            f"border-bottom:1px solid {C.BORDER};")
        hdr_lay = QHBoxLayout(hdr_w)
        hdr_lay.setContentsMargins(22, 0, 14, 0)
        hdr_lay.setSpacing(8)

        title_lbl = QLabel("⚙  CONFIGURACIÓN")
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color:#ffffff; background:transparent; letter-spacing:3px;")
        hdr_lay.addWidget(title_lbl)
        hdr_lay.addStretch()

        _cb = QPushButton("✕")
        _cb.setFixedSize(28, 28)
        _cb.setFont(QFont("Segoe UI", 11))
        _cb.setCursor(Qt.CursorShape.PointingHandCursor)
        _cb.setStyleSheet(
            "QPushButton{background:transparent;color:#444;border:none;border-radius:14px;}"
            "QPushButton:hover{color:#ff3355;background:rgba(255,51,85,0.18);}")
        _cb.clicked.connect(self.hide)
        hdr_lay.addWidget(_cb)
        root.addWidget(hdr_w)

        # ── Tab bar ───────────────────────────────────────────
        TABS = [
            ("🛡", "General"),
            ("🎙", "Audio & Voz"),
            ("🌐", "Google"),
            ("🔗", "APIs"),
            ("♿", "Accesibilidad"),
            ("⚡", "Automatizaciones"),
        ]
        tab_bar_w = QWidget()
        tab_bar_w.setFixedHeight(46)
        tab_bar_w.setStyleSheet(
            f"background:#000d18; border-bottom:1px solid {C.BORDER};")
        tab_bar_lay = QHBoxLayout(tab_bar_w)
        tab_bar_lay.setContentsMargins(18, 6, 18, 6)
        tab_bar_lay.setSpacing(5)

        self._tab_btns: list[QPushButton] = []
        self._pages = QStackedWidget()
        self._pages.setStyleSheet("background:transparent;")

        _tab_style = f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid transparent; border-radius: 14px;
                padding: 0 13px; font-size: 8pt; font-weight: bold;
            }}
            QPushButton:checked {{
                background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM};
            }}
            QPushButton:hover:!checked {{
                background: rgba(255,255,255,0.04); color:#aaa;
            }}
        """
        for i, (icon, label) in enumerate(TABS):
            b = QPushButton(f"{icon}  {label}")
            b.setCheckable(True)
            b.setFixedHeight(28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_tab_style)
            b.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            self._tab_btns.append(b)
            tab_bar_lay.addWidget(b)
        tab_bar_lay.addStretch()
        root.addWidget(tab_bar_w)

        # Build all pages
        self._pages.addWidget(self._build_page_general())
        self._pages.addWidget(self._build_page_audio())
        self._pages.addWidget(self._build_page_google())
        self._pages.addWidget(self._build_page_apis())
        self._pages.addWidget(self._build_page_accessibility())
        self._pages.addWidget(self._build_page_automations())
        root.addWidget(self._pages, stretch=1)

        # ── Save bar ─────────────────────────────────────────
        save_bar = QWidget()
        save_bar.setFixedHeight(56)
        save_bar.setStyleSheet(
            f"background:#000d18; border-top:1px solid {C.BORDER};"
            f"border-radius:0 0 24px 24px;")
        save_lay = QHBoxLayout(save_bar)
        save_lay.setContentsMargins(22, 0, 22, 0)

        hint_lbl = QLabel("Los cambios se aplican al guardar y reiniciar la sesión de voz")
        hint_lbl.setFont(QFont("Segoe UI", 7))
        hint_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent;")
        save_lay.addWidget(hint_lbl)
        save_lay.addStretch()

        save_btn = QPushButton("💾  Guardar")
        save_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        save_btn.setFixedHeight(34)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 17px;
                padding: 0 20px;
            }}
            QPushButton:hover {{ background:{C.PRI}; color:#000; border-color:{C.PRI}; }}
        """)
        save_btn.clicked.connect(self._save)
        save_lay.addWidget(save_btn)
        root.addWidget(save_bar)

        self._switch_tab(0)

    # ── Shared widget builders ────────────────────────────
    def _s_scroll_page(self) -> tuple:
        """Return (QScrollArea, form QVBoxLayout) for a tab page."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 4px; background: #000; }
            QScrollBar::handle:vertical { background: #1a5070; border-radius: 2px; }
        """)
        form_w = QWidget()
        form_w.setStyleSheet("background: transparent;")
        form = QVBoxLayout(form_w)
        form.setContentsMargins(14, 8, 14, 8)
        form.setSpacing(5)
        scroll.setWidget(form_w)
        return scroll, form

    def _build_theme_selector(self) -> QWidget:
        """Build colored swatch buttons for each available theme."""
        container = QWidget()
        container.setStyleSheet("background:transparent;")
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 2, 0, 4)
        vlay.setSpacing(4)

        # Current theme
        current = self._cfg.get("nexo_theme", "cyan")

        # Swatch row
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(10)

        self._theme_swatches: dict[str, QPushButton] = {}

        for key, (label, color) in THEME_LABELS.items():
            btn = QPushButton()
            btn.setFixedSize(48, 48)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(label)
            active = (key == current)
            border = f"3px solid #ffffff" if active else f"2px solid {color}55"
            btn.setStyleSheet(
                f"QPushButton{{background:{color}; border:{border}; border-radius:8px;}}"
                f"QPushButton:hover{{border:3px solid {color}; border-radius:8px;}}"
            )
            btn.clicked.connect(lambda _checked, k=key: self._apply_theme(k))
            swatch_row.addWidget(btn)
            self._theme_swatches[key] = btn

        swatch_row.addStretch()
        vlay.addLayout(swatch_row)

        # Label row
        label_row = QHBoxLayout()
        label_row.setSpacing(10)
        for key, (label, color) in THEME_LABELS.items():
            lbl = QLabel(label)
            lbl.setFixedWidth(48)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFont(QFont("Segoe UI", 7))
            active = (key == current)
            lbl.setStyleSheet(
                f"color:{'#ffffff' if active else color}; background:transparent;"
                f"font-weight:{'bold' if active else 'normal'};"
            )
            label_row.addWidget(lbl)
            # keep ref for highlight update
            btn = self._theme_swatches[key]
            btn._label_widget = lbl   # type: ignore[attr-defined]

        label_row.addStretch()
        vlay.addLayout(label_row)

        restart_note = QLabel("✦  El tema se aplica al instante. Guardá para que persista.")
        restart_note.setFont(QFont("Segoe UI", 8))
        restart_note.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent;")
        vlay.addWidget(restart_note)

        return container

    def _apply_theme(self, name: str):
        """Save theme choice, update swatch highlights, apply global stylesheet immediately."""
        if name not in THEMES:
            return
        # Update swatch borders / label weights
        for key, btn in self._theme_swatches.items():
            color = THEME_LABELS[key][1]
            active = (key == name)
            btn.setStyleSheet(
                f"QPushButton{{background:{color}; "
                f"border:{'3px solid #ffffff' if active else f'2px solid {color}55'}; "
                f"border-radius:8px;}}"
                f"QPushButton:hover{{border:3px solid {color}; border-radius:8px;}}"
            )
            if hasattr(btn, "_label_widget"):
                lbl = btn._label_widget
                lbl.setStyleSheet(
                    f"color:{'#ffffff' if active else color}; background:transparent;"
                    f"font-weight:{'bold' if active else 'normal'};"
                )
        # Persist to config immediately (write to disk NOW, before anything reads it)
        self._cfg["nexo_theme"] = name
        _save_theme(name)                          # ← write to disk first
        # 1. Mutate C.* attributes directly from THEMES dict (no disk re-read)
        for attr, val in THEMES[name].items():
            setattr(C, attr, val)
        # 2. Rebuild orb state colors from new C.PRI
        try:
            _refresh_orb_colors()
        except Exception:
            pass
        # 3. Apply comprehensive QApplication stylesheet + force repaint all widgets
        try:
            app = QApplication.instance()
            _apply_theme_stylesheet(app, name)
            # Also repaint this dialog explicitly
            self.update()
        except Exception:
            pass

    # ── Improvement 1: Auto-start with Windows ────────────────────────────────
    @staticmethod
    def _autostart_reg_key() -> str:
        return "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"

    @staticmethod
    def _autostart_name() -> str:
        return "NEXO"

    def _is_autostart_enabled(self) -> bool:
        """Check if NEXO is registered to start with Windows."""
        try:
            import subprocess as _sp
            r = _sp.run(
                ["reg", "query", self._autostart_reg_key(),
                 "/v", self._autostart_name()],
                capture_output=True, creationflags=0x08000000, timeout=5,
            )
            return r.returncode == 0
        except Exception:
            return False

    def _set_autostart(self, enable: bool):
        """Add or remove the Windows startup registry entry for NEXO."""
        import subprocess as _sp
        key   = self._autostart_reg_key()
        name  = self._autostart_name()
        if enable:
            # Find pythonw.exe in the venv next to main.py
            base = Path(__file__).resolve().parent
            pythonw = base / ".venv" / "Scripts" / "pythonw.exe"
            py      = base / ".venv" / "Scripts" / "python.exe"
            launcher = pythonw if pythonw.exists() else (py if py.exists() else None)
            main_py  = base / "main.py"
            if launcher and main_py.exists():
                cmd = f'"{launcher}" "{main_py}"'
                _sp.run(
                    ["reg", "add", key, "/v", name, "/t", "REG_SZ", "/d", cmd, "/f"],
                    capture_output=True, creationflags=0x08000000, timeout=10,
                )
                print(f"[Settings] ✅ Auto-inicio activado: {cmd}")
            else:
                print("[Settings] ⚠ No se encontró python en .venv para auto-inicio")
        else:
            _sp.run(
                ["reg", "delete", key, "/v", name, "/f"],
                capture_output=True, creationflags=0x08000000, timeout=10,
            )
            print("[Settings] ⏹ Auto-inicio desactivado")

    def _create_desktop_shortcut(self):
        """Create a desktop shortcut in a background thread — never blocks the Qt main thread."""
        # Disable button to prevent double-clicks while working
        self._shortcut_btn.setEnabled(False)
        orig_text = self._shortcut_btn.text()
        self._shortcut_btn.setText("  Creando acceso directo…")

        def _worker():
            """Runs on a daemon thread — no Qt calls allowed here directly."""
            import sys as _sys
            import platform as _plat
            import subprocess as _sp
            import traceback as _tb

            ok  = False
            msg = "Error desconocido"

            try:
                base   = Path(__file__).resolve().parent
                system = _plat.system()

                # ── Find Desktop folder ─────────────────────────────────────────
                desktop = Path.home() / "Desktop"
                if not desktop.exists():
                    desktop = Path.home() / "OneDrive" / "Desktop"
                if not desktop.exists():
                    desktop = Path.home()
                desktop.mkdir(parents=True, exist_ok=True)

                if system == "Windows":
                    # ── Find launcher (prefer pythonw — no console flash) ────────
                    pythonw  = base / ".venv" / "Scripts" / "pythonw.exe"
                    python_  = base / ".venv" / "Scripts" / "python.exe"
                    launcher = (
                        pythonw  if pythonw.exists()  else
                        python_  if python_.exists()  else
                        Path(_sys.executable)
                    )
                    main_py  = base / "main.py"
                    lnk_path = desktop / "NEXO.lnk"

                    # ── Find icon ────────────────────────────────────────────────
                    icon_path = None
                    for _ic in [
                        base / "assets" / "nexo.ico",
                        base / "nexo_icono.ico",
                        base / "icon.ico",
                    ]:
                        if _ic.exists():
                            icon_path = _ic
                            break

                    # ── VBScript via cscript.exe — works on ALL Windows,
                    #    zero execution-policy issues, no PATH dependency ─────────
                    import tempfile as _tmp
                    _icon_line = f'oLink.IconLocation = "{icon_path},0"' if icon_path else ""
                    _vbs = (
                        f'Set oWS = WScript.CreateObject("WScript.Shell")\n'
                        f'Set oLink = oWS.CreateShortcut("{lnk_path}")\n'
                        f'oLink.TargetPath = "{launcher}"\n'
                        f'oLink.Arguments = Chr(34) & "{main_py}" & Chr(34)\n'
                        f'oLink.WorkingDirectory = "{base}"\n'
                        f'{_icon_line}\n'
                        f'oLink.Save\n'
                    )
                    with _tmp.NamedTemporaryFile(
                        mode="w", suffix=".vbs", delete=False, encoding="utf-8"
                    ) as _f:
                        _f.write(_vbs)
                        _vbs_path = _f.name

                    _cscript = r"C:\Windows\System32\cscript.exe"
                    try:
                        result = _sp.run(
                            [_cscript, "//NoLogo", "//B", _vbs_path],
                            capture_output=True, timeout=10,
                            creationflags=0x08000000,
                        )
                    finally:
                        try:
                            Path(_vbs_path).unlink(missing_ok=True)
                        except Exception:
                            pass

                    if result.returncode == 0 and lnk_path.exists():
                        ok  = True
                        msg = f"Acceso directo de NEXO creado en:\n{lnk_path}"
                    else:
                        err = (result.stderr or b"").decode("utf-8", errors="replace").strip()
                        msg = f"cscript salió con código {result.returncode}:\n{err[:400]}"

                elif system == "Darwin":
                    py_bin   = base / ".venv" / "bin" / "python3"
                    launcher = str(py_bin) if py_bin.exists() else "python3"
                    app_script = desktop / "NEXO.command"
                    app_script.write_text(
                        f'#!/bin/bash\ncd "{base}"\n"{launcher}" "{base}/main.py"\n',
                        encoding="utf-8"
                    )
                    app_script.chmod(0o755)
                    ok  = True
                    msg = (
                        f"Script NEXO.command creado en:\n{app_script}\n\n"
                        "Hacé doble clic para iniciar NEXO."
                    )

                else:
                    # Linux .desktop
                    py_bin   = base / ".venv" / "bin" / "python3"
                    launcher = str(py_bin) if py_bin.exists() else "python3"
                    icon_path_l = base / "assets" / "nexo.ico"
                    icon_str    = str(icon_path_l) if icon_path_l.exists() else "utilities-terminal"
                    desktop_file = desktop / "NEXO.desktop"
                    desktop_file.write_text(
                        "[Desktop Entry]\nVersion=1.0\nType=Application\n"
                        f"Name=NEXO\nComment=NEXO AI Assistant\n"
                        f'Exec="{launcher}" "{base}/main.py"\n'
                        f"Icon={icon_str}\n"
                        "Terminal=false\nCategories=Utility;\n",
                        encoding="utf-8"
                    )
                    desktop_file.chmod(0o755)
                    ok  = True
                    msg = f"Archivo .desktop creado en:\n{desktop_file}"

            except Exception as _e:
                ok  = False
                msg = f"{_e}\n\n{_tb.format_exc()[-600:]}"
                print(f"[Settings] shortcut error:\n{_tb.format_exc()}")

            # ── Deliver result back to the Qt main thread safely ─────────────────
            def _finish():
                try:
                    self._shortcut_btn.setEnabled(True)
                    self._shortcut_btn.setText(orig_text)
                    if ok:
                        QMessageBox.information(self, "✅ Acceso directo creado", msg)
                    else:
                        QMessageBox.warning(self, "Error al crear acceso directo", msg)
                except Exception:
                    pass   # widget may have been closed

            QTimer.singleShot(0, _finish)

        threading.Thread(target=_worker, daemon=True).start()

    def _s_section(self, title: str) -> QWidget:
        f = QWidget()
        f.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(0, 4, 0, 1)
        lay.setSpacing(8)
        lbl = QLabel(title)
        lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{C.PRI}; background:transparent; letter-spacing:2px;")
        lay.addWidget(lbl)
        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background:{C.BORDER}; border:none; max-height:1px;")
        lay.addWidget(line, stretch=1)
        return f

    def _s_field(self, label_text: str, widget, label_w=120) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(label_text)
        lbl.setFont(QFont("Segoe UI", 9))
        lbl.setStyleSheet(f"color:#cccccc; background:transparent;")
        lbl.setFixedWidth(label_w)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(lbl)
        row.addWidget(widget, stretch=1)
        return row

    def _s_combo(self, items: list, current=None) -> QComboBox:
        c = QComboBox()
        c.addItems(items)
        c.setFont(QFont("Segoe UI", 9))
        c.setStyleSheet(f"""
            QComboBox {{
                background:#080808; color:#ffffff;
                border:1px solid {C.BORDER_A}; border-radius:12px;
                padding:2px 10px; min-height:24px;
            }}
            QComboBox:hover {{ border:1px solid {C.PRI}; }}
            QComboBox::drop-down {{ border:none; width:22px; }}
            QComboBox::down-arrow {{ image:none; }}
            QComboBox QAbstractItemView {{
                background:#080808; color:#ffffff;
                border:1px solid {C.BORDER_A}; border-radius:8px;
                selection-background-color:{C.PRI_GHO};
            }}
        """)
        if current is not None and current in items:
            c.setCurrentText(current)
        elif items:
            c.setCurrentIndex(0)
        return c

    def _s_line(self, value="", placeholder="", password=False) -> QLineEdit:
        le = QLineEdit(str(value))
        le.setFont(QFont("Segoe UI", 9))
        le.setPlaceholderText(placeholder)
        if password:
            le.setEchoMode(QLineEdit.EchoMode.Password)
        le.setStyleSheet(f"""
            QLineEdit {{
                background:#080808; color:#ffffff;
                border:1px solid {C.BORDER_A}; border-radius:14px;
                padding:3px 12px; min-height:28px;
            }}
            QLineEdit:focus {{ border:1px solid {C.PRI}; }}
        """)
        return le

    def _s_check(self, label: str, checked: bool) -> QCheckBox:
        cb = QCheckBox(label)
        cb.setChecked(checked)
        cb.setFont(QFont("Segoe UI", 9))
        cb.setStyleSheet(f"""
            QCheckBox {{ color:{C.TEXT_MED}; background:transparent; }}
            QCheckBox::indicator {{ width:18px; height:18px; border-radius:4px; }}
            QCheckBox::indicator:checked {{ background:{C.PRI}; border:1px solid {C.PRI}; }}
            QCheckBox::indicator:unchecked {{ background:#0d2540; border:1px solid {C.BORDER}; }}
        """)
        return cb

    # ── Tab switching ──────────────────────────────────────
    def _switch_tab(self, idx: int):
        self._pages.setCurrentIndex(idx)
        for i, b in enumerate(self._tab_btns):
            b.setChecked(i == idx)

    # ── Page builders ──────────────────────────────────────
    def _build_page_general(self) -> QWidget:
        scroll, form = self._s_scroll_page()

        form.addWidget(self._s_section("🔑  GEMINI API"))
        self._key_input = self._s_line(self._cfg.get("gemini_api_key", ""), "AIza...", password=True)
        key_row = QHBoxLayout()
        key_row.setSpacing(6)
        _key_lbl = QLabel("API Key")
        _key_lbl.setFont(QFont("Segoe UI", 9))
        _key_lbl.setFixedWidth(110)
        _key_lbl.setStyleSheet("color:#ccc; background:transparent;")
        key_row.addWidget(_key_lbl)
        key_row.addWidget(self._key_input, stretch=1)
        eye = QPushButton("👁")
        eye.setFixedSize(28, 28)
        eye.setCheckable(True)
        eye.setFont(QFont("Segoe UI Emoji", 11))
        eye.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#444;}"
            "QPushButton:hover{color:#00d4ff;}"
            "QPushButton:checked{color:#00d4ff;}")
        eye.setCursor(Qt.CursorShape.PointingHandCursor)
        eye.toggled.connect(
            lambda on: self._key_input.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        key_row.addWidget(eye)
        form.addLayout(key_row)

        key_hint = QLabel("Obtén tu clave gratuita en aistudio.google.com/apikey")
        key_hint.setFont(QFont("Segoe UI", 7))
        key_hint.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; padding:0 0 4px 120px;")
        form.addWidget(key_hint)

        # ── Theme / Color ──────────────────────────────────────────────────────
        form.addWidget(self._s_section("🎨  TEMA DE COLOR"))
        form.addWidget(self._build_theme_selector())

        form.addWidget(self._s_section("🌍  REGIÓN E IDIOMA"))
        timezones = [
            "America/Argentina/Buenos_Aires","America/Mexico_City","America/Bogota",
            "America/Santiago","America/Lima","America/Caracas","America/New_York",
            "America/Chicago","America/Denver","America/Los_Angeles",
            "Europe/Madrid","Europe/London","Europe/Paris","Europe/Berlin",
            "Asia/Tokyo","Asia/Shanghai","Australia/Sydney",
        ]
        self._tz_combo = self._s_combo(timezones, self._cfg.get("timezone","America/Argentina/Buenos_Aires"))
        form.addLayout(self._s_field("Zona horaria", self._tz_combo))

        self._lang_input = self._s_line(self._cfg.get("language","es-ES"), "es-ES, en-US…")
        form.addLayout(self._s_field("Idioma", self._lang_input))

        self._os_combo = self._s_combo(["windows","mac","linux"], self._cfg.get("os_system","windows"))
        form.addLayout(self._s_field("Sistema OP", self._os_combo))

        form.addWidget(self._s_section("🔊  SONIDOS"))
        self._thinking_sound_cb = self._s_check(
            "Sonido de carga mientras NEXO piensa / analiza",
            self._cfg.get("thinking_sound", True))
        form.addWidget(self._thinking_sound_cb)

        # ── IMPROVEMENT 1: Auto-start with Windows ────────────────────────────
        form.addWidget(self._s_section("🚀  INICIO AUTOMÁTICO"))
        _autostart_active = self._is_autostart_enabled()
        self._autostart_cb = self._s_check(
            "Iniciar NEXO automáticamente con Windows", _autostart_active)
        form.addWidget(self._autostart_cb)
        _as_hint = QLabel("NEXO se iniciará en segundo plano al encender la PC.")
        _as_hint.setFont(QFont("Segoe UI", 8))
        _as_hint.setStyleSheet("color:#5a7a8a; margin-left:22px;")
        form.addWidget(_as_hint)

        # ── IMPROVEMENT: Desktop Shortcut ─────────────────────────────────────
        form.addWidget(self._s_section("🖥️  ACCESO DIRECTO"))
        _shortcut_row = QHBoxLayout()
        _shortcut_row.setContentsMargins(0, 0, 0, 0)
        _shortcut_row.setSpacing(10)
        self._shortcut_btn = QPushButton("  Crear acceso directo en el escritorio")
        try:
            self._shortcut_btn.setIcon(self.style().standardIcon(
                QStyle.StandardPixmap.SP_DesktopIcon))
        except Exception:
            pass   # Icon optional — button still works without it
        self._shortcut_btn.setFixedHeight(34)
        self._shortcut_btn.setFont(QFont("Segoe UI", 9))
        self._shortcut_btn.setStyleSheet(
            f"QPushButton{{background:{C.PRI}22; border:1.5px solid {C.PRI}; "
            f"border-radius:7px; color:{C.PRI}; padding:0 16px;}}"
            f"QPushButton:hover{{background:{C.PRI}44;}}"
            f"QPushButton:pressed{{background:{C.PRI}66;}}"
        )
        self._shortcut_btn.clicked.connect(lambda: self._create_desktop_shortcut())
        _shortcut_row.addWidget(self._shortcut_btn)
        _shortcut_row.addStretch()
        _sc_wrap = QWidget(); _sc_wrap.setLayout(_shortcut_row)
        form.addWidget(_sc_wrap)
        _sc_hint = QLabel("Crea un icono de NEXO en el escritorio en cualquier momento.")
        _sc_hint.setFont(QFont("Segoe UI", 8))
        _sc_hint.setStyleSheet("color:#5a7a8a; margin-left:22px;")
        form.addWidget(_sc_hint)

        form.addWidget(self._s_section("👁  GUARDIAN DE VISIÓN"))
        _vg_state = False   # Desactivado por defecto — el usuario lo activa manualmente
        try:
            import json as _json
            from pathlib import Path as _Path
            _vg_cfg = _Path(__file__).resolve().parent / "config" / "vision_guardian_state.json"
            _vg_state = _json.loads(_vg_cfg.read_text()).get("enabled", False)
        except Exception:
            pass
        self._vision_guardian_cb = self._s_check(
            "Monitoreo ambiental de pantalla (NEXO observa y ofrece ayuda proactiva)",
            _vg_state)
        form.addWidget(self._vision_guardian_cb)

        _vg_hint = QLabel("NEXO analiza tu pantalla periódicamente con IA y te avisa si detecta algo importante.")
        _vg_hint.setFont(QFont("Segoe UI", 8))
        _vg_hint.setStyleSheet("color:#5a7a8a; margin-left:22px;")
        _vg_hint.setWordWrap(True)
        form.addWidget(_vg_hint)

        form.addWidget(self._s_section("📷  CÁMARA"))
        self._cam_index = self._s_line(str(self._cfg.get("camera_index", 0)), "0")
        form.addLayout(self._s_field("Índice cámara", self._cam_index))

        # ── Modelos IA ────────────────────────────────────────────────────────
        form.addWidget(self._s_section("🤖  MODELOS IA"))

        self._ollama_enabled_cb = self._s_check(
            "Habilitar Ollama (modelo local — funciona sin internet)",
            self._cfg.get("ollama_enabled", False))
        form.addWidget(self._ollama_enabled_cb)

        _ollama_hint = QLabel(
            "Ollama permite usar LLMs locales (Llama, Mistral, etc.) como alternativa o "
            "respaldo cuando Gemini no está disponible. Descargá Ollama en ollama.ai")
        _ollama_hint.setFont(QFont("Segoe UI", 8))
        _ollama_hint.setStyleSheet(f"color:{C.TEXT_DIM}; margin-left:22px;")
        _ollama_hint.setWordWrap(True)
        form.addWidget(_ollama_hint)

        self._ollama_url = self._s_line(
            self._cfg.get("ollama_base_url", "http://localhost:11434"),
            "http://localhost:11434")
        form.addLayout(self._s_field("URL Ollama", self._ollama_url))

        self._ollama_model_input = self._s_line(
            self._cfg.get("ollama_model", "llama3.2"), "llama3.2")
        form.addLayout(self._s_field("Modelo Ollama", self._ollama_model_input))

        # Test Ollama connection button
        _ollama_test_row = QHBoxLayout()
        _ollama_test_row.setContentsMargins(0, 0, 0, 0)
        self._ollama_status_lbl = QLabel("●  No verificado")
        self._ollama_status_lbl.setFont(QFont("Segoe UI", 8))
        self._ollama_status_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent;")
        _ollama_test_btn = QPushButton("Verificar conexión")
        _ollama_test_btn.setFixedHeight(28)
        _ollama_test_btn.setFont(QFont("Segoe UI", 8))
        _ollama_test_btn.setStyleSheet(
            f"QPushButton{{background:{C.PRI}22; border:1px solid {C.PRI}44; "
            f"border-radius:6px; color:{C.PRI}; padding:0 12px;}}"
            f"QPushButton:hover{{background:{C.PRI}44;}}"
        )
        _ollama_test_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def _test_ollama():
            _ollama_test_btn.setEnabled(False)
            self._ollama_status_lbl.setText("●  Verificando…")
            self._ollama_status_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent;")
            def _run():
                try:
                    from actions.ollama_provider import is_available, list_models
                    ok = is_available()
                    if ok:
                        models = list_models()
                        models_str = ", ".join(models[:5]) if models else "ninguno"
                        msg = f"●  Conectado — modelos: {models_str}"
                        color = "#00ff88"
                    else:
                        msg = "●  No disponible — ¿Ollama está ejecutándose?"
                        color = "#ff6b6b"
                except Exception as e:
                    msg = f"●  Error: {e}"
                    color = "#ff6b6b"
                def _apply():
                    self._ollama_status_lbl.setText(msg)
                    self._ollama_status_lbl.setStyleSheet(f"color:{color}; background:transparent;")
                    _ollama_test_btn.setEnabled(True)
                QTimer.singleShot(0, _apply)
            import threading as _thr
            _thr.Thread(target=_run, daemon=True).start()

        _ollama_test_btn.clicked.connect(_test_ollama)
        _ollama_test_row.addWidget(_ollama_test_btn)
        _ollama_test_row.addWidget(self._ollama_status_lbl)
        _ollama_test_row.addStretch()
        _ollama_test_wrap = QWidget(); _ollama_test_wrap.setLayout(_ollama_test_row)
        form.addWidget(_ollama_test_wrap)

        # Per-task model selectors
        _model_opts = ["gemini", "ollama"]
        self._model_conv  = self._s_combo(_model_opts, self._cfg.get("model_for_conversation", "gemini"))
        self._model_agent = self._s_combo(_model_opts, self._cfg.get("model_for_agents",       "gemini"))
        self._model_search = self._s_combo(_model_opts, self._cfg.get("model_for_search",      "gemini"))
        form.addLayout(self._s_field("Conversación",   self._model_conv,  label_w=140))
        form.addLayout(self._s_field("Tareas agente",  self._model_agent, label_w=140))
        form.addLayout(self._s_field("Búsquedas",      self._model_search, label_w=140))

        _model_hint = QLabel(
            "Gemini requiere conexión a internet. "
            "Ollama funciona localmente (más privado, sin costo de API).")
        _model_hint.setFont(QFont("Segoe UI", 8))
        _model_hint.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent;")
        _model_hint.setWordWrap(True)
        form.addWidget(_model_hint)

        form.addStretch()
        return scroll

    def _build_page_audio(self) -> QWidget:
        scroll, form = self._s_scroll_page()

        # ── Mic + Speaker ──
        try:
            import sounddevice as sd
            devs = sd.query_devices()
            mic_names = [f"{d['name']} (idx {i})" for i, d in enumerate(devs) if d['max_input_channels'] > 0]
            spk_names = [f"{d['name']} (idx {i})" for i, d in enumerate(devs) if d['max_output_channels'] > 0]
        except Exception:
            mic_names = spk_names = ["Por defecto (idx 0)"]

        form.addWidget(self._s_section("🎤  DISPOSITIVOS DE AUDIO"))

        cur_mic_idx = self._cfg.get("mic_device", 0)
        cur_mic = next((n for n in mic_names if f"(idx {cur_mic_idx})" in n), mic_names[0] if mic_names else "Por defecto")
        self._mic_combo = self._s_combo(mic_names or ["Por defecto"], cur_mic)
        form.addLayout(self._s_field("Micrófono", self._mic_combo))

        cur_spk_idx = self._cfg.get("spk_device", 0)
        cur_spk = next((n for n in spk_names if f"(idx {cur_spk_idx})" in n), spk_names[0] if spk_names else "Por defecto")
        self._spk_combo = self._s_combo(spk_names or ["Por defecto"], cur_spk)
        form.addLayout(self._s_field("Altavoz", self._spk_combo))

        # ── Voice selector ──
        form.addWidget(self._s_section("🎭  VOZ DE NEXO"))

        voice_hint = QLabel(
            "Elige la voz que NEXO usará para hablar. "
            "Los cambios aplican en la próxima sesión de audio."
        )
        voice_hint.setFont(QFont("Segoe UI", 8))
        voice_hint.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; padding:0 0 8px;")
        voice_hint.setWordWrap(True)
        form.addWidget(voice_hint)

        cur_voice = self._cfg.get("nexo_voice", "Charon")

        # Voice cards grid (2 per row)
        self._voice_btns: dict[str, QPushButton] = {}
        voice_grid = QWidget()
        voice_grid.setStyleSheet("background:transparent;")
        vg_lay = QVBoxLayout(voice_grid)
        vg_lay.setContentsMargins(0, 0, 0, 0)
        vg_lay.setSpacing(6)

        row_w: QWidget | None = None
        row_l: QHBoxLayout | None = None

        for idx, (name, gender, desc) in enumerate(_VOICES):
            if idx % 2 == 0:
                row_w = QWidget(); row_w.setStyleSheet("background:transparent;")
                row_l = QHBoxLayout(row_w)
                row_l.setContentsMargins(0, 0, 0, 0)
                row_l.setSpacing(6)
                vg_lay.addWidget(row_w)

            is_sel = name == cur_voice
            gender_col = C.PRI if "Femeni" in gender else "#aaa"
            card = QPushButton()
            card.setCheckable(True)
            card.setChecked(is_sel)
            card.setFixedHeight(56)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card_html = f"<b style='font-size:10pt;color:#fff;'>{name}</b><br>" \
                        f"<span style='font-size:7pt;color:{gender_col};'>{gender}</span>" \
                        f"<span style='font-size:7pt;color:#555;'>  ·  {desc}</span>"
            inner_lbl = QLabel(card_html)
            inner_lbl.setWordWrap(True)
            inner_lbl.setStyleSheet("background:transparent; padding:0;")
            inner_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

            card_lay_inner = QVBoxLayout(card)
            card_lay_inner.setContentsMargins(12, 6, 12, 6)
            card_lay_inner.addWidget(inner_lbl)

            card.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255,255,255,0.02);
                    border: 1px solid {C.BORDER};
                    border-radius: 12px; text-align: left;
                }}
                QPushButton:checked {{
                    background: {C.PRI_GHO};
                    border: 1px solid {C.PRI};
                }}
                QPushButton:hover:!checked {{
                    background: rgba(255,255,255,0.05);
                    border: 1px solid {C.BORDER_A};
                }}
            """)
            self._voice_btns[name] = card
            card.toggled.connect(lambda checked, n=name: self._on_voice_selected(n) if checked else None)
            row_l.addWidget(card, stretch=1)

        if len(_VOICES) % 2 != 0 and row_l:
            row_l.addWidget(QWidget(), stretch=1)

        form.addWidget(voice_grid)
        form.addStretch()
        return scroll

    def _on_voice_selected(self, name: str):
        for n, btn in self._voice_btns.items():
            btn.setChecked(n == name)

    def _build_page_google(self) -> QWidget:
        scroll, form = self._s_scroll_page()
        form.addWidget(self._s_section("🌐  CHROME"))

        _chrome_profiles = _get_chrome_profiles()
        _profile_labels  = [p[0] for p in _chrome_profiles]
        self._google_profile_dirs = [p[1] for p in _chrome_profiles]
        _cur_dir = self._cfg.get("chrome_google_profile", "Default")
        _cur_lbl = next(
            (_chrome_profiles[i][0] for i, d in enumerate(self._google_profile_dirs) if d == _cur_dir),
            _profile_labels[0] if _profile_labels else "Default")
        self._google_profile = self._s_combo(_profile_labels, _cur_lbl)
        form.addLayout(self._s_field("Perfil Chrome", self._google_profile))

        self._chrome_path = self._s_line(self._cfg.get("chrome_exe_path",""), "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
        form.addLayout(self._s_field("Chrome EXE", self._chrome_path))

        chrome_hint = QLabel("Ruta completa al ejecutable de Google Chrome.\n"
                             "Usado para automatización web con tu perfil real.")
        chrome_hint.setFont(QFont("Segoe UI", 8))
        chrome_hint.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; padding:4px 0;")
        chrome_hint.setWordWrap(True)
        form.addWidget(chrome_hint)

        form.addStretch()
        return scroll

    def _build_page_apis(self) -> QWidget:
        _is_beta = (BASE_DIR / "beta_config.py").exists()
        scroll, form = self._s_scroll_page()

        form.addWidget(self._s_section("🎵  SPOTIFY"))
        self._spotify_id     = self._s_line(self._cfg.get("spotify_client_id",""), "Client ID")
        self._spotify_secret = self._s_line(self._cfg.get("spotify_client_secret",""), "Client Secret", password=True)
        self._spotify_redirect = self._s_line(self._cfg.get("spotify_redirect_uri","http://127.0.0.1:8888/callback"), "Redirect URI")
        form.addLayout(self._s_field("Client ID", self._spotify_id))
        form.addLayout(self._s_field("Client Secret", self._spotify_secret))
        form.addLayout(self._s_field("Redirect URI", self._spotify_redirect))

        form.addWidget(self._s_section("🎬  TMDB (Películas)"))
        self._tmdb_key = self._s_line(self._cfg.get("tmdb_api_key",""), "API Key", password=True)
        form.addLayout(self._s_field("API Key", self._tmdb_key))

        # Social media APIs — only shown in PRO
        self._tw_key = self._tw_secret = self._tw_at = self._tw_ats = self._tw_bt = None
        self._ig_user = self._ig_pass = None
        if not _is_beta:
            form.addWidget(self._s_section("🐦  TWITTER / X"))
            self._tw_key    = self._s_line(self._cfg.get("twitter_api_key",""), "API Key")
            self._tw_secret = self._s_line(self._cfg.get("twitter_api_secret",""), "API Secret", password=True)
            self._tw_at     = self._s_line(self._cfg.get("twitter_access_token",""), "Access Token")
            self._tw_ats    = self._s_line(self._cfg.get("twitter_access_token_secret",""), "Token Secret", password=True)
            self._tw_bt     = self._s_line(self._cfg.get("twitter_bearer_token",""), "Bearer Token", password=True)
            form.addLayout(self._s_field("API Key", self._tw_key))
            form.addLayout(self._s_field("API Secret", self._tw_secret))
            form.addLayout(self._s_field("Access Token", self._tw_at))
            form.addLayout(self._s_field("Token Secret", self._tw_ats))
            form.addLayout(self._s_field("Bearer Token", self._tw_bt))

            form.addWidget(self._s_section("📸  INSTAGRAM"))
            self._ig_user = self._s_line(self._cfg.get("instagram_username",""), "Usuario")
            self._ig_pass = self._s_line(self._cfg.get("instagram_password",""), "Contraseña", password=True)
            form.addLayout(self._s_field("Usuario", self._ig_user))
            form.addLayout(self._s_field("Contraseña", self._ig_pass))
        else:
            # Beta: show upgrade notice instead
            pro_notice = QLabel(
                "🔒  Twitter / X, Instagram y otras redes sociales\n"
                "     son funciones exclusivas de NEXO PRO."
            )
            pro_notice.setFont(QFont("Segoe UI", 9))
            pro_notice.setStyleSheet(
                "color:#7c3aed; background:rgba(124,58,237,0.08);"
                "border:1px solid rgba(124,58,237,0.3); border-radius:10px;"
                "padding:12px 16px;"
            )
            pro_notice.setWordWrap(True)
            form.addWidget(pro_notice)

        form.addStretch()
        return scroll

    def _build_page_accessibility(self) -> QWidget:
        scroll, form = self._s_scroll_page()

        form.addWidget(self._s_section("♿  ACCESIBILIDAD UNIVERSAL"))
        hint = QLabel(
            "Configuracion para personas con discapacidad motriz, cognitiva, "
            "visual o auditiva. Todas las opciones tambien pueden controlarse "
            "por comando de voz."
        )
        hint.setFont(QFont("Segoe UI", 8))
        hint.setStyleSheet(f"color:{C.TEXT_MED}; background:transparent; padding:4px 0;")
        hint.setWordWrap(True)
        form.addWidget(hint)
        form.addSpacing(10)

        # Load accessibility config
        _acc_path = Path(CONFIG_DIR) / "accessibility_config.json"
        try:
            _acc_cfg = json.loads(_acc_path.read_text("utf-8"))
        except Exception:
            _acc_cfg = {}

        def _acc_get(key: str, default=False):
            return _acc_cfg.get(key, default)

        # Cognitive / Task simplification
        form.addWidget(self._s_section("🧠  APOYO COGNITIVO"))
        self._acc_simplify = QCheckBox("Simplificacion automatica de tareas")
        self._acc_simplify.setChecked(_acc_get("task_simplification_enabled", True))
        self._acc_simplify.setStyleSheet(f"QCheckBox {{ color: {C.TEXT_MED}; }}")
        form.addWidget(self._acc_simplify)

        self._acc_emotion = QCheckBox("Regulacion emocional por tono de voz")
        self._acc_emotion.setChecked(_acc_get("emotional_regulation_enabled", False))
        self._acc_emotion.setStyleSheet(f"QCheckBox {{ color: {C.TEXT_MED}; }}")
        form.addWidget(self._acc_emotion)

        self._acc_routine = QCheckBox("Rutinas diarias gamificadas")
        self._acc_routine.setChecked(_acc_get("routine_gamification_enabled", False))
        self._acc_routine.setStyleSheet(f"QCheckBox {{ color: {C.TEXT_MED}; }}")
        form.addWidget(self._acc_routine)

        form.addSpacing(10)

        # Motor / Movement
        form.addWidget(self._s_section("🦾  CONTROL POR CAMARA"))

        cam_hint = QLabel(
            "Requiere: pip install opencv-python\n"
            "Activá la opcion y guardá — NEXO iniciará el seguimiento automaticamente."
        )
        cam_hint.setFont(QFont("Segoe UI", 8))
        cam_hint.setStyleSheet(f"color:{C.TEXT_DIM}; background:rgba(0,212,255,0.04);"
                               f"border:1px solid {C.BORDER}; border-radius:6px; padding:6px;")
        cam_hint.setWordWrap(True)
        form.addWidget(cam_hint)
        form.addSpacing(4)

        # Eye tracking row
        eye_row = QHBoxLayout()
        self._acc_eye = QCheckBox("Seguimiento ocular")
        self._acc_eye.setChecked(_acc_get("eye_tracking_enabled", False))
        self._acc_eye.setStyleSheet(f"QCheckBox {{ color: {C.TEXT_MED}; font-weight:bold; }}")
        eye_row.addWidget(self._acc_eye)
        eye_desc = QLabel("  —  mover ojos para controlar el cursor")
        eye_desc.setStyleSheet(f"color:{C.TEXT_DIM}; font-size:9px;")
        eye_row.addWidget(eye_desc)
        eye_row.addStretch()
        # Live status indicator
        self._acc_eye_status = QLabel("⚪ Inactivo")
        self._acc_eye_status.setStyleSheet(f"color:{C.TEXT_DIM}; font-size:9px; font-weight:bold;")
        eye_row.addWidget(self._acc_eye_status)
        form.addLayout(eye_row)

        # Micro movement row
        micro_row = QHBoxLayout()
        self._acc_micro = QCheckBox("Control por gestos de cabeza")
        self._acc_micro.setChecked(_acc_get("micro_movement_enabled", False))
        self._acc_micro.setStyleSheet(f"QCheckBox {{ color: {C.TEXT_MED}; font-weight:bold; }}")
        micro_row.addWidget(self._acc_micro)
        micro_desc = QLabel("  —  inclinar/cabecear para dar comandos")
        micro_desc.setStyleSheet(f"color:{C.TEXT_DIM}; font-size:9px;")
        micro_row.addWidget(micro_desc)
        micro_row.addStretch()
        self._acc_micro_status = QLabel("⚪ Inactivo")
        self._acc_micro_status.setStyleSheet(f"color:{C.TEXT_DIM}; font-size:9px; font-weight:bold;")
        micro_row.addWidget(self._acc_micro_status)
        form.addLayout(micro_row)

        # Gesture reference
        gestures_hint = QLabel(
            "Gestos: asentir = Confirmar/Sí  •  levantar cabeza = Cancelar/No  "
            "•  girar izq. = Anterior  •  girar der. = Siguiente"
        )
        gestures_hint.setFont(QFont("Segoe UI", 8))
        gestures_hint.setStyleSheet(f"color:{C.TEXT_DIM}; padding:2px 0 0 24px;")
        gestures_hint.setWordWrap(True)
        form.addWidget(gestures_hint)

        # Camera preview (live feed when tracking is active)
        cam_container = QWidget()
        cam_vbox = QVBoxLayout(cam_container)
        cam_vbox.setContentsMargins(0, 0, 0, 0)
        cam_vbox.setSpacing(0)

        self._acc_cam_label = QLabel("Camara inactiva")
        self._acc_cam_label.setFixedSize(320, 180)
        self._acc_cam_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._acc_cam_label.setStyleSheet(
            f"background:#020e18; border:1px solid {C.BORDER};"
            f"border-radius:6px 6px 0 0; color:{C.TEXT_DIM}; font-size:10px;"
        )

        self._acc_cam_status_bar = QLabel("⚫  Cámara inactiva")
        self._acc_cam_status_bar.setFixedSize(320, 22)
        self._acc_cam_status_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._acc_cam_status_bar.setStyleSheet(
            "background:#0a1520; border:1px solid #1a2e40; border-top:none;"
            "border-radius:0 0 6px 6px; color:#455a64; font-size:9px; font-weight:bold;"
        )

        cam_vbox.addWidget(self._acc_cam_label)
        cam_vbox.addWidget(self._acc_cam_status_bar)
        form.addWidget(cam_container)

        # Buttons row: Probar + Start Eye + Start Gesture
        cam_btn_row = QHBoxLayout()
        test_btn = QPushButton("🎥  Probar")
        test_btn.setFixedSize(80, 28)
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.setStyleSheet(f"""
            QPushButton {{ background:#0d2540; color:{C.PRI}; border:1px solid {C.PRI};
                border-radius:4px; font-size:9px; }}
            QPushButton:hover {{ background:{C.PRI}; color:#000; }}
        """)
        test_btn.clicked.connect(self._test_camera_accessibility)

        self._btn_acc_start_eye = QPushButton("👁  Activar Eye")
        self._btn_acc_start_eye.setFixedSize(108, 28)
        self._btn_acc_start_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_acc_start_eye.setStyleSheet(f"""
            QPushButton {{ background:#071826; color:{C.PRI}; border:1px solid {C.PRI};
                border-radius:4px; font-size:9px; font-weight:bold; }}
            QPushButton:hover {{ background:{C.PRI}; color:#000; }}
        """)
        self._btn_acc_start_eye.clicked.connect(lambda: self._acc_toggle_eye(self._btn_acc_start_eye))

        self._btn_acc_start_gesture = QPushButton("🤖  Activar Gestos")
        self._btn_acc_start_gesture.setFixedSize(120, 28)
        self._btn_acc_start_gesture.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_acc_start_gesture.setStyleSheet(f"""
            QPushButton {{ background:#071826; color:{C.PRI}; border:1px solid {C.PRI};
                border-radius:4px; font-size:9px; font-weight:bold; }}
            QPushButton:hover {{ background:{C.PRI}; color:#000; }}
        """)
        self._btn_acc_start_gesture.clicked.connect(lambda: self._acc_toggle_gesture(self._btn_acc_start_gesture))

        cam_btn_row.addWidget(test_btn)
        cam_btn_row.addSpacing(6)
        cam_btn_row.addWidget(self._btn_acc_start_eye)
        cam_btn_row.addSpacing(6)
        cam_btn_row.addWidget(self._btn_acc_start_gesture)
        cam_btn_row.addStretch()
        form.addLayout(cam_btn_row)

        # Timer to refresh camera preview from shared frame buffer
        self._acc_cam_timer = None
        self._acc_cam_mode  = None   # "eye" | "micro" | None
        self._acc_live_blink = False  # toggled each refresh for blinking dot

        # Auto-sync: if tracking was already active before dialog opened, restore state
        try:
            from actions.accessibility import _get_eye_tracker, _get_micro_detector
            _et = _get_eye_tracker()
            _md = _get_micro_detector()
            if _et.running:
                self._btn_acc_start_eye.setText("⏹  Detener Eye")
                self._acc_start_camera_preview("eye")
                if hasattr(self, "_acc_eye_status"):
                    self._acc_eye_status.setText("✅ Activo")
                    self._acc_eye_status.setStyleSheet("color:#00e5ff; font-size:9px; font-weight:bold;")
            if _md.running:
                self._btn_acc_start_gesture.setText("⏹  Detener Gestos")
                if not _et.running:
                    self._acc_start_camera_preview("micro")
                if hasattr(self, "_acc_micro_status"):
                    self._acc_micro_status.setText("✅ Activo")
                    self._acc_micro_status.setStyleSheet("color:#ff9800; font-size:9px; font-weight:bold;")
        except Exception:
            pass

        form.addSpacing(10)

        # Speech / Voice
        form.addWidget(self._s_section("🗣  RECONOCIMIENTO DE VOZ"))
        thresh_row = QHBoxLayout()
        label_t = QLabel("Tolerancia para habla no convencional:")
        label_t.setStyleSheet(f"color:{C.TEXT_MED}; font-size:11px;")
        self._acc_threshold = QSlider(Qt.Orientation.Horizontal)
        self._acc_threshold.setRange(1, 10)
        _cur_thresh = int(_acc_get("speech_error_threshold", 0.5) * 10)
        self._acc_threshold.setValue(_cur_thresh)
        self._acc_threshold.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height:4px; background:{C.BORDER}; border-radius:2px; }}
            QSlider::handle:horizontal {{ background:{C.PRI}; width:16px; height:16px;
                margin:-6px 0; border-radius:8px; }}
            QSlider::sub-page:horizontal {{ background:{C.PRI}; border-radius:2px; }}
        """)
        self._acc_threshold_label = QLabel(f"{_cur_thresh / 10:.1f}")
        self._acc_threshold_label.setStyleSheet(f"color:{C.PRI}; font-weight:bold; font-size:11px;")
        self._acc_threshold.valueChanged.connect(
            lambda v: self._acc_threshold_label.setText(f"{v / 10:.1f}")
        )
        thresh_row.addWidget(label_t, stretch=1)
        thresh_row.addWidget(self._acc_threshold)
        thresh_row.addWidget(self._acc_threshold_label)
        form.addLayout(thresh_row)

        form.addSpacing(10)

        # Visual / Feedback
        form.addWidget(self._s_section("👁  FEEDBACK VISUAL"))
        self._acc_visual = QCheckBox("Feedback visual activado")
        self._acc_visual.setChecked(_acc_get("visual_feedback_enabled", True))
        self._acc_visual.setStyleSheet(f"QCheckBox {{ color: {C.TEXT_MED}; }}")
        form.addWidget(self._acc_visual)

        self._acc_contrast = QCheckBox("Modo alto contraste")
        self._acc_contrast.setChecked(_acc_get("high_contrast_mode", False))
        self._acc_contrast.setStyleSheet(f"QCheckBox {{ color: {C.TEXT_MED}; }}")
        form.addWidget(self._acc_contrast)

        font_row = QHBoxLayout()
        label_f = QLabel("Escala de fuente:")
        label_f.setStyleSheet(f"color:{C.TEXT_MED}; font-size:11px;")
        self._acc_font_scale = QComboBox()
        self._acc_font_scale.addItems(["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
        _cur_font = _acc_get("font_size_scale", 1.0)
        self._acc_font_scale.setCurrentText(f"{_cur_font:.2f}x".replace(".", ",") if _cur_font != 1.0 else "1.0x")
        self._acc_font_scale.setStyleSheet(f"""
            QComboBox {{ color:{C.TEXT_MED}; background:#001018; border:1px solid {C.BORDER};
                border-radius:4px; padding:2px 8px; }}
            QComboBox::drop-down {{ border:none; }}
        """)
        font_row.addWidget(label_f)
        font_row.addWidget(self._acc_font_scale)
        font_row.addStretch()
        form.addLayout(font_row)

        form.addSpacing(10)

        # Learning
        form.addWidget(self._s_section("🤖  APRENDIZAJE"))
        self._acc_learn = QCheckBox("Aprendizaje automatico de rutinas")
        self._acc_learn.setChecked(_acc_get("auto_learn_routines", False))
        self._acc_learn.setStyleSheet(f"QCheckBox {{ color: {C.TEXT_MED}; }}")
        form.addWidget(self._acc_learn)

        form.addSpacing(14)

        # ── Blind / Screen reader section ─────────────────────────────────────
        form.addWidget(self._s_section("🦯  LECTOR DE PANTALLA (PERSONAS CIEGAS)"))

        blind_hint = QLabel(
            "Narración de voz inmediata usando el motor TTS de Windows (sin instalar nada).\n"
            "NEXO puede describir la pantalla, clicar elementos por descripción, "
            "escribir, navegar y anunciar cambios de ventana en tiempo real.\n"
            "Comandos de voz: 'describí la pantalla', 'hacé clic en Aceptar', 'activar dwell click'."
        )
        blind_hint.setFont(QFont("Segoe UI", 8))
        blind_hint.setStyleSheet(
            f"color:{C.TEXT_MED}; background:rgba(0,212,255,0.05);"
            f"border:1px solid {C.BORDER}; border-radius:6px; padding:8px;"
        )
        blind_hint.setWordWrap(True)
        form.addWidget(blind_hint)
        form.addSpacing(6)

        # Overlay launch button
        overlay_row = QHBoxLayout()
        self._btn_acc_overlay = QPushButton("♿  Abrir Barra de Accesibilidad")
        self._btn_acc_overlay.setFixedHeight(32)
        self._btn_acc_overlay.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_acc_overlay.setStyleSheet(f"""
            QPushButton {{
                background: #071826;
                color: {C.PRI};
                border: 1px solid {C.PRI};
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
                padding: 0 16px;
            }}
            QPushButton:hover {{ background: {C.PRI}; color: #000; }}
        """)
        self._btn_acc_overlay.clicked.connect(self._launch_accessibility_overlay)
        self._btn_acc_overlay_status = QLabel("⚪ Inactiva")
        self._btn_acc_overlay_status.setStyleSheet(f"color:{C.TEXT_DIM}; font-size:9px; font-weight:bold;")
        overlay_row.addWidget(self._btn_acc_overlay)
        overlay_row.addSpacing(8)
        overlay_row.addWidget(self._btn_acc_overlay_status)
        overlay_row.addStretch()
        form.addLayout(overlay_row)

        overlay_desc = QLabel(
            "La barra flota sobre todas las ventanas con botones: Narrar, Dwell Click, Monitor, Contraste."
        )
        overlay_desc.setFont(QFont("Segoe UI", 8))
        overlay_desc.setStyleSheet(f"color:{C.TEXT_DIM}; padding:2px 0 0 0;")
        overlay_desc.setWordWrap(True)
        form.addWidget(overlay_desc)
        form.addSpacing(8)

        # Screen reader voice test
        tts_row = QHBoxLayout()
        btn_tts_test = QPushButton("🔊  Probar Voz")
        btn_tts_test.setFixedSize(120, 28)
        btn_tts_test.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_tts_test.setStyleSheet(f"""
            QPushButton {{
                background: #0d2540;
                color: {C.PRI};
                border: 1px solid {C.PRI};
                border-radius: 4px;
                font-size: 10px;
            }}
            QPushButton:hover {{ background: {C.PRI}; color: #000; }}
        """)
        btn_tts_test.clicked.connect(self._test_tts_voice)
        tts_row.addWidget(btn_tts_test)
        tts_row.addStretch()
        form.addLayout(tts_row)

        form.addSpacing(12)

        # ── BlindNavigator — AI-powered voice navigation ──────────────────────
        form.addWidget(self._s_section("🦯  NAVEGACIÓN POR VOZ CON IA (CIEGOS)"))

        bnav_hint = QLabel(
            "Habla con NEXO para navegar tu PC: describir pantalla, hacer clic en elementos, "
            "escribir texto, abrir apps, desplazarte y más.\n"
            "Ejemplos: 'describí la pantalla', 'hacé clic en Aceptar', 'abrí Chrome', "
            "'escribí hola mundo', 'scrolleá hacia abajo'.\n"
            "Requiere API Key de Gemini (se configura en Configuración > API Keys)."
        )
        bnav_hint.setFont(QFont("Segoe UI", 8))
        bnav_hint.setStyleSheet(
            f"color:{C.TEXT_MED}; background:rgba(255,180,0,0.05);"
            f"border:1px solid rgba(255,180,0,0.25); border-radius:6px; padding:8px;"
        )
        bnav_hint.setWordWrap(True)
        form.addWidget(bnav_hint)
        form.addSpacing(6)

        # Status + toggle row
        bnav_ctrl_row = QHBoxLayout()
        self._btn_blind_nav = QPushButton("🦯  Activar Navegación Ciegos")
        self._btn_blind_nav.setFixedHeight(32)
        self._btn_blind_nav.setCursor(Qt.CursorShape.PointingHandCursor)
        self._blind_nav_style_off = f"""
            QPushButton {{
                background: #071826;
                color: {C.PRI};
                border: 1px solid {C.PRI};
                border-radius: 6px;
                font-size: 10px;
                font-weight: bold;
                padding: 0 14px;
            }}
            QPushButton:hover {{ background: {C.PRI}; color: #000; }}
        """
        self._blind_nav_style_on = f"""
            QPushButton {{
                background: rgba(255,165,0,0.18);
                color: #ffb300;
                border: 1px solid #ffb300;
                border-radius: 6px;
                font-size: 10px;
                font-weight: bold;
                padding: 0 14px;
            }}
            QPushButton:hover {{ background: #ffb300; color: #000; }}
        """
        self._btn_blind_nav.setStyleSheet(self._blind_nav_style_off)
        self._lbl_blind_nav_status = QLabel("⚪ Inactivo")
        self._lbl_blind_nav_status.setStyleSheet(f"color:{C.TEXT_DIM}; font-size:9px; font-weight:bold;")
        self._btn_blind_nav.clicked.connect(self._toggle_blind_nav)
        bnav_ctrl_row.addWidget(self._btn_blind_nav)
        bnav_ctrl_row.addSpacing(10)
        bnav_ctrl_row.addWidget(self._lbl_blind_nav_status)
        bnav_ctrl_row.addStretch()
        form.addLayout(bnav_ctrl_row)
        form.addSpacing(6)

        # Quick describe button
        bnav_quick_row = QHBoxLayout()
        btn_describe = QPushButton("🖼  Describir Pantalla Ahora")
        btn_describe.setFixedHeight(28)
        btn_describe.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_describe.setStyleSheet(f"""
            QPushButton {{
                background: #0d2540;
                color: {C.PRI};
                border: 1px solid {C.PRI};
                border-radius: 4px;
                font-size: 10px;
                padding: 0 12px;
            }}
            QPushButton:hover {{ background: {C.PRI}; color: #000; }}
        """)
        btn_describe.clicked.connect(self._blind_nav_quick_describe)
        bnav_quick_row.addWidget(btn_describe)
        bnav_quick_row.addStretch()
        form.addLayout(bnav_quick_row)
        form.addSpacing(8)

        # TTS speed slider
        bnav_speed_row = QHBoxLayout()
        lbl_spd = QLabel("Velocidad de voz TTS:")
        lbl_spd.setStyleSheet(f"color:{C.TEXT_MED}; font-size:11px;")
        self._sld_blind_tts_rate = QSlider(Qt.Orientation.Horizontal)
        self._sld_blind_tts_rate.setRange(1, 10)
        _tts_rate_val = int(_acc_get("blind_tts_rate", 0.5) * 10)
        self._sld_blind_tts_rate.setValue(max(1, min(10, _tts_rate_val if _tts_rate_val > 0 else 5)))
        self._sld_blind_tts_rate.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height:4px; background:{C.BORDER}; border-radius:2px; }}
            QSlider::handle:horizontal {{ background:#ffb300; width:16px; height:16px;
                margin:-6px 0; border-radius:8px; }}
            QSlider::sub-page:horizontal {{ background:#ffb300; border-radius:2px; }}
        """)
        self._lbl_blind_tts_rate_val = QLabel(f"{self._sld_blind_tts_rate.value() / 10:.1f}")
        self._lbl_blind_tts_rate_val.setStyleSheet("color:#ffb300; font-weight:bold; font-size:11px;")
        self._sld_blind_tts_rate.valueChanged.connect(
            lambda v: (
                self._lbl_blind_tts_rate_val.setText(f"{v / 10:.1f}"),
                self._blind_nav_set_tts_rate(v),
            )
        )
        bnav_speed_row.addWidget(lbl_spd, stretch=1)
        bnav_speed_row.addWidget(self._sld_blind_tts_rate)
        bnav_speed_row.addWidget(self._lbl_blind_tts_rate_val)
        form.addLayout(bnav_speed_row)

        # Sync button state if BlindNavigator already active
        try:
            bn = getattr(self, "_blind_navigator", None)
            if bn is not None and bn.running:
                self._btn_blind_nav.setText("⏹  Detener Navegación")
                self._btn_blind_nav.setStyleSheet(self._blind_nav_style_on)
                self._lbl_blind_nav_status.setText("✅ Activo")
                self._lbl_blind_nav_status.setStyleSheet("color:#ffb300; font-size:9px; font-weight:bold;")
        except Exception:
            pass

        form.addStretch()
        return scroll

    # ── BlindNavigator helpers ─────────────────────────────────────────────────

    def _toggle_blind_nav(self):
        try:
            from actions.blind_nav import BlindNavigator
            if not hasattr(self, "_blind_navigator") or self._blind_navigator is None:
                api_key = self._get_gemini_api_key()
                self._blind_navigator = BlindNavigator(gemini_api_key=api_key)
            bn = self._blind_navigator
            if bn.running:
                bn.stop()
                self._btn_blind_nav.setText("🦯  Activar Navegación Ciegos")
                self._btn_blind_nav.setStyleSheet(self._blind_nav_style_off)
                self._lbl_blind_nav_status.setText("⚪ Inactivo")
                self._lbl_blind_nav_status.setStyleSheet(f"color:{C.TEXT_DIM}; font-size:9px; font-weight:bold;")
            else:
                bn.start()
                self._btn_blind_nav.setText("⏹  Detener Navegación")
                self._btn_blind_nav.setStyleSheet(self._blind_nav_style_on)
                self._lbl_blind_nav_status.setText("✅ Activo — di un comando")
                self._lbl_blind_nav_status.setStyleSheet("color:#ffb300; font-size:9px; font-weight:bold;")
        except Exception as e:
            if hasattr(self, "_lbl_blind_nav_status"):
                self._lbl_blind_nav_status.setText(f"❌ Error: {e}")
                self._lbl_blind_nav_status.setStyleSheet("color:#f44336; font-size:9px;")

    def _blind_nav_quick_describe(self):
        try:
            from actions.blind_nav import BlindNavigator
            if not hasattr(self, "_blind_navigator") or self._blind_navigator is None:
                api_key = self._get_gemini_api_key()
                self._blind_navigator = BlindNavigator(gemini_api_key=api_key)
            if hasattr(self, "_lbl_blind_nav_status"):
                self._lbl_blind_nav_status.setText("🔄 Analizando pantalla…")
                self._lbl_blind_nav_status.setStyleSheet("color:#ffb300; font-size:9px;")
            self._blind_navigator.quick_describe()
            if hasattr(self, "_lbl_blind_nav_status"):
                self._lbl_blind_nav_status.setText("✅ Descripción lista")
                self._lbl_blind_nav_status.setStyleSheet("color:#ffb300; font-size:9px; font-weight:bold;")
        except Exception as e:
            if hasattr(self, "_lbl_blind_nav_status"):
                self._lbl_blind_nav_status.setText(f"❌ {e}")
                self._lbl_blind_nav_status.setStyleSheet("color:#f44336; font-size:9px;")

    def _blind_nav_set_tts_rate(self, slider_val: int):
        try:
            if hasattr(self, "_blind_navigator") and self._blind_navigator is not None:
                rate_normalized = slider_val / 10.0   # 0.1–1.0
                self._blind_navigator.set_tts_rate(rate_normalized)
        except Exception:
            pass

    def _get_gemini_api_key(self) -> str:
        """Return Gemini API key from config, env var, or empty string."""
        import os
        try:
            cfg_path = Path(CONFIG_DIR) / "api_keys.json"
            keys = json.loads(cfg_path.read_text("utf-8"))
            return keys.get("gemini_api_key", "") or keys.get("GEMINI_API_KEY", "")
        except Exception:
            pass
        return os.environ.get("GEMINI_API_KEY", "")

    def _launch_accessibility_overlay(self):
        try:
            from actions.accessibility_overlay import accessibility_overlay, _overlay_proc
            accessibility_overlay({"action": "show"})
            if hasattr(self, "_btn_acc_overlay_status"):
                self._btn_acc_overlay_status.setText("✅ Activa")
                self._btn_acc_overlay_status.setStyleSheet("color:#00e5ff; font-size:9px; font-weight:bold;")
        except Exception as e:
            print(f"[acc] overlay error: {e}")

    def _test_tts_voice(self):
        import subprocess
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Rate = 1; "
            "$s.Speak('Hola, soy NEXO. El lector de pantalla está funcionando correctamente.');"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            creationflags=0x08000000,
        )

    # ── Camera preview helpers ────────────────────────────────────────────────

    def _acc_toggle_eye(self, btn: QPushButton):
        try:
            from actions.accessibility import _get_eye_tracker
            tracker = _get_eye_tracker()
            if tracker.running:
                msg = tracker.stop()
                btn.setText("👁  Activar Eye")
                self._acc_stop_camera_preview()
                if hasattr(self, "_acc_eye_status"):
                    self._acc_eye_status.setText("⚪ Inactivo")
                    self._acc_eye_status.setStyleSheet("color:#607d8b; font-size:9px; font-weight:bold;")
            else:
                msg = tracker.start()
                btn.setText("⏹  Detener Eye")
                if "✅" in msg:
                    self._acc_start_camera_preview("eye")
                    if hasattr(self, "_acc_eye_status"):
                        self._acc_eye_status.setText("✅ Activo")
                        self._acc_eye_status.setStyleSheet("color:#00e5ff; font-size:9px; font-weight:bold;")
                    if hasattr(self, "_acc_cam_status_bar"):
                        self._acc_cam_status_bar.setText("⏳  Iniciando eye tracking...  ○")
                        self._acc_cam_status_bar.setStyleSheet(
                            "background:#001a2e; border:1px solid #00d4ff; border-top:none;"
                            "border-radius:0 0 6px 6px; color:#607d8b; font-size:9px; font-weight:bold;"
                        )
            print(f"[acc] {msg}")
        except Exception as e:
            print(f"[acc] eye error: {e}")

    def _acc_toggle_gesture(self, btn: QPushButton):
        try:
            from actions.accessibility import _get_micro_detector
            det = _get_micro_detector()
            if det.running:
                msg = det.stop()
                btn.setText("🤖  Activar Gestos")
                self._acc_stop_camera_preview()
                if hasattr(self, "_acc_micro_status"):
                    self._acc_micro_status.setText("⚪ Inactivo")
                    self._acc_micro_status.setStyleSheet("color:#607d8b; font-size:9px; font-weight:bold;")
            else:
                msg = det.start()
                btn.setText("⏹  Detener Gestos")
                if "✅" in msg:
                    self._acc_start_camera_preview("micro")
                    if hasattr(self, "_acc_micro_status"):
                        self._acc_micro_status.setText("✅ Activo")
                        self._acc_micro_status.setStyleSheet("color:#ff9800; font-size:9px; font-weight:bold;")
                    if hasattr(self, "_acc_cam_status_bar"):
                        self._acc_cam_status_bar.setText("⏳  Iniciando gestos...  ○")
                        self._acc_cam_status_bar.setStyleSheet(
                            "background:#1a0e00; border:1px solid #ff9800; border-top:none;"
                            "border-radius:0 0 6px 6px; color:#8a6000; font-size:9px; font-weight:bold;"
                        )
            print(f"[acc] {msg}")
        except Exception as e:
            print(f"[acc] gesture error: {e}")

    def _acc_start_camera_preview(self, mode: str):
        """Start QTimer to refresh camera frame in _acc_cam_label."""
        from PyQt6.QtCore import QTimer
        self._acc_cam_mode = mode
        if not hasattr(self, "_acc_cam_timer") or self._acc_cam_timer is None:
            self._acc_cam_timer = QTimer(self)
            self._acc_cam_timer.setInterval(50)   # 20 fps
            self._acc_cam_timer.timeout.connect(self._acc_refresh_camera_frame)
        self._acc_cam_timer.start()

    def _acc_stop_camera_preview(self):
        if hasattr(self, "_acc_cam_timer") and self._acc_cam_timer:
            self._acc_cam_timer.stop()
        self._acc_cam_mode = None
        if hasattr(self, "_acc_cam_label"):
            self._acc_cam_label.clear()
            self._acc_cam_label.setText("Camara inactiva")
            self._acc_cam_label.setStyleSheet(
                "background:#020e18; border:1px solid #1a2e40;"
                "border-radius:6px 6px 0 0; color:#607d8b; font-size:10px;"
            )
        if hasattr(self, "_acc_cam_status_bar"):
            self._acc_cam_status_bar.setText("⚫  Cámara inactiva")
            self._acc_cam_status_bar.setStyleSheet(
                "background:#0a1520; border:1px solid #1a2e40; border-top:none;"
                "border-radius:0 0 6px 6px; color:#455a64; font-size:9px; font-weight:bold;"
            )

    def _acc_refresh_camera_frame(self):
        """Pull latest annotated frame from tracker and show in cam label."""
        if not hasattr(self, "_acc_cam_label") or not self._acc_cam_mode:
            return
        try:
            from actions.accessibility import get_latest_camera_frame
            from PyQt6.QtGui import QImage, QPixmap
            frame = get_latest_camera_frame(self._acc_cam_mode)

            # Toggle blink dot
            self._acc_live_blink = not getattr(self, "_acc_live_blink", False)
            dot = "●" if self._acc_live_blink else "○"

            if frame is None:
                # Tracking active but camera not ready yet
                if hasattr(self, "_acc_cam_status_bar"):
                    mode = self._acc_cam_mode
                    if mode == "eye":
                        self._acc_cam_status_bar.setText(f"⏳  Iniciando eye tracking...  {dot}")
                        self._acc_cam_status_bar.setStyleSheet(
                            "background:#001a2e; border:1px solid #00d4ff; border-top:none;"
                            "border-radius:0 0 6px 6px; color:#607d8b; font-size:9px; font-weight:bold;"
                        )
                    else:
                        self._acc_cam_status_bar.setText(f"⏳  Iniciando gestos...  {dot}")
                        self._acc_cam_status_bar.setStyleSheet(
                            "background:#1a0e00; border:1px solid #ff9800; border-top:none;"
                            "border-radius:0 0 6px 6px; color:#8a6000; font-size:9px; font-weight:bold;"
                        )
                return

            import cv2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
            pix  = QPixmap.fromImage(qimg).scaled(
                320, 180,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._acc_cam_label.setPixmap(pix)
            self._acc_cam_label.setStyleSheet(
                "background:#000; border:1px solid #00d4ff; border-radius:6px 6px 0 0;"
            )

            # Status bar with mode name + live dot
            if hasattr(self, "_acc_cam_status_bar"):
                if self._acc_cam_mode == "eye":
                    self._acc_cam_status_bar.setText(f"👁  EYE TRACKING ACTIVO  {dot}")
                    self._acc_cam_status_bar.setStyleSheet(
                        "background:#001a2e; border:1px solid #00d4ff; border-top:none;"
                        "border-radius:0 0 6px 6px; color:#00e5ff; font-size:9px; font-weight:bold;"
                    )
                elif self._acc_cam_mode == "micro":
                    self._acc_cam_status_bar.setText(f"🤖  CONTROL POR GESTOS ACTIVO  {dot}")
                    self._acc_cam_status_bar.setStyleSheet(
                        "background:#1a0e00; border:1px solid #ff9800; border-top:none;"
                        "border-radius:0 0 6px 6px; color:#ff9800; font-size:9px; font-weight:bold;"
                    )
        except Exception:
            pass

    def _apply_high_contrast(self, enabled: bool):
        """Toggle high-contrast mode on the main settings panel."""
        if not hasattr(self, "_win"):
            return
        if enabled:
            self._win.setStyleSheet(
                self._win.styleSheet() +
                " QLabel { color: #ffffff !important; font-size: 14px !important; }"
                " QPushButton { font-size: 13px !important; }"
                " QWidget { background-color: #000000 !important; }"
            )
        else:
            # Reload normal stylesheet (force repaint)
            ss = self._win.styleSheet()
            self._win.setStyleSheet(ss)

    def _test_camera_accessibility(self):
        """Quick camera test: open webcam, show a frame in a QDialog."""
        try:
            import cv2
        except ImportError:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Camara",
                                "OpenCV no está instalado.\n"
                                "Ejecutá: pip install opencv-python")
            return

        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel as _QL, QPushButton as _QPB
        from PyQt6.QtGui import QImage, QPixmap
        from PyQt6.QtCore import QTimer

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Camara", "No se pudo abrir la camara (indice 0).")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("NEXO — Prueba de Camara")
        dlg.setFixedSize(400, 320)
        dlg.setStyleSheet("background:#030d0d;")
        lay = QVBoxLayout(dlg)

        lbl = _QL()
        lbl.setFixedSize(380, 280)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)

        close_btn = _QPB("Cerrar")
        close_btn.setStyleSheet("color:#00e5ff; background:#0d2540; border:1px solid #00e5ff;"
                                "border-radius:4px; padding:4px 16px;")
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)

        def _update():
            ret, frame = cap.read()
            if ret:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
                pix = QPixmap.fromImage(qimg).scaled(380, 280,
                      Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)
                lbl.setPixmap(pix)

        timer = QTimer(dlg)
        timer.timeout.connect(_update)
        timer.start(33)

        dlg.exec()
        timer.stop()
        cap.release()

    def _build_page_automations(self) -> QWidget:
        scroll, form = self._s_scroll_page()
        form.addWidget(self._s_section("⚡  AUTOMATIZACIONES POR FRASE"))

        hint = QLabel(
            "Decile a NEXO por voz:\n"
            "  \"cuando diga estoy en casa, abrí Spotify\"\n"
            "  \"cuando diga buenas noches, apagá las luces\"\n"
            "Las reglas se activan automáticamente cuando NEXO detecta la frase."
        )
        hint.setFont(QFont("Segoe UI", 8))
        hint.setStyleSheet(f"color:{C.TEXT_DIM}; background:rgba(0,212,255,0.04);"
                           f"border:1px solid {C.BORDER}; border-radius:8px; padding:8px;")
        hint.setWordWrap(True)
        form.addWidget(hint)

        self._auto_list_layout = QVBoxLayout()
        self._auto_list_layout.setSpacing(5)
        self._auto_list_container = QWidget()
        self._auto_list_container.setStyleSheet("background:transparent;")
        self._auto_list_container.setLayout(self._auto_list_layout)
        form.addWidget(self._auto_list_container)
        self._refresh_automations()

        form.addStretch()
        return scroll

    def _refresh_automations(self):
        layout = self._auto_list_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            rules_file = BASE_DIR / "config" / "rules.json"
            rules = json.loads(rules_file.read_text("utf-8")) if rules_file.exists() else []
            phrases = [r for r in rules if r.get("condition", {}).get("type") == "phrase"]
        except Exception:
            phrases = []

        if not phrases:
            empty_lbl = QLabel("Sin automatizaciones. Pedíselas a NEXO por voz.")
            empty_lbl.setFont(QFont("Segoe UI", 8))
            empty_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; padding:4px;")
            layout.addWidget(empty_lbl)
            return

        for rule in phrases:
            cond    = rule.get("condition", {})
            act     = rule.get("action", {})
            trigger = cond.get("trigger", "?")
            enabled = rule.get("enabled", True)
            act_map = {
                "open_app":    f"abrir {act.get('app_name','?')}",
                "spotify_play":f"Spotify: {act.get('query','?')}",
                "browser":     f"abrir {act.get('url','?')}",
                "notify":      f"notificar: {act.get('message','?')}",
                "speak":       f"hablar: {act.get('message','?')}",
                "composite":   f"{len(act.get('actions',[]))} acciones",
                "smart_home":  f"smart home: {act.get('device','?')}",
            }
            act_lbl = act_map.get(act.get("type","?"), act.get("type","?"))
            status  = "✅" if enabled else "⏸"

            row = QHBoxLayout()
            lbl = QLabel(f"{status}  <b>\"{trigger}\"</b>  →  {act_lbl}")
            lbl.setFont(QFont("Segoe UI", 8))
            lbl.setStyleSheet(f"color:{C.TEXT_MED}; background:transparent;")
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            row.addWidget(lbl, stretch=1)

            del_btn = QPushButton("🗑")
            del_btn.setFixedSize(26, 26)
            del_btn.setFont(QFont("Segoe UI Emoji", 10))
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(
                "QPushButton{background:transparent;color:#555;border:none;border-radius:13px;}"
                "QPushButton:hover{color:#ff3355;background:rgba(255,51,85,0.18);}")
            rid = rule.get("id","")
            del_btn.clicked.connect(lambda _, r=rid: self._delete_automation(r))
            row.addWidget(del_btn)

            row_w = QWidget()
            row_w.setLayout(row)
            row_w.setStyleSheet(
                f"background:rgba(0,212,255,0.03); border:1px solid {C.BORDER}; border-radius:8px; padding:2px 8px;")
            layout.addWidget(row_w)

    def _delete_automation(self, rule_id: str):
        try:
            rules_file = BASE_DIR / "config" / "rules.json"
            rules = json.loads(rules_file.read_text("utf-8")) if rules_file.exists() else []
            rules = [r for r in rules if r.get("id") != rule_id]
            rules_file.write_text(json.dumps(rules, indent=2, ensure_ascii=False), "utf-8")
        except Exception as e:
            print(f"[Settings] Error borrando automatización: {e}")
        self._refresh_automations()

    def _load_config(self):
        try:
            self._cfg = json.loads(API_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._cfg = {}

    def _get_combo_value(self, combo):
        txt = combo.currentText()
        if "(idx " in txt:
            try:
                return int(txt.split("(idx ")[1].rstrip(")"))
            except Exception:
                return txt
        return txt

    def _save(self):
        try:
            d = self._cfg.copy()
            d["gemini_api_key"] = self._key_input.text().strip()

            # Voice
            selected_voice = next((n for n, b in self._voice_btns.items() if b.isChecked()), "Charon")
            d["nexo_voice"] = selected_voice

            # Google
            _sel_idx = self._google_profile.currentIndex()
            _dirs    = getattr(self, "_google_profile_dirs", [])
            d["chrome_google_profile"] = _dirs[_sel_idx] if 0 <= _sel_idx < len(_dirs) else "Default"
            d["chrome_exe_path"]       = self._chrome_path.text().strip()

            # General
            d["timezone"]       = self._tz_combo.currentText()
            d["language"]       = self._lang_input.text().strip() or "es-ES"
            d["os_system"]      = self._os_combo.currentText()
            d["thinking_sound"] = self._thinking_sound_cb.isChecked()
            try:
                d["camera_index"] = int(self._cam_index.text().strip())
            except Exception:
                d["camera_index"] = 0

            # Ollama / Model routing
            if hasattr(self, "_ollama_enabled_cb"):
                d["ollama_enabled"]        = self._ollama_enabled_cb.isChecked()
            if hasattr(self, "_ollama_url"):
                d["ollama_base_url"]       = self._ollama_url.text().strip() or "http://localhost:11434"
            if hasattr(self, "_ollama_model_input"):
                d["ollama_model"]          = self._ollama_model_input.text().strip() or "llama3.2"
            if hasattr(self, "_model_conv"):
                d["model_for_conversation"] = self._model_conv.currentText()
            if hasattr(self, "_model_agent"):
                d["model_for_agents"]       = self._model_agent.currentText()
            if hasattr(self, "_model_search"):
                d["model_for_search"]       = self._model_search.currentText()

            # Audio
            d["mic_device"] = self._get_combo_value(self._mic_combo)
            d["spk_device"] = self._get_combo_value(self._spk_combo)

            # APIs
            d["spotify_client_id"]     = self._spotify_id.text().strip()
            d["spotify_client_secret"] = self._spotify_secret.text().strip()
            d["spotify_redirect_uri"]  = self._spotify_redirect.text().strip() or "http://127.0.0.1:8888/callback"
            d["tmdb_api_key"]          = self._tmdb_key.text().strip()
            # Social media fields only exist in PRO build
            if self._tw_key is not None:
                d["twitter_api_key"]             = self._tw_key.text().strip()
                d["twitter_api_secret"]          = self._tw_secret.text().strip()
                d["twitter_access_token"]        = self._tw_at.text().strip()
                d["twitter_access_token_secret"] = self._tw_ats.text().strip()
                d["twitter_bearer_token"]        = self._tw_bt.text().strip()
            if self._ig_user is not None:
                d["instagram_username"] = self._ig_user.text().strip()
                d["instagram_password"] = self._ig_pass.text().strip()

            # Accessibility
            _acc = {}
            _acc["task_simplification_enabled"]  = self._acc_simplify.isChecked()
            _acc["emotional_regulation_enabled"]  = self._acc_emotion.isChecked()
            _acc["routine_gamification_enabled"]  = self._acc_routine.isChecked()
            _acc["eye_tracking_enabled"]          = self._acc_eye.isChecked()
            _acc["micro_movement_enabled"]        = self._acc_micro.isChecked()
            _acc["visual_feedback_enabled"]       = self._acc_visual.isChecked()
            _acc["high_contrast_mode"]            = self._acc_contrast.isChecked()
            _acc["auto_learn_routines"]           = self._acc_learn.isChecked()
            _acc["speech_error_threshold"]        = self._acc_threshold.value() / 10.0
            _fs_text = self._acc_font_scale.currentText().replace("x","")
            try:
                _acc["font_size_scale"] = float(_fs_text.replace(",", "."))
            except Exception:
                _acc["font_size_scale"] = 1.0
            _acc_path = Path(CONFIG_DIR) / "accessibility_config.json"
            _acc_path.write_text(json.dumps(_acc, indent=2), encoding="utf-8")

            # Apply eye tracking and micro movement changes immediately
            try:
                from actions.accessibility import _get_eye_tracker, _get_micro_detector
                eye_enabled = _acc["eye_tracking_enabled"]
                tracker = _get_eye_tracker()
                if eye_enabled and not tracker.running:
                    tracker.start()
                    if hasattr(self, "_acc_eye_status"):
                        self._acc_eye_status.setText("✅ Activo")
                        self._acc_eye_status.setStyleSheet("color:#00e5ff; font-size:9px; font-weight:bold;")
                    self._acc_start_camera_preview("eye")
                elif not eye_enabled and tracker.running:
                    tracker.stop()
                    if hasattr(self, "_acc_eye_status"):
                        self._acc_eye_status.setText("⚪ Inactivo")
                        self._acc_eye_status.setStyleSheet("color:#607d8b; font-size:9px; font-weight:bold;")
                    self._acc_stop_camera_preview()

                micro_enabled = _acc["micro_movement_enabled"]
                detector = _get_micro_detector()
                if micro_enabled and not detector.running:
                    detector.start()
                    if hasattr(self, "_acc_micro_status"):
                        self._acc_micro_status.setText("✅ Activo")
                        self._acc_micro_status.setStyleSheet("color:#00e5ff; font-size:9px; font-weight:bold;")
                    self._acc_start_camera_preview("micro")
                elif not micro_enabled and detector.running:
                    detector.stop()
                    if hasattr(self, "_acc_micro_status"):
                        self._acc_micro_status.setText("⚪ Inactivo")
                        self._acc_micro_status.setStyleSheet("color:#607d8b; font-size:9px; font-weight:bold;")
                    if not (eye_enabled and tracker.running):
                        self._acc_stop_camera_preview()
            except Exception as _acc_err:
                print(f"[Accessibility] apply error: {_acc_err}")

            # Apply high contrast / visual feedback immediately
            try:
                if _acc.get("high_contrast_mode"):
                    self._apply_high_contrast(True)
                else:
                    self._apply_high_contrast(False)
            except Exception:
                pass

            # Theme: ensure saved theme is in d and applied globally
            if "nexo_theme" in self._cfg:
                d["nexo_theme"] = self._cfg["nexo_theme"]
            os.makedirs(CONFIG_DIR, exist_ok=True)
            API_FILE.write_text(json.dumps(d, indent=4), encoding="utf-8")

            # social_media.json backward compat (PRO only)
            social = {}
            if self._tw_key is not None and any(
                d.get(k) for k in ("twitter_api_key","twitter_api_secret","twitter_access_token",
                                   "twitter_access_token_secret","twitter_bearer_token")
            ):
                social["twitter"] = {
                    "api_key": d.get("twitter_api_key",""),
                    "api_secret": d.get("twitter_api_secret",""),
                    "access_token": d.get("twitter_access_token",""),
                    "access_token_secret": d.get("twitter_access_token_secret",""),
                    "bearer_token": d.get("twitter_bearer_token",""),
                }
            if self._ig_user is not None and (d.get("instagram_username") or d.get("instagram_password")):
                social["instagram"] = {
                    "username": d.get("instagram_username",""),
                    "password": d.get("instagram_password",""),
                }
            if social:
                (Path(CONFIG_DIR) / "social_media.json").write_text(
                    json.dumps(social, indent=2, ensure_ascii=False), encoding="utf-8")

            # Vision Guardian state
            try:
                _vg_enabled = self._vision_guardian_cb.isChecked()
                _vg_path = Path(CONFIG_DIR) / "vision_guardian_state.json"
                _vg_state = {}
                try:
                    _vg_state = json.loads(_vg_path.read_text())
                except Exception:
                    pass
                _vg_state["enabled"] = _vg_enabled
                _vg_path.write_text(json.dumps(_vg_state, ensure_ascii=False))
                # Apply immediately
                from actions.vision_guardian import stop as _vg_stop
                if not _vg_enabled:
                    _vg_stop()
            except Exception:
                pass

            # Auto-start with Windows (Improvement 1)
            try:
                if hasattr(self, "_autostart_cb"):
                    self._set_autostart(self._autostart_cb.isChecked())
            except Exception as _as_err:
                print(f"[Settings] Auto-start error: {_as_err}")

            _load_tz_from_config()
            self.config_saved.emit(d)
            self.hide()
        except Exception as e:
            print(f"[Settings] Error al guardar: {e}")


# ═══════════════════════════════════════════════════════════
# SETUP OVERLAY  — first-run API key entry
# ═══════════════════════════════════════════════════════════
class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(50); shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 200))
        self.setGraphicsEffect(shadow)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(2,8,16,250);
                border: 1px solid {C.BORDER_A};
                border-radius: 24px;
            }}
        """)
        det = {"darwin": "mac", "windows": "windows"}.get(_OS.lower(), "linux")
        self._sel_os = det
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 26, 32, 26)
        lay.setSpacing(10)

        def _l(txt, fs=9, bold=False, color=C.PRI, align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(QFont("Segoe UI", fs, QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color:{color};background:transparent;")
            return w

        lay.addWidget(_l("◈  INICIALIZACIÓN REQUERIDA", 13, True))
        lay.addWidget(_l("Configura Nexo antes del primer arranque.", 9, color=C.PRI_DIM))
        lay.addSpacing(4)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{C.BORDER};"); lay.addWidget(sep)
        lay.addSpacing(4)
        lay.addWidget(_l("GEMINI API KEY", 8, color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))

        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setPlaceholderText("AIza…")
        self._key.setFont(QFont("Segoe UI", 10))
        self._key.setFixedHeight(36)
        self._key.setStyleSheet(f"""
            QLineEdit {{
                background:#000d12;color:{C.TEXT};
                border:1px solid {C.BORDER};border-radius:18px;padding:4px 14px;
            }}
            QLineEdit:focus {{border:1px solid {C.PRI};}}
        """)
        lay.addWidget(self._key)
        lay.addSpacing(8)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color:{C.BORDER};"); lay.addWidget(sep2)
        lay.addSpacing(4)
        lay.addWidget(_l("SISTEMA OPERATIVO", 8, color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[det]
        lay.addWidget(_l(f"Auto-detectado: {det_name}", 8, color=C.ACC2, align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(8)
        self._os_btns: dict[str, QPushButton] = {}
        for key, lbl in [("windows", "⊞  Windows"), ("mac", "  macOS"), ("linux", "🐧  Linux")]:
            btn = QPushButton(lbl)
            btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            btn.setFixedHeight(32); btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn); self._os_btns[key] = btn
        lay.addLayout(os_row)
        self._sel(det)
        lay.addSpacing(12)

        init = QPushButton("▸  INICIALIZAR SISTEMAS")
        init.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        init.setFixedHeight(40); init.setCursor(Qt.CursorShape.PointingHandCursor)
        init.setStyleSheet(f"""
            QPushButton {{
                background:transparent;color:{C.PRI};
                border:1px solid {C.PRI_DIM};border-radius:20px;
            }}
            QPushButton:hover {{background:{C.PRI_GHO};border:1px solid {C.PRI};}}
        """)
        init.clicked.connect(self._submit)
        lay.addWidget(init)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows": (C.PRI, "#001a22"), "mac": (C.ACC2, "#1a1400"), "linux": (C.GREEN, "#001a0d")}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"QPushButton {{background:{fg};color:{bg};border:none;border-radius:16px;font-weight:bold;}}")
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{background:#000d12;color:{C.TEXT_DIM};border:1px solid {C.BORDER};border-radius:16px;}}
                    QPushButton:hover {{color:{C.TEXT};border:1px solid {C.BORDER_A};}}
                """)

    def _submit(self):
        key = self._key.text().strip()
        if not key:
            self._key.setStyleSheet(self._key.styleSheet() +
                                    f" QLineEdit {{border:1px solid {C.RED};}}")
            return
        self.done.emit(key, self._sel_os)


# ═══════════════════════════════════════════════════════════
# MAP WEB WIDGET  — Google Maps embebido en la UI de NEXO
# ═══════════════════════════════════════════════════════════
class MapWebWidget(DraggableWidget):
    """
    Muestra Google Maps con ruta completa e indicaciones en español.
    Widgets creados UNA SOLA VEZ en __init__ — load_route() sólo ACTUALIZA
    los valores existentes, sin crear ni eliminar nada → cero lag.
    """

    _STEP_ICONS = {
        "depart":     "▶", "arrive": "🏁", "turn":   "↪",
        "merge":      "⤵", "fork":   "⑂", "roundabout": "🔄",
        "end of road": "⚠", "straight": "↑", "new name": "↑",
        "notification": "ℹ",
    }
    _MAX_STEP_ROWS = 25   # máximo de filas de pasos pre-creadas

    def __init__(self, parent=None):
        super().__init__("GOOGLE MAPS", "🗺", C.ACC2, closeable=True, parent=parent)
        self.resize(980, 640)
        self._current_url  = ""
        self._current_data: dict = {}

        # ── Barra de resumen (siempre visible — origen, destino, tiempo, distancia) ──
        info = QFrame()
        info.setStyleSheet(
            f"QFrame {{background:#060d1f; border-radius:8px; "
            f"border:1px solid {C.BORDER}; margin-bottom:4px;}}"
        )
        info_lay = QHBoxLayout(info)
        info_lay.setContentsMargins(10, 7, 10, 7)
        info_lay.setSpacing(8)

        # Punto de origen
        self._orig_dot = QLabel("●")
        self._orig_dot.setFont(QFont("Segoe UI", 8))
        self._orig_dot.setStyleSheet(f"color:{C.PRI}; background:transparent; min-width:12px;")
        self._orig_lbl = QLabel("—")
        self._orig_lbl.setFont(QFont("Segoe UI", 8))
        self._orig_lbl.setStyleSheet(f"color:{C.TEXT_MED}; background:transparent;")
        self._orig_lbl.setSizePolicy(
            self._orig_lbl.sizePolicy().horizontalPolicy(),
            self._orig_lbl.sizePolicy().verticalPolicy()
        )

        # Flecha
        arrow = QLabel("→")
        arrow.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        arrow.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent;")

        # Destino
        self._dest_dot = QLabel("●")
        self._dest_dot.setFont(QFont("Segoe UI", 8))
        self._dest_dot.setStyleSheet(f"color:{C.RED}; background:transparent; min-width:12px;")
        self._dest_lbl = QLabel("—")
        self._dest_lbl.setFont(QFont("Segoe UI", 8))
        self._dest_lbl.setStyleSheet(f"color:{C.TEXT_MED}; background:transparent;")

        info_lay.addWidget(self._orig_dot)
        info_lay.addWidget(self._orig_lbl, 2)
        info_lay.addWidget(arrow)
        info_lay.addWidget(self._dest_dot)
        info_lay.addWidget(self._dest_lbl, 2)
        info_lay.addStretch()

        # Chips tiempo / distancia
        for attr, label, color in [
            ("_time_chip", "TIEMPO",    C.ACC2),
            ("_dist_chip", "DISTANCIA", C.PRI),
        ]:
            chip = QFrame()
            chip.setStyleSheet(
                f"QFrame {{background:#0d1e3d; border:1px solid {C.BORDER}; "
                f"border-radius:8px; padding:2px 6px;}}"
            )
            cl = QVBoxLayout(chip)
            cl.setContentsMargins(6, 3, 6, 3)
            cl.setSpacing(0)
            val = QLabel("—")
            val.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(f"color:{color}; background:transparent;")
            sub = QLabel(label)
            sub.setFont(QFont("Segoe UI", 6))
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent;")
            cl.addWidget(val)
            cl.addWidget(sub)
            setattr(self, attr + "_val", val)
            info_lay.addWidget(chip)

        self._body.addWidget(info)

        # ── Mapa o lista de pasos (dependiendo de si hay WebEngine) ──
        if _HAS_WEBENGINE:
            self._web = QWebEngineView()
            self._web.setStyleSheet("border: none; background: #030a10;")
            # Optimizaciones de rendimiento del WebEngine
            try:
                from PyQt6.QtWebEngineCore import QWebEngineSettings as _WES
                _s = self._web.settings()
                _s.setAttribute(_WES.WebAttribute.ScrollAnimatorEnabled,  False)
                _s.setAttribute(_WES.WebAttribute.LocalStorageEnabled,    False)
                _s.setAttribute(_WES.WebAttribute.AutoLoadImages,         True)
            except Exception:
                pass
            self._web.setHtml(self._placeholder_html(), QUrl("about:blank"))
            self._body.addWidget(self._web, stretch=1)
            self._load_timer = QTimer(self)
            self._load_timer.setSingleShot(True)
            self._load_timer.timeout.connect(self._do_load_url)
            # No hay lista de pasos en modo webengine (el mapa los muestra)
            self._steps_layout = None
            self._step_rows: list[QWidget] = []
        else:
            self._web        = None
            self._load_timer = None
            warn = QLabel(
                "⚠  Para mapa interactivo instalá: pip install PyQt6-WebEngine"
            )
            warn.setFont(QFont("Segoe UI", 8))
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color:{C.ACC}; background:transparent; padding:2px 0 4px 0;")
            self._body.addWidget(warn)

            # Scroll + contenedor de pasos — creado UNA sola vez
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setStyleSheet("""
                QScrollArea { background: transparent; border: none; }
                QScrollBar:vertical {
                    width: 4px; background: #030a10; margin: 0;
                }
                QScrollBar::handle:vertical {
                    background: #1a3060; border-radius: 2px; min-height: 20px;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0;
                }
            """)
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            self._steps_layout = QVBoxLayout(container)
            self._steps_layout.setContentsMargins(0, 2, 0, 2)
            self._steps_layout.setSpacing(3)

            # Pre-crear filas de pasos (reutilizables → cero alloc en load_route)
            self._step_rows: list[tuple[QLabel, QLabel, QLabel]] = []
            for _ in range(self._MAX_STEP_ROWS):
                row = QWidget()
                row.setStyleSheet(
                    "QWidget{background:#060d1f; border-radius:5px;}"
                    "QWidget:hover{background:#0a1628;}"
                )
                rl = QHBoxLayout(row)
                rl.setContentsMargins(8, 4, 8, 4)
                rl.setSpacing(7)
                ic = QLabel("•")
                ic.setFont(QFont("Segoe UI Emoji" if _OS == "Windows" else "Arial", 10))
                ic.setStyleSheet("background:transparent; color:#4fc3f7; min-width:16px;")
                ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
                tl = QLabel("")
                tl.setFont(QFont("Segoe UI", 8))
                tl.setStyleSheet(f"background:transparent; color:{C.TEXT_MED};")
                dl = QLabel("")
                dl.setFont(QFont("Consolas", 7))
                dl.setStyleSheet(f"background:transparent; color:{C.TEXT_DIM};")
                dl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                dl.setFixedWidth(45)
                rl.addWidget(ic)
                rl.addWidget(tl, 1)
                rl.addWidget(dl)
                row.hide()
                self._steps_layout.addWidget(row)
                self._step_rows.append((row, ic, tl, dl))   # type: ignore[arg-type]

            self._steps_layout.addStretch()
            scroll.setWidget(container)
            self._body.addWidget(scroll, stretch=1)

        # ── Barra inferior: modo + botón abrir ──────────────────────
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self._mode_lbl = QLabel("")
        self._mode_lbl.setFont(QFont("Segoe UI", 9))
        self._mode_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent;")
        bar.addWidget(self._mode_lbl)
        bar.addStretch()

        open_btn = QPushButton("🌐  Abrir en Google Maps")
        open_btn.setFixedHeight(28)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background:rgba(0,212,255,0.07); color:{C.PRI};
                border:1px solid {C.PRI_DIM}; border-radius:14px; padding:0 12px;
            }}
            QPushButton:hover {{ background:rgba(0,212,255,0.18); border-color:{C.PRI}; }}
            QPushButton:pressed {{ background:rgba(0,212,255,0.30); }}
        """)
        open_btn.clicked.connect(lambda: self._open_in_browser())
        bar.addWidget(open_btn)
        self._body.addLayout(bar)

    # ── Helpers ────────────────────────────────────────────
    def _placeholder_html(self) -> str:
        return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body{background:#030a10;color:#1a5070;font-family:'Segoe UI',sans-serif;
       display:flex;align-items:center;justify-content:center;
       height:100vh;margin:0;flex-direction:column;gap:14px;}
  .icon{font-size:56px;animation:pulse 2s infinite;}
  .hint{font-size:12px;color:#0d2540;letter-spacing:.5px;}
  @keyframes pulse{0%,100%{opacity:.5;}50%{opacity:1;}}
</style></head><body>
<div class="icon">🗺</div>
<div class="hint">Calculando ruta…</div>
</body></html>"""

    def _open_in_browser(self):
        if self._current_url:
            import webbrowser
            webbrowser.open(self._current_url)

    def _do_load_url(self):
        if _HAS_WEBENGINE and self._web and self._current_url:
            self._web.load(QUrl(self._current_url))

    # ── load_route: SÓLO actualiza — no crea ni elimina widgets ────
    def load_route(self, data: dict):
        self._current_data = data
        url = data.get("url", "")
        self._current_url = url

        # Actualizar info bar
        orig = (data.get("origin_display") or data.get("origin", "") or "—")[:55]
        dest = (data.get("dest_display")   or data.get("destination", "") or "—")[:55]
        dur  = data.get("duration", "")
        dist = data.get("distance", "")
        mode_icon = data.get("mode", "🚗")
        mode_name = data.get("mode_name", "")

        self._orig_lbl.setText(orig or "—")
        self._dest_lbl.setText(dest or "—")
        self._time_chip_val.setText(dur  or "—")
        self._dist_chip_val.setText(dist or "—")

        # Ocultar chips vacíos
        self._time_chip_val.parentWidget().setVisible(bool(dur))
        self._dist_chip_val.parentWidget().setVisible(bool(dist))

        mode_str = f"{mode_icon}  {mode_name}" if mode_name else mode_icon
        if dur and dist:
            mode_str += f"  ·  {dur}  ·  {dist}"
        self._mode_lbl.setText(mode_str)

        # ── Modo WebEngine: disparar carga con debounce ──────────
        if _HAS_WEBENGINE and self._web:
            if url:
                # 350ms de debounce — esperar que termine la animación de aparición
                self._load_timer.start(350)
            return

        # ── Modo texto: actualizar filas de pasos pre-creadas ────
        steps = data.get("steps", [])[:self._MAX_STEP_ROWS]

        for i, (row, ic, tl, dl) in enumerate(self._step_rows):
            if i < len(steps):
                step = steps[i]
                typ  = step.get("type", "")
                mod  = step.get("modifier", "")
                name = (step.get("name", "") or "").strip()
                d    = step.get("distance_str", "")

                icon_char = self._STEP_ICONS.get(typ, "•")
                ic.setText(icon_char)

                parts = []
                if mod:
                    parts.append(mod.capitalize())
                if name:
                    parts.append(name)
                txt = " ".join(parts) or typ.replace("_", " ").capitalize() or "—"
                tl.setText(txt[:60])
                dl.setText(d)
                row.show()
            else:
                row.hide()   # esconder filas sobrantes sin eliminarlas



# ═══════════════════════════════════════════════════════════
# IMAGE WIDGET  — muestra imágenes generadas por IA
# ═══════════════════════════════════════════════════════════

class ImageWidget(DraggableWidget):
    """Widget que muestra una o varias imágenes generadas por IA."""

    def __init__(self, parent=None):
        super().__init__("IMAGEN IA", "🎨", C.ACC2, closeable=True, parent=parent)
        self.resize(520, 520)
        self._current_paths: list[str] = []
        self._maximized = False
        self._normal_geo = self.geometry()

        # Scroll area for images
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 4px; background: #030a10; }
            QScrollBar::handle:vertical { background: #1a3060; border-radius: 2px; }
        """)
        self._scroll = scroll

        self._img_container = QWidget()
        self._img_container.setStyleSheet("background: transparent;")
        self._img_layout = QVBoxLayout(self._img_container)
        self._img_layout.setContentsMargins(0, 0, 0, 0)
        self._img_layout.setSpacing(8)
        self._img_layout.addStretch()
        scroll.setWidget(self._img_container)
        self._body.addWidget(scroll, stretch=1)

        # Bottom bar: image count + maximize toggle
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self._count_lbl = QLabel("")
        self._count_lbl.setFont(QFont("Segoe UI", 8))
        self._count_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent;")
        bar.addWidget(self._count_lbl)
        bar.addStretch()

        max_btn = QPushButton("⛶")
        max_btn.setFixedSize(24, 24)
        max_btn.setFont(QFont("Segoe UI", 10))
        max_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        max_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:{C.TEXT_DIM};
                border:1px solid {C.BORDER}; border-radius:12px; }}
            QPushButton:hover {{ color:{C.PRI}; border-color:{C.PRI}; }}
        """)
        max_btn.clicked.connect(self._toggle_maximize)
        bar.addWidget(max_btn)

        save_btn = QPushButton("💾")
        save_btn.setFixedSize(24, 24)
        save_btn.setFont(QFont("Segoe UI", 10))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:{C.TEXT_DIM};
                border:1px solid {C.BORDER}; border-radius:12px; }}
            QPushButton:hover {{ color:{C.GREEN}; border-color:{C.GREEN}; }}
        """)
        save_btn.clicked.connect(self._save_current)
        bar.addWidget(save_btn)
        self._body.addLayout(bar)

    def set_images(self, paths: list[str]):
        """Display one or more images from file paths."""
        self._current_paths = paths
        # Clear existing
        while self._img_layout.count() > 0:
            item = self._img_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._img_layout.addStretch()

        for path in paths:
            pix = QPixmap(path)
            if pix.isNull():
                continue
            # Scale to fit widget width while maintaining aspect ratio
            max_w = self.width() - 40
            if pix.width() > max_w:
                pix = pix.scaledToWidth(max_w, Qt.TransformationMode.SmoothTransformation)
            lbl = QLabel()
            lbl.setPixmap(pix)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("background: transparent; border: none;")
            self._img_layout.insertWidget(self._img_layout.count() - 1, lbl)

        n = len([p for p in paths if Path(p).exists()])
        self._count_lbl.setText(f"{n} imagen{'es' if n != 1 else ''}")

    def _toggle_maximize(self):
        area = self.parent()
        if not area:
            return
        if self._maximized:
            self.setGeometry(self._normal_geo)
            self._maximized = False
        else:
            self._normal_geo = self.geometry()
            W, H = area.width(), area.height()
            margin = 40
            self.setGeometry(margin, margin, W - margin * 2, H - margin * 2)
            self._maximized = True
        # Re-scale images to new size
        self.set_images(self._current_paths)

    def _save_current(self):
        if not self._current_paths:
            return
        from shutil import copy2
        dest = Path.home() / "Pictures" / "NEXO_Generadas"
        dest.mkdir(parents=True, exist_ok=True)
        saved = []
        for src in self._current_paths:
            p = Path(src)
            if p.exists():
                dst = dest / p.name
                copy2(str(p), str(dst))
                saved.append(str(dst))
        if saved:
            self._count_lbl.setText(f"💾 Guardada en {dest}")


# ═══════════════════════════════════════════════════════════
# FILE EVENTS — import (optional, degrades gracefully)
# ═══════════════════════════════════════════════════════════
try:
    import file_events as _file_events
    _HAS_FILE_EVENTS = True
except ImportError:
    _HAS_FILE_EVENTS = False


# ═══════════════════════════════════════════════════════════
# VISION SCANNER WIDGET — escaneo épico de pantalla estilo NEXO
# ═══════════════════════════════════════════════════════════
class VisionScannerWidget(QWidget):
    """Escaneo épico de pantalla estilo NEXO - Barra horizontal con análisis"""
    
    EXPANDED_H = 180
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scanning = False
        self._scan_y = 0
        self._scan_line = 0
        self._result = ""
        self._anim_timer = None
        self.setFixedHeight(0)
        self.hide()
        
        # Colors
        self._scan_color = QColor(0, 212, 255)  # Cyan NEXO
        self._bg_dark = QColor(0, 13, 24)
        self._border = QColor(0, 95, 119)
        
        # Layout
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        
        # Top bar - título
        top_bar = QWidget()
        top_bar.setFixedHeight(36)
        top_bar.setStyleSheet(f"background:rgba(0,13,24,240); border-bottom:1px solid {C.PRI_DIM};")
        top_lay = QHBoxLayout(top_bar)
        top_lay.setContentsMargins(16, 0, 16, 0)
        
        self._title = QLabel("⚡  ESCANEANDO ENTORNO...")
        self._title.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self._title.setStyleSheet(f"color:{C.PRI}; letter-spacing:2px;")
        top_lay.addWidget(self._title)
        top_lay.addStretch()
        
        self._status = QLabel("Analizando...")
        self._status.setFont(QFont("Segoe UI", 9))
        self._status.setStyleSheet(f"color:{C.TEXT_DIM};")
        top_lay.addWidget(self._status)
        
        main_lay.addWidget(top_bar)
        
        # Scanner area
        self._scanner_area = QWidget()
        self._scanner_area.setStyleSheet(f"background:transparent;")
        scanner_lay = QVBoxLayout(self._scanner_area)
        scanner_lay.setContentsMargins(0, 0, 0, 0)
        
        # Progress bar
        self._progress = QProgressBar()
        self._progress.setFixedHeight(8)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background: {C.BG_DARK};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0, 
                    stop:0 {C.PRI_DIM}, stop:0.5 {C.PRI}, stop:1 {C.PRI_GHO});
                border-radius: 3px;
            }}
        """)
        scanner_lay.addWidget(self._progress, alignment=Qt.AlignmentFlag.AlignCenter)
        
        main_lay.addWidget(self._scanner_area)
        
        # Result area (hidden initially)
        self._result_area = QScrollArea()
        self._result_area.setWidgetResizable(True)
        self._result_area.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
        """)
        
        result_w = QWidget()
        result_lay = QVBoxLayout(result_w)
        result_lay.setContentsMargins(16, 8, 16, 8)
        
        self._result_label = QLabel("")
        self._result_label.setWordWrap(True)
        self._result_label.setFont(QFont("Segoe UI", 9))
        self._result_label.setStyleSheet(f"color:{C.TEXT_MED}; background:transparent;")
        result_lay.addWidget(self._result_label)
        
        self._result_area.setWidget(result_w)
        self._result_area.hide()
        main_lay.addWidget(self._result_area)
    
    def start_scan(self, callback=None):
        """Inicia el escaneo épico"""
        self._scanning = True
        self._scan_y = 0
        self._scan_line = 0
        self._result = ""
        self._callback = callback
        
        self.show()
        self.setFixedHeight(self.EXPANDED_H)
        
        # Start animation
        if self._anim_timer:
            self._anim_timer.stop()
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._animate_scan)
        self._anim_timer.start(30)
        
        self._status.setText("Capturando pantalla...")
        self._progress.setValue(0)
    
    def _animate_scan(self):
        """Animación del escaneo"""
        if not self._scanning:
            return
        
        # Update scan position
        self._scan_line += 1
        
        if self._scan_line <= 30:
            # Phase 1: Scanning
            progress = int((self._scan_line / 30) * 100)
            self._progress.setValue(progress)
            self._status.setText("Analizando entorno... {}%".format(progress))
            self.update()
        elif self._scan_line == 31:
            # Phase 2: Processing complete
            self._progress.setValue(100)
            self._status.setText("Procesando con IA...")
            self.update()
        elif self._scan_line >= 50:
            # Phase 3: Done - show result
            self._scanning = False
            self._anim_timer.stop()
            self._show_result()
    
    def set_result(self, text: str):
        """Establece el resultado del análisis"""
        self._result = text
    
    def _show_result(self):
        """Muestra el resultado con efecto"""
        self._status.setText("Análisis completado")
        self._result_label.setText(self._result)
        self._result_area.show()
        
        if self._callback:
            self._callback(self._result)
    
    def stop_scan(self):
        """Detiene el escaneo"""
        self._scanning = False
        if self._anim_timer:
            self._anim_timer.stop()
        self.hide()
        self.setFixedHeight(0)
    
    def paintEvent(self, event):
        """Dibuja la línea de escaneo"""
        if not self._scanning:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw scan line
        if self._scan_line <= 30:
            y = int(self.height() * self._scan_line / 30)
            
            # Main scan line
            gradient = QLinearGradient(0, y-20, 0, y+20)
            gradient.setColorAt(0, QColor(0, 0, 0, 0))
            gradient.setColorAt(0.3, self._scan_color)
            gradient.setColorAt(0.5, QColor(255, 255, 255, 200))
            gradient.setColorAt(0.7, self._scan_color)
            gradient.setColorAt(1, QColor(0, 0, 0, 0))
            
            painter.fillRect(0, y-2, self.width(), 4, gradient)
            
            # Glow effect
            glow = QPainterPath()
            glow.addRect(0, y-30, self.width(), 60)
            painter.fillPath(glow, QColor(0, 212, 255, 15))
        
        painter.end()


# ═══════════════════════════════════════════════════════════
# LIVE CODE WIDGET  — typing animation for file creation
# ═══════════════════════════════════════════════════════════
class LiveCodeWidget(QWidget):
    """Shows a real-time 'coding' animation when NEXO creates a file."""

    EXPANDED_H = 210

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._content  = ""
        self._pos      = 0
        self._filename = ""
        self._done     = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)

        # Header row: status label + cursor blink
        self._status = QLabel("▶  Generando...")
        self._status.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._status.setStyleSheet(f"color:{C.GREEN}; background:transparent;")
        lay.addWidget(self._status)

        self._code = QTextEdit()
        self._code.setReadOnly(True)
        self._code.setFont(QFont("Consolas", 8))
        self._code.setStyleSheet(f"""
            QTextEdit {{
                background: {C.BG};
                color: {C.PRI};
                border: 1px solid {C.BORDER_A};
                border-radius: 4px;
                padding: 4px 6px;
                selection-background-color: {C.BORDER_A};
            }}
            QScrollBar:vertical {{ width: 4px; background: {C.BG}; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER_A}; border-radius: 2px; }}
        """)
        lay.addWidget(self._code)

        # Typing timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        # Height animation
        self._h_anim: QPropertyAnimation | None = None
        self.setMaximumHeight(0)

    def animate(self, filename: str, content: str, file_type: str) -> None:
        self._filename = filename
        self._content  = content[:4000]  # cap for performance
        self._pos      = 0
        self._done     = False

        suffix = Path(filename).suffix.lower()
        if file_type == "image" or not content:
            display = f"[archivo binario: {filename}]"
        else:
            display = ""

        self._code.setPlainText(display)
        self._status.setText(f"▶  Generando: {filename}")
        self._status.setStyleSheet(f"color:{C.GREEN}; background:transparent;")

        # Expand if collapsed
        if self.maximumHeight() < 20:
            self._h_anim = QPropertyAnimation(self, b"maximumHeight")
            self._h_anim.setDuration(200)
            self._h_anim.setStartValue(0)
            self._h_anim.setEndValue(self.EXPANDED_H)
            self._h_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._h_anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

        self._timer.stop()
        if content and file_type != "image":
            self._timer.start(18)   # ~55fps
        else:
            self._finish()

    def _tick(self) -> None:
        if self._pos >= len(self._content):
            self._timer.stop()
            self._finish()
            return
        chunk = self._content[self._pos:self._pos + 48]
        self._pos += 48
        cursor = self._code.textCursor()
        from PyQt6.QtGui import QTextCursor
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._code.setTextCursor(cursor)
        self._code.insertPlainText(chunk)
        sb = self._code.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _finish(self) -> None:
        self._done = True
        self._status.setText(f"✔  Guardado: {self._filename}")
        self._status.setStyleSheet(f"color:{C.PRI}; background:transparent;")


# ═══════════════════════════════════════════════════════════
# FILE CARD  — single entry in the files panel list
# ═══════════════════════════════════════════════════════════
class FileCard(QFrame):
    _ICONS = {
        "code":     "💻",
        "document": "📄",
        "image":    "🖼",
        "pdf":      "📋",
        "other":    "📁",
    }

    def __init__(self, parent: QWidget, path: str, name: str, file_type: str):
        super().__init__(parent)
        self._path = path
        self.setStyleSheet(f"""
            QFrame {{
                background: {C.PRI_GHO};
                border: 1px solid {C.BORDER};
                border-radius: 6px;
            }}
            QFrame:hover {{ border: 1px solid {C.BORDER_A}; }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)

        icon = QLabel(self._ICONS.get(file_type, "📁"))
        icon.setFont(QFont("Segoe UI Emoji", 14))
        icon.setFixedWidth(28)
        icon.setStyleSheet("background:transparent;")
        lay.addWidget(icon)

        info = QVBoxLayout()
        info.setSpacing(2)
        name_lbl = QLabel(name[:36] + ("…" if len(name) > 36 else ""))
        name_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        name_lbl.setStyleSheet(f"color:{C.TEXT}; background:transparent;")
        info.addWidget(name_lbl)
        ts = QLabel(_dt.now().strftime("%H:%M:%S"))
        ts.setFont(QFont("Segoe UI", 7))
        ts.setStyleSheet(f"color:{C.TEXT_MED}; background:transparent;")
        info.addWidget(ts)
        lay.addLayout(info)
        lay.addStretch()

        open_btn = QPushButton("Abrir")
        open_btn.setFixedSize(54, 26)
        open_btn.setFont(QFont("Segoe UI", 8))
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background:transparent; color:{C.PRI};
                border:1px solid {C.BORDER_A}; border-radius:4px;
            }}
            QPushButton:hover {{
                background:{C.PRI_GHO}; border:1px solid {C.PRI};
            }}
        """)
        open_btn.clicked.connect(self._open)
        lay.addWidget(open_btn)

    def _open(self) -> None:
        try:
            p = Path(self._path)
            if p.exists():
                os.startfile(str(p))
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
# FILES PANEL  — right sidebar that slides in/out
# ═══════════════════════════════════════════════════════════
class FilesPanel(QWidget):
    PANEL_W = 360

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._visible    = False
        self._file_count = 0
        self._slide_anim: QPropertyAnimation | None = None
        self._build()
        self.hide()

    def _build(self) -> None:
        self.setStyleSheet(f"""
            FilesPanel {{
                background: {C.PANEL};
                border-left: 1px solid {C.BORDER_A};
            }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ───────────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setFixedHeight(40)
        hdr.setStyleSheet(f"background:{C.DARK}; border-bottom:1px solid {C.BORDER_A};")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(12, 0, 10, 0)
        hdr_lay.setSpacing(6)

        ico = QLabel("📁")
        ico.setFont(QFont("Segoe UI Emoji", 12))
        ico.setStyleSheet("background:transparent;")
        hdr_lay.addWidget(ico)

        lbl = QLabel("ARCHIVOS GENERADOS")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{C.PRI}; background:transparent; letter-spacing:1px;")
        hdr_lay.addWidget(lbl)
        hdr_lay.addStretch()

        self._count_lbl = QLabel("0")
        self._count_lbl.setFont(QFont("Segoe UI", 8))
        self._count_lbl.setStyleSheet(
            f"color:{C.TEXT_MED}; background:transparent; padding:2px 6px;"
            f" border:1px solid {C.BORDER}; border-radius:8px;")
        hdr_lay.addWidget(self._count_lbl)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:{C.TEXT_MED};
                border:1px solid {C.BORDER}; border-radius:12px; font-size:10px; }}
            QPushButton:hover {{ color:{C.RED}; border-color:{C.RED}; }}
        """)
        close_btn.clicked.connect(self.toggle)
        hdr_lay.addWidget(close_btn)

        root.addWidget(hdr)

        # ── Live code section ─────────────────────────────────────────────────
        self._live = LiveCodeWidget(self)
        root.addWidget(self._live)

        # ── Separator ────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{C.BORDER};")
        root.addWidget(sep)

        # ── Scrollable file list ──────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background:transparent; border:none; }}
            QScrollBar:vertical {{ width:4px; background:{C.BG}; }}
            QScrollBar::handle:vertical {{ background:{C.BORDER_A}; border-radius:2px; }}
        """)
        self._list_widget = QWidget()
        self._list_widget.setStyleSheet(f"background:{C.PANEL};")
        self._list_lay = QVBoxLayout(self._list_widget)
        self._list_lay.setContentsMargins(8, 8, 8, 8)
        self._list_lay.setSpacing(6)
        self._list_lay.addStretch()

        # Empty state label
        self._empty_lbl = QLabel("Los archivos generados\naparecerán aquí.")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setFont(QFont("Segoe UI", 9))
        self._empty_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; padding:20px;")
        self._list_lay.insertWidget(0, self._empty_lbl)

        scroll.setWidget(self._list_widget)
        root.addWidget(scroll, stretch=1)

        # ── Footer: clear button ──────────────────────────────────────────────
        foot = QWidget()
        foot.setFixedHeight(36)
        foot.setStyleSheet(f"background:{C.DARK}; border-top:1px solid {C.BORDER};")
        foot_lay = QHBoxLayout(foot)
        foot_lay.setContentsMargins(10, 0, 10, 0)
        clear_btn = QPushButton("Limpiar lista")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setFont(QFont("Segoe UI", 8))
        clear_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:{C.TEXT_MED};
                border:1px solid {C.BORDER}; border-radius:4px; padding:2px 8px; }}
            QPushButton:hover {{ color:{C.RED}; border-color:{C.RED}; }}
        """)
        clear_btn.clicked.connect(self._clear)
        foot_lay.addStretch()
        foot_lay.addWidget(clear_btn)
        root.addWidget(foot)

    # ── Public API ────────────────────────────────────────────────────────────

    def add_file(self, path: str, name: str, content: str, file_type: str, mime: str) -> None:
        """Called (via signal) when a file is created by any action."""
        # Start live coding animation
        self._live.animate(name, content, file_type)

        # Show empty-state label removal on first file
        if self._file_count == 0 and self._empty_lbl:
            self._empty_lbl.hide()

        # Add card at top of list (most recent first)
        card = FileCard(self._list_widget, path, name, file_type)
        self._list_lay.insertWidget(0, card)

        self._file_count += 1
        self._count_lbl.setText(str(self._file_count))

        # Auto-open panel
        if not self._visible:
            self.toggle()

    def toggle(self) -> None:
        if self._visible:
            self._slide_out()
        else:
            self._slide_in()

    def update_geometry_for(self, W: int, H: int) -> None:
        """Call from _layout_orb_area when window resizes."""
        if self._visible:
            self.setGeometry(W - self.PANEL_W, 0, self.PANEL_W, H)

    # ── Slide animation ───────────────────────────────────────────────────────

    def _slide_in(self) -> None:
        self._visible = True
        p = self.parent()
        W, H = p.width(), p.height()
        self.setGeometry(W, 0, self.PANEL_W, H)
        self.show()
        self.raise_()

        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(240)
        anim.setStartValue(self.geometry())
        anim.setEndValue(QRect(W - self.PANEL_W, 0, self.PANEL_W, H))
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._slide_anim = anim

    def _slide_out(self) -> None:
        self._visible = False
        p = self.parent()
        W = p.width()
        H = self.height()

        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(200)
        anim.setStartValue(self.geometry())
        anim.setEndValue(QRect(W, 0, self.PANEL_W, H))
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self.hide)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._slide_anim = anim

    def _clear(self) -> None:
        self._file_count = 0
        self._count_lbl.setText("0")
        # Remove all FileCard widgets
        for i in reversed(range(self._list_lay.count())):
            item = self._list_lay.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), FileCard):
                w = item.widget()
                self._list_lay.removeWidget(w)
                w.deleteLater()
        self._empty_lbl.show()
        self._live.setMaximumHeight(0)


# ═══════════════════════════════════════════════════════════
# MAIN WINDOW  — full-screen NEXO layout
# ═══════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    _log_sig      = pyqtSignal(str)
    _state_sig    = pyqtSignal(str)
    _chunk_sig    = pyqtSignal(str)
    _shutdown_sig = pyqtSignal()
    _file_sig     = pyqtSignal(str, str, str, str, str)   # path,name,content,type,mime
    _config_sig   = pyqtSignal(dict)

    def __init__(self, face_path: str):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        scr = QApplication.primaryScreen().availableGeometry()
        self.move((scr.width() - _DEFAULT_W) // 2,
                  (scr.height() - _DEFAULT_H) // 2)

        self.on_text_command  = None
        self.on_stop_command  = None
        self.on_config_saved  = None
        self._config_sig.connect(self._on_config_saved)
        self._muted           = False
        self._cur_file: str | None = None
        self._cam_active      = False
        self._settings_ov: DeviceSettingsDialog | None = None
        self._console_ov:  ConsoleDialog | None = None
        self._orb_mini        = False
        self._orb_anim: QPropertyAnimation | None = None

        central = QWidget()
        central.setStyleSheet(f"background:{C.BG};")
        self.setCentralWidget(central)

        # ── Root: VBox ──────────────────────────────────
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header strip
        self._hdr_bar = self._build_header()
        root.addWidget(self._hdr_bar, stretch=0)

        # Beta banner (only visible when beta_config.py is present)
        self._beta_banner = self._build_beta_banner()
        if self._beta_banner:
            root.addWidget(self._beta_banner, stretch=0)

        # Orb area (fills everything except header and input)
        self._orb_area = QWidget()
        self._orb_area.setStyleSheet("background: transparent;")
        root.addWidget(self._orb_area, stretch=1)

        # Input strip at very bottom
        self._input_strip = self._build_input_strip()
        root.addWidget(self._input_strip, stretch=0)

        # ── Orb area children (absolutely positioned) ──
        # 1. Grid canvas — background
        self._grid_canvas = GridCanvas(self._orb_area)

        # 2. Orb container — animated
        self._orb_container = QWidget(self._orb_area)
        self._orb_container.setStyleSheet("background: transparent;")
        _ol = QVBoxLayout(self._orb_container)
        _ol.setContentsMargins(0, 0, 0, 0)
        self.orb = ParticleOrb()
        _ol.addWidget(self.orb)

        # 3. Transcript — below orb, always at bottom of orb_area
        self._transcript = TranscriptArea(self._orb_area)

        # 4. Floating widgets — all hidden at start
        self._weather_w = WeatherWidget(self._orb_area)
        self._todo_w    = TodoWidget(self._orb_area)
        self._spotify_w = SpotifyWidget(self._orb_area)
        self._system_w  = SystemWidget(self._orb_area)
        self._notes_w   = NotesWidget(self._orb_area)
        self._camera_w  = CameraWidget(self._orb_area)
        self._clock_w   = ClockWidget(self._orb_area)
        self._maps_w    = MapWebWidget(self._orb_area)
        self._image_w   = ImageWidget(self._orb_area)

        for w in [self._weather_w, self._todo_w, self._spotify_w,
                  self._system_w, self._notes_w, self._camera_w,
                  self._clock_w, self._maps_w, self._image_w]:
            w.hide()
            w.closed.connect(self._on_widget_closed)

        # System-wide camera floater (shown when minimised to tray)
        self._sys_floater      = SystemCameraFloater(restore_callback=self._show_from_tray)
        self._sys_hand_overlay = SystemHandOverlay()
        # Give the floater a reference to the camera widget (for toggle buttons)
        self._sys_floater.set_camera_widget(self._camera_w)
        # Wire camera frames / status into the floater
        self._camera_w._frame_sig.connect(self._sys_floater.update_frame)
        self._camera_w._status_sig.connect(self._sys_floater.update_status)
        # Wire hand cursor signals into the system-wide hand overlay
        self._camera_w._hand_cursor_sig.connect(self._sys_hand_overlay.on_cursor)
        self._camera_w._hand_fist_sig.connect(self._sys_hand_overlay.on_fist)
        # Give CameraWidget a reference so it can show/hide the overlay on start/stop
        self._camera_w.set_sys_hand_overlay(self._sys_hand_overlay)

        # 5. Drop zone (inside orb_area, floating bottom-center)
        self._drop_container = QWidget(self._orb_area)
        self._drop_container.setStyleSheet("background: transparent;")
        _dl = QVBoxLayout(self._drop_container)
        _dl.setContentsMargins(0, 0, 0, 0)
        self._drop = FileDropZone()
        self._drop.file_selected.connect(self._on_file)
        _dl.addWidget(self._drop)

        # 6. Files panel — right sidebar, hidden by default
        self._files_panel = FilesPanel(self._orb_area)

        # Signals
        self._log_sig.connect(self._route_log)
        self._state_sig.connect(self._apply_state)
        self._chunk_sig.connect(self._transcript.append_text)
        self._shutdown_sig.connect(self._quit_app)
        self._file_sig.connect(self._files_panel.add_file)

        # Subscribe to file creation events (thread-safe via Qt signal)
        if _HAS_FILE_EVENTS:
            _file_events.subscribe(
                lambda evt: self._file_sig.emit(
                    evt.path, evt.name, evt.content, evt.file_type, evt.mime
                )
            )

        # Clock
        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Cache for config values that are read on every state change
        self._thinking_sound_cached: bool = True   # populated below after _check_cfg

        # ── System Tray ──────────────────────────────────
        self._tray_icon: QSystemTrayIcon | None = None
        self._setup_tray()

        # Setup overlay
        self._overlay: SetupOverlay | None = None
        self._ready = self._check_cfg()
        if not self._ready:
            self._show_setup()
        # Populate config cache (avoids disk read on every orb state change)
        self._refresh_thinking_sound_cache()

        QShortcut(QKeySequence("F4"),    self).activated.connect(self._toggle_mute)
        QShortcut(QKeySequence("F11"),   self).activated.connect(self._toggle_fs)
        QShortcut(QKeySequence("Escape"),self).activated.connect(self._stop)

        # Ensure orb is centered on first show (before first resizeEvent fires)
        QTimer.singleShot(0,   self._safe_relayout)
        QTimer.singleShot(120, self._safe_relayout)   # second pass after Qt geometry pass

    def showEvent(self, event):
        super().showEvent(event)
        # Layout orb on first real show (window has actual dimensions now)
        QTimer.singleShot(50, self._safe_relayout)

    # ── System Tray ─────────────────────────────────────
    def _setup_tray(self):
        try:
            icon_path = str(BASE_DIR / "assets" / "nexo_icono.ico")
            if os.path.isfile(icon_path):
                icon = QIcon(icon_path)
            else:
                icon = QIcon()
            self._tray_icon = QSystemTrayIcon(icon, self)
            self._tray_icon.setToolTip("J.A.R.V.I.S")

            menu = QMenu()
            show_act = QAction("Mostrar NEXO", self)
            show_act.triggered.connect(self._show_from_tray)
            menu.addAction(show_act)

            settings_act = QAction("Configuración", self)
            settings_act.triggered.connect(self._toggle_settings)
            menu.addAction(settings_act)

            menu.addSeparator()

            quit_act = QAction("Salir", self)
            quit_act.triggered.connect(self._quit_app)
            menu.addAction(quit_act)

            self._tray_icon.setContextMenu(menu)
            self._tray_icon.activated.connect(self._tray_activated)
            self._tray_icon.show()
        except Exception as e:
            print(f"[Tray] Error: {e}")
            self._tray_icon = None

    def _show_from_tray(self):
        # Hide the floating overlays — the main window takes over again
        if hasattr(self, "_sys_floater"):
            self._sys_floater.hide()
        if hasattr(self, "_sys_hand_overlay"):
            self._sys_hand_overlay.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _quit_app(self):
        """Triggered by shutdown_nexo tool. Waits for farewell speech to finish first."""
        self._shutdown_pending = True
        # Delay first check: Gemini needs ~2s to process the tool response and start speaking
        QTimer.singleShot(2800, self._shutdown_check)

    def _shutdown_check(self):
        """Poll until orb leaves SPEAKING state, then quit after a grace period."""
        if getattr(self, '_shutdown_done', False):
            return
        if self.orb._state == "SPEAKING":
            # Still speaking — check again soon
            QTimer.singleShot(300, self._shutdown_check)
        else:
            # Speech finished — wait a beat then quit
            QTimer.singleShot(800, self._shutdown_now)

    def _shutdown_now(self):
        if getattr(self, '_shutdown_done', False):
            return
        self._shutdown_done = True
        if self._tray_icon:
            self._tray_icon.hide()
        QApplication.quit()
        import os
        os._exit(0)

    def closeEvent(self, event):
        """Minimize to tray instead of closing.
        If camera tracking is active, keep a floating overlay on screen."""
        if self._tray_icon and self._tray_icon.isVisible():
            event.ignore()

            # ── Check BEFORE hide() — children are invisible after hide() ───
            _cam_active    = hasattr(self, "_camera_w") and getattr(self._camera_w, "_active", False)
            _tracking      = hasattr(self, "_camera_w") and self._camera_w.is_tracking_active()
            _cam_tracking  = _cam_active or _tracking
            _hand_on       = hasattr(self, "_camera_w") and getattr(self._camera_w, "_hand_active", False)

            self.hide()

            # ── Show system-wide camera floater if camera/tracking is running ─
            if _cam_tracking and hasattr(self, "_sys_floater"):
                self._sys_floater.show()
                self._sys_floater.raise_()
                # Screen-wide hand cursor overlay (only when hand control is on)
                if _hand_on and hasattr(self, "_sys_hand_overlay"):
                    self._sys_hand_overlay.show()
                    self._sys_hand_overlay.raise_()

            if self._tray_icon:
                _msg = (
                    "Tracking activo — flotante visible en pantalla."
                    if _cam_tracking
                    else "NEXO sigue ejecutándose en segundo plano."
                )
                self._tray_icon.showMessage(
                    "J.A.R.V.I.S",
                    _msg,
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )
        else:
            event.accept()

    def moveEvent(self, event):
        super().moveEvent(event)
        # Baja FPS del orb durante el arrastre para dragging fluido
        if hasattr(self, 'orb') and hasattr(self.orb, '_timer'):
            self.orb._timer.setInterval(50)
        if not hasattr(self, '_move_restore_timer'):
            self._move_restore_timer = QTimer(self)
            self._move_restore_timer.setSingleShot(True)
            self._move_restore_timer.timeout.connect(self._restore_orb_fps)
        self._move_restore_timer.start(250)

    def _restore_orb_fps(self):
        if not hasattr(self, 'orb') or not hasattr(self.orb, '_timer'):
            return
        interval = 33 if getattr(self.orb, '_state', '') in ('IDLE', '') else 16
        self.orb._timer.setInterval(interval)

    # ── Header ──────────────────────────────────────────
    def _build_beta_banner(self) -> QWidget | None:
        """Returns a fixed 26px beta banner strip, or None if not running as Beta."""
        if not (BASE_DIR / "beta_config.py").exists():
            return None
        w = QWidget()
        w.setFixedHeight(26)
        w.setStyleSheet(
            "background: #12043a;"
            "border-bottom: 1px solid #3d1a6b;"
        )
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(0)

        star = QLabel("✦")
        star.setFont(QFont("Segoe UI Emoji", 8))
        star.setStyleSheet("color:#7c3aed; background:transparent; padding-right:6px;")
        lay.addWidget(star)

        msg = QLabel(
            "NEXO BETA GRATUITA  —  "
            "Actualizá a PRO para acceder a funciones únicas de NEXO"
        )
        msg.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        msg.setStyleSheet("color:#a78bfa; background:transparent; letter-spacing:0.5px;")
        lay.addWidget(msg, stretch=1)

        pro_btn = QPushButton("  Conocer PRO  →")
        pro_btn.setFixedSize(110, 18)
        pro_btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        pro_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pro_btn.setStyleSheet(
            "QPushButton { background:#7c3aed; color:#ffffff; border:none;"
            " border-radius:4px; padding:0 8px; }"
            "QPushButton:hover { background:#8b5cf6; }"
        )
        pro_btn.clicked.connect(
            lambda: __import__("webbrowser").open("https://market.amssystems.com.ar/")
        )
        lay.addWidget(pro_btn)
        return w

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(HEADER_H)
        w.setStyleSheet(f"background:{C.DARK}; border-bottom:1px solid rgba(13,37,66,0.4);")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(12, 0, 12, 0)

        def _hdr_btn(icon, tooltip, slot):
            b = QPushButton(icon)
            b.setFixedSize(28, 28)
            b.setFont(QFont("Segoe UI Emoji", 11))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(tooltip)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 14px;
                }}
                QPushButton:hover {{
                    color: {C.PRI}; border: 1px solid {C.PRI}; background: {C.PRI_GHO};
                }}
            """)
            b.clicked.connect(slot)
            return b

        # ⚙ Settings
        gear = _hdr_btn("⚙", "Configuración", self._toggle_settings)
        lay.addWidget(gear)

        # ▸ Console log
        console_btn = _hdr_btn("▸", "Consola / Log", self._toggle_console)
        lay.addWidget(console_btn)

        # 📁 Files panel
        self._files_btn = _hdr_btn("📁", "Archivos generados", self._toggle_files)
        lay.addWidget(self._files_btn)

        lay.addStretch()

        # Title
        title = QLabel("J·A·R·V·I·S")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{C.PRI}; background:transparent; letter-spacing:4px;")
        lay.addWidget(title)
        lay.addStretch()

        # Clock + date
        right_col = QVBoxLayout()
        right_col.setSpacing(0)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color:{C.PRI}; background:transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Segoe UI", 7))
        self._date_lbl.setStyleSheet(f"color:{C.TEXT_MED}; background:transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        lay.addLayout(right_col)
        return w

    def _tick_clock(self):
        now = _dt.now(_BA_TZ)
        self._clock_lbl.setText(now.strftime("%H:%M:%S"))
        self._date_lbl.setText(now.strftime("%a %d %b %Y"))

    # ── Input strip ─────────────────────────────────────
    def _build_input_strip(self) -> QWidget:
        outer = QWidget()
        outer.setFixedHeight(INPUT_H)
        outer.setStyleSheet(f"background:{C.DARK}; border-top:1px solid rgba(13,37,66,0.4);")
        lay = QHBoxLayout(outer)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(6)

        # Mic
        self._mic_btn = QPushButton("🎙")
        self._mic_btn.setFixedSize(44, 44)
        self._mic_btn.setFont(QFont("Segoe UI Emoji" if _OS == "Windows" else "Arial", 18))
        self._mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mic_btn.setToolTip("Micrófono (F4)")
        self._mic_btn.clicked.connect(self._toggle_mute)
        self._style_mic(False)
        lay.addWidget(self._mic_btn)

        # Camera
        self._cam_btn = QPushButton("📷")
        self._cam_btn.setFixedSize(38, 38)
        self._cam_btn.setFont(QFont("Segoe UI Emoji" if _OS == "Windows" else "Arial", 16))
        self._cam_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cam_btn.setToolTip("Cámara")
        self._cam_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0,212,255,0.06); color: {C.TEXT_DIM};
                border: none; border-radius: 19px;
            }}
            QPushButton:hover {{
                background: rgba(0,212,255,0.15); color: {C.PRI};
            }}
        """)
        self._cam_btn.clicked.connect(self._toggle_cam)
        lay.addWidget(self._cam_btn)

        # Drop zone
        self._drop = FileDropZone()
        self._drop.file_selected.connect(self._on_file)
        lay.addWidget(self._drop, stretch=0)

        # Divider
        dv = QFrame(); dv.setFrameShape(QFrame.Shape.VLine); dv.setFixedWidth(1)
        dv.setStyleSheet(f"background:{C.BORDER};border:none;")
        lay.addWidget(dv)

        # Text input
        self._input = QLineEdit()
        self._input.setPlaceholderText("Mensaje para NEXO…")
        self._input.setFont(QFont("Segoe UI", 11))
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(7,15,26,180); color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 22px;
                padding: 0 16px;
            }}
            QLineEdit:focus {{
                border: 1px solid {C.PRI_DIM};
            }}
        """)
        self._input.setFixedHeight(44)
        self._input.returnPressed.connect(self._send)
        lay.addWidget(self._input, stretch=1)

        # Send
        self._send_btn = QPushButton("➤")
        self._send_btn.setFixedSize(40, 40)
        self._send_btn.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0,212,255,0.10); color:{C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 20px;
            }}
            QPushButton:hover {{
                background: rgba(0,212,255,0.22); border:1px solid {C.PRI};
            }}
        """)
        self._send_btn.clicked.connect(self._send)
        lay.addWidget(self._send_btn)

        # Improvement 2: Export transcript button
        self._export_btn = QPushButton("💾")
        self._export_btn.setFixedSize(30, 30)
        self._export_btn.setFont(QFont("Segoe UI Emoji", 13))
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setToolTip("Exportar conversación (.txt)")
        self._export_btn.setStyleSheet(f"""
            QPushButton {{background:transparent;color:{C.TEXT_DIM};border:none;border-radius:15px;}}
            QPushButton:hover {{color:{C.PRI};background:{C.PRI_GHO};}}
        """)
        self._export_btn.clicked.connect(self._export_transcript)
        lay.addWidget(self._export_btn)

        # Fullscreen
        fs = QPushButton("⛶")
        fs.setFixedSize(30, 30)
        fs.setFont(QFont("Segoe UI", 13))
        fs.setCursor(Qt.CursorShape.PointingHandCursor)
        fs.setToolTip("Pantalla completa (F11)")
        fs.setStyleSheet(f"""
            QPushButton {{background:transparent;color:{C.TEXT_DIM};border:none;border-radius:15px;}}
            QPushButton:hover {{color:{C.PRI};background:{C.PRI_GHO};}}
        """)
        fs.clicked.connect(self._toggle_fs)
        lay.addWidget(fs)

        # Stop
        stop = QPushButton("■")
        stop.setFixedSize(30, 30)
        stop.setFont(QFont("Segoe UI", 12))
        stop.setCursor(Qt.CursorShape.PointingHandCursor)
        stop.setToolTip("Detener (Esc)")
        stop.setStyleSheet(f"""
            QPushButton {{background:transparent;color:{C.RED};border:none;border-radius:15px;}}
            QPushButton:hover {{background:rgba(255,51,85,0.14);}}
        """)
        stop.clicked.connect(self._stop)
        lay.addWidget(stop)

        return outer

    # ── Layout of orb_area (called from resizeEvent) ────
    def _layout_orb_area(self):
        if not hasattr(self, '_orb_area'):
            return
        W = self._orb_area.width()
        H = self._orb_area.height()
        if W < 20 or H < 20:
            return

        # Grid canvas — always fills everything
        self._grid_canvas.setGeometry(0, 0, W, H)

        if not self._orb_mini:
            # Orb always centered in the orb_area with proportional size
            orb_radius = min(W, H - TRANS_H) * 0.38
            orb_size = int(orb_radius * 2.6)
            orb_x = (W - orb_size) // 2
            orb_y = (H - TRANS_H - orb_size) // 2
            self._orb_container.setGeometry(orb_x, orb_y, orb_size, orb_size)
            # Transcript overlays the bottom strip (semi-transparent bg)
            self._transcript.setGeometry(0, H - TRANS_H, W, TRANS_H)
        else:
            # Mini: orb at bottom-left corner
            mx = 18
            my = H - TRANS_H - MINI_H - 18
            self._orb_container.setGeometry(mx, my, MINI_W, MINI_H)
            self._transcript.setGeometry(0, H - TRANS_H, W, TRANS_H)

        # Drop zone floating bottom-center of orb area (above transcript)
        dw = min(W - 200, 440)
        self._drop_container.setGeometry(
            (W - dw) // 2, H - TRANS_H - 54, dw, 44
        )

        # Files panel — anchored to right edge, full height of orb area
        if hasattr(self, '_files_panel'):
            self._files_panel.update_geometry_for(W, H)

    def changeEvent(self, event):
        """Handle window state changes (maximize/restore/minimize) without crashing."""
        try:
            super().changeEvent(event)
        except Exception:
            pass
        try:
            from PyQt6.QtCore import QEvent
            if event.type() != QEvent.Type.WindowStateChange:
                return
            try:
                old_state = event.oldState()
                new_state = self.windowState()
            except Exception:
                return
            was_fullscreen = bool(old_state & Qt.WindowState.WindowFullScreen)
            minimized  = bool(new_state & Qt.WindowState.WindowMinimized)
            maximized  = bool(new_state & Qt.WindowState.WindowMaximized)
            fullscreen = bool(new_state & Qt.WindowState.WindowFullScreen)

            # Stop any running geometry animations before state changes
            try:
                if hasattr(self, '_orb_anim') and self._orb_anim is not None:
                    if self._orb_anim.state() != QPropertyAnimation.State.Stopped:
                        self._orb_anim.stop()
                    self._orb_anim = None
            except Exception:
                self._orb_anim = None

            # Pause heavy paint widgets while minimized
            try:
                if hasattr(self, '_grid_canvas') and self._grid_canvas:
                    self._grid_canvas.setUpdatesEnabled(not minimized)
            except Exception:
                pass
            try:
                if hasattr(self, 'orb') and self.orb:
                    self.orb.setUpdatesEnabled(not minimized)
            except Exception:
                pass

            if minimized:
                return

            # Schedule layout refresh — always delayed to let Qt finish geometry pass
            delay = 80 if (was_fullscreen or maximized) else 50
            QTimer.singleShot(delay, self._safe_relayout)
            if was_fullscreen and not fullscreen:
                QTimer.singleShot(160, self._safe_relayout)  # extra pass after fullscreen exit
        except Exception as _ce:
            print(f"[UI] changeEvent error: {_ce}")

    def _safe_relayout(self):
        """Relayout the orb area, skipping if window is in a bad state."""
        try:
            if not self.isVisible() or self.isMinimized():
                return
            if not hasattr(self, '_orb_area') or self._orb_area is None:
                return
            try:
                W = self._orb_area.width()
                H = self._orb_area.height()
            except Exception:
                return
            if W < 20 or H < 20:
                QTimer.singleShot(100, self._safe_relayout)
                return
            self._layout_orb_area()
        except Exception as e:
            print(f"[UI] relayout error: {e}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Skip layout while window is minimized (zero-size widgets cause crashes)
        if self.isMinimized():
            return
        try:
            if not hasattr(self, '_orb_area') or not self._orb_area:
                return
            # Don't override geometry during animation
            anim_running = (
                self._orb_anim is not None
                and hasattr(self._orb_anim, 'state')
                and self._orb_anim.state() == QPropertyAnimation.State.Running
            )
            if anim_running:
                W = self._orb_area.width()
                H = self._orb_area.height()
                if W > 0 and H > 0:
                    self._grid_canvas.setGeometry(0, 0, W, H)
            else:
                self._layout_orb_area()

            if self._overlay and self._overlay.isVisible():
                ow, oh = 500, 430
                cw = self.centralWidget()
                if cw:
                    self._overlay.setGeometry(
                        (cw.width() - ow) // 2, (cw.height() - oh) // 2, ow, oh)
        except Exception:
            pass

    # ── Mini / Normal orb animation ──────────────────────
    def _set_orb_mini(self, mini: bool):
        if mini == self._orb_mini:
            return
        self._orb_mini = mini
        W = self._orb_area.width()
        H = self._orb_area.height()
        if W < 20 or H < 20:
            return

        if mini:
            # Orb slides to bottom-left corner with margin
            mx = 18
            my = H - TRANS_H - MINI_H - 18
            orb_target = QRect(mx, my, MINI_W, MINI_H)
            trans_target = QRect(0, H - TRANS_H, W, TRANS_H)
        else:
            orb_radius = min(W, H - TRANS_H) * 0.38
            orb_size = int(orb_radius * 2.6)
            orb_x = (W - orb_size) // 2
            orb_y = (H - TRANS_H - orb_size) // 2
            orb_target = QRect(orb_x, orb_y, orb_size, orb_size)
            trans_target = QRect(0, H - TRANS_H, W, TRANS_H)

        anim1 = QPropertyAnimation(self._orb_container, b"geometry", self)
        anim1.setDuration(280)
        anim1.setStartValue(self._orb_container.geometry())
        anim1.setEndValue(orb_target)
        anim1.setEasingCurve(QEasingCurve.Type.InOutCubic)

        anim2 = QPropertyAnimation(self._transcript, b"geometry", self)
        anim2.setDuration(280)
        anim2.setStartValue(self._transcript.geometry())
        anim2.setEndValue(trans_target)
        anim2.setEasingCurve(QEasingCurve.Type.InOutCubic)

        grp = QParallelAnimationGroup(self)
        grp.addAnimation(anim1)
        grp.addAnimation(anim2)
        grp.start(QParallelAnimationGroup.DeletionPolicy.DeleteWhenStopped)
        self._orb_anim = grp

    def _show_widget(self, widget: DraggableWidget, make_orb_mini: bool = True):
        if make_orb_mini:
            self._set_orb_mini(True)
        # Center the widget in the orb area for a clean, minimalist look
        W = self._orb_area.width()
        H = self._orb_area.height()
        ww = widget.width()
        wh = widget.height()
        cx = (W - ww) // 2
        cy = max((H - wh) // 2 - 20, 10)
        widget.move(cx, cy)
        widget.show_animated()
        widget.raise_()

    def _hide_all_widgets(self):
        for w in [self._clock_w, self._system_w, self._weather_w,
                  self._spotify_w, self._todo_w, self._notes_w,
                  self._camera_w, self._maps_w, self._image_w]:
            if w.isVisible():
                w.hide_animated()
        self._camera_w.stop_camera()
        self._cam_active = False
        self._style_cam(False)
        self._set_orb_mini(False)

    def _on_widget_closed(self, _widget=None):
        """Called when any dashboard widget is closed via its ✕ button.
        Restores the full-screen orb if no other widgets remain visible."""
        QTimer.singleShot(300, self._check_restore_orb)

    def _check_restore_orb(self):
        """If no dashboard widget is visible, return orb to full-screen centre."""
        any_visible = any(
            w.isVisible() for w in [
                self._weather_w, self._todo_w, self._spotify_w,
                self._system_w, self._notes_w, self._camera_w,
                self._clock_w, self._maps_w, self._image_w,
            ]
        )
        if not any_visible:
            self._set_orb_mini(False)

    # ── Log routing ─────────────────────────────────────
    def _route_log(self, text: str):
        tl = text.lower().strip()
        if tl.startswith(("tú:", "tu:", "you:")):
            return
        if tl.startswith("nexo:"):
            content = text[text.index(":") + 1:].strip()
            self._transcript.append_text("__clear__")
            self._transcript.append_text(content)
            return
        if tl.startswith("err:") or "❌" in text:
            cleaned = re.sub(r'^err:\s*', '', text, flags=re.IGNORECASE)
            self._transcript.append_text("__clear__")
            self._transcript.append_text(f"❌ {cleaned}")
            return
        if tl.startswith("archivo:"):
            return

        # Widget commands
        if tl.startswith("__weather__:"):
            parts = text[12:].split("|")
            # Extended format: city|temp|desc|icon|feels|humid|wind|forecast
            # Basic format:    city|temp|desc  (legacy, icon optional at [3])
            city     = parts[0] if len(parts) > 0 else "—"
            temp     = parts[1] if len(parts) > 1 else "—"
            desc     = parts[2] if len(parts) > 2 else "Sin datos"
            icon     = parts[3] if len(parts) > 3 else "🌤"
            feels    = parts[4] if len(parts) > 4 else ""
            humid    = parts[5] if len(parts) > 5 else ""
            wind     = parts[6] if len(parts) > 6 else ""
            forecast = parts[7] if len(parts) > 7 else ""

            # Auto-detect icon from description if no icon provided
            if not icon or icon == "—":
                icons = {"clear": "☀", "sunny": "☀", "cloud": "⛅", "rain": "🌧",
                         "storm": "⛈", "snow": "❄", "wind": "💨", "fog": "🌫",
                         "hot": "🌡", "cold": "🥶", "drizzle": "🌦"}
                icon = "🌤"
                for k, v in icons.items():
                    if k in desc.lower():
                        icon = v; break

            self._weather_w.update_weather(city, temp, desc, icon, feels, humid, wind, forecast)
            self._show_widget(self._weather_w, make_orb_mini=True)
            return

        if tl.startswith("__todo__:"):
            self._todo_w.add_todo(text[9:])
            self._show_widget(self._todo_w, make_orb_mini=True)
            return

        if tl.startswith("__spotify__:"):
            parts = text[12:].split("|")
            song       = parts[0] if parts else ""
            artist     = parts[1] if len(parts) > 1 else ""
            album      = parts[2] if len(parts) > 2 else ""
            try:
                dur_ms = int(parts[3]) if len(parts) > 3 else 0
            except (ValueError, IndexError):
                dur_ms = 0
            try:
                prog_ms = int(parts[4]) if len(parts) > 4 else 0
            except (ValueError, IndexError):
                prog_ms = 0
            is_playing = (parts[5].lower() == "true") if len(parts) > 5 else True
            self._spotify_w.update_spotify(song, artist, album, dur_ms, prog_ms, is_playing)
            self._show_widget(self._spotify_w, make_orb_mini=True)
            return

        if tl.startswith("__system__"):
            self._show_widget(self._system_w, make_orb_mini=True)
            return

        if tl.startswith("__notes__"):
            self._show_widget(self._notes_w, make_orb_mini=True)
            return

        if tl.startswith("__image__:"):
            raw = text[10:]
            paths = [p.strip() for p in raw.split("|") if p.strip()]
            if paths:
                self._image_w.set_images(paths)
                self._show_widget(self._image_w, make_orb_mini=True)
            return

        if tl.startswith("__hide__"):
            self._hide_all_widgets()
            return

        if tl.startswith("__maps__:"):
            try:
                raw = text[9:]
                data = json.loads(raw)
                self._maps_w.load_route(data)
                W = self._orb_area.width()
                H = self._orb_area.height()
                # Large map: use most available space (padding 20px each side)
                mw = max(800, min(1200, W - 40))
                mh = max(520, min(760, H - 40))
                self._maps_w.resize(mw, mh)
                self._maps_w.move(
                    max(10, (W - mw) // 2),
                    max(10, (H - mh) // 2),
                )
                self._show_widget(self._maps_w, make_orb_mini=True)
            except Exception as ex:
                print(f"[UI] maps widget error: {ex}")
            return

        if tl.startswith("__orb_mini__"):
            val = tl.split(":")[-1].strip()
            self._set_orb_mini(val in ("true", "1"))
            return

        if tl.startswith("__widget_show__:"):
            name_w = text[16:].strip().lower()
            widget_map = {
                "weather": self._weather_w, "clima": self._weather_w,
                "spotify": self._spotify_w, "musica": self._spotify_w, "música": self._spotify_w,
                "system":  self._system_w,  "sistema": self._system_w,
                "notes":   self._notes_w,   "notas": self._notes_w,
                "todo":    self._todo_w,     "tareas": self._todo_w,
                "maps":    self._maps_w,     "mapas": self._maps_w,
                "image":   self._image_w,    "imagen": self._image_w,
                "camera":  self._camera_w,   "camara": self._camera_w, "cámara": self._camera_w,
            }
            w = widget_map.get(name_w)
            if w:
                if name_w in ("camera", "camara", "cámara"):
                    self._camera_w.start_camera()
                self._show_widget(w, make_orb_mini=True)
            return

        if tl.startswith("__widget_close__:"):
            name_w = text[17:].strip().lower()
            widget_map = {
                "weather": self._weather_w, "clima": self._weather_w,
                "spotify": self._spotify_w, "musica": self._spotify_w, "música": self._spotify_w,
                "system":  self._system_w,  "sistema": self._system_w,
                "notes":   self._notes_w,   "notas": self._notes_w,
                "todo":    self._todo_w,     "tareas": self._todo_w,
                "maps":    self._maps_w,     "mapas": self._maps_w,
                "image":   self._image_w,    "imagen": self._image_w,
                "camera":  self._camera_w,   "camara": self._camera_w, "cámara": self._camera_w,
            }
            w = widget_map.get(name_w)
            if w:
                if name_w in ("camera", "camara", "cámara"):
                    self._camera_w.stop_camera()
                if hasattr(w, "hide_animated"):
                    w.hide_animated()
                else:
                    w.hide()
            return

    # ── State / audio ───────────────────────────────────
    def _apply_state(self, state: str):
        self.orb.set_state(state)
        self.orb.speaking = (state == "SPEAKING")
        # Only play thinking sounds if user hasn't disabled them
        if self._thinking_sound_enabled():
            if state in ("THINKING", "PROCESSING", "LOADING", "SEARCHING"):
                start_thinking_sound()
            else:
                stop_thinking_sound()
        else:
            stop_thinking_sound()

    def _thinking_sound_enabled(self) -> bool:
        # Use cached value — avoids disk read on every state change (can be very frequent)
        return self._thinking_sound_cached

    def _refresh_thinking_sound_cache(self):
        """Re-read config from disk. Called once on init and again when settings are saved."""
        try:
            self._thinking_sound_cached = json.loads(
                API_FILE.read_text(encoding="utf-8")
            ).get("thinking_sound", True)
        except Exception:
            self._thinking_sound_cached = True

    def _on_file(self, path: str):
        self._cur_file = path
        if self.on_text_command:
            p = Path(path)
            audio_exts = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma', '.opus', '.webm'}
            if p.suffix.lower() in audio_exts:
                # Signal main.py to process as audio file (not text command)
                msg = (f"[AUDIO_FILE] path={path} | name={p.name} | "
                       f"type={p.suffix.lstrip('.')}")
            else:
                msg = (f"[FILE_UPLOADED] path={path} | name={p.name} | "
                       f"type={p.suffix.lstrip('.')} | size={_fmtsz(p.stat().st_size)} | "
                       f"Briefly tell the user you can see '{p.name}' has been uploaded "
                       f"and ask what they'd like to do with it.")
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.orb.set_state("MUTED" if self._muted else "LISTENING")
        self._style_mic(self._muted)

    def _toggle_cam(self):
        self._cam_active = not self._cam_active
        self._style_cam(self._cam_active)
        if self._cam_active:
            self._show_widget(self._camera_w, make_orb_mini=True)
            self._camera_w.start_camera()
        else:
            self._camera_w.stop_camera()
            self._camera_w.hide_animated()
            # Restore orb if no other widgets visible
            any_visible = any(
                w.isVisible() for w in [
                    self._weather_w, self._todo_w, self._spotify_w,
                    self._system_w, self._notes_w, self._clock_w,
                    self._maps_w, self._image_w
                ]
            )
            if not any_visible:
                self._set_orb_mini(False)

    def _style_cam(self, active: bool):
        self._cam_btn.setStyleSheet(f"""
            QPushButton {{
                background: {"rgba(0,212,255,0.18)" if active else "rgba(0,212,255,0.06)"};
                color: {C.PRI if active else C.TEXT_DIM};
                border: none; border-radius: 19px;
            }}
            QPushButton:hover {{
                background: rgba(0,212,255,0.22); color: {C.PRI};
            }}
        """)

    def _style_mic(self, muted: bool):
        if muted:
            self._mic_btn.setText("🔇")
            self._mic_btn.setStyleSheet(f"""
                QPushButton {{
                    background:rgba(255,51,102,0.12); color:{C.MUTED_C};
                    border:none; border-radius:22px;
                }}
            """)
        else:
            self._mic_btn.setText("🎙")
            self._mic_btn.setStyleSheet(f"""
                QPushButton {{
                    background:rgba(0,255,136,0.07); color:{C.GREEN};
                    border:none; border-radius:22px;
                }}
                QPushButton:hover {{background:rgba(0,255,136,0.16);}}
            """)

    def _toggle_fs(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        QTimer.singleShot(100, self._safe_relayout)

    def _toggle_settings(self):
        if self._settings_ov and self._settings_ov.isVisible():
            self._settings_ov.hide()
            return
        if not self._settings_ov:
            self._settings_ov = DeviceSettingsDialog(self.centralWidget())
            self._settings_ov.config_saved.connect(self._config_sig)
        cw = self.centralWidget()
        sw, sh = 700, 640
        self._settings_ov.setGeometry(
            (cw.width() - sw) // 2, (cw.height() - sh) // 2, sw, sh)
        self._settings_ov.show()
        self._settings_ov.raise_()

    def _on_config_saved(self, cfg: dict):
        # Refresh cached config values so no disk I/O on hot paths
        self._refresh_thinking_sound_cache()
        if callable(self.on_config_saved):
            self.on_config_saved(cfg)

    def _toggle_files(self) -> None:
        """Toggle the right-side files panel."""
        if hasattr(self, '_files_panel'):
            self._files_panel.toggle()

    def _toggle_console(self):
        if self._console_ov and self._console_ov.isVisible():
            self._console_ov.hide()
            return
        if not self._console_ov:
            self._console_ov = ConsoleDialog(self.centralWidget())
        cw = self.centralWidget()
        cw_w, cw_h = 680, 420
        self._console_ov.setGeometry(
            (cw.width() - cw_w) // 2, (cw.height() - cw_h) // 2, cw_w, cw_h)
        self._console_ov.show()
        self._console_ov.raise_()

    def _send(self):
        txt = self._input.text().strip()
        if not txt:
            return
        self._input.clear()
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _stop(self):
        if self.on_stop_command:
            self.on_stop_command()

    # ── Improvement 2: Export transcript ──────────────────────
    def _export_transcript(self):
        """Save the full chat log to a timestamped .txt file next to main.py."""
        try:
            from datetime import datetime as _dt
            ts   = _dt.now().strftime("%Y%m%d_%H%M%S")
            path = BASE_DIR / f"nexo_transcript_{ts}.txt"
            # Pull raw text from the transcript widget
            raw = ""
            if hasattr(self, "_transcript") and hasattr(self._transcript, "_te"):
                raw = self._transcript._te.toPlainText()
            elif hasattr(self, "_transcript"):
                try:
                    raw = self._transcript.toPlainText()
                except Exception:
                    pass
            # Also grab anything in the console
            if hasattr(self, "_console_log") and hasattr(self._console_log, "toPlainText"):
                raw += "\n\n--- LOG ---\n" + self._console_log.toPlainText()
            path.write_text(raw or "(conversación vacía)", encoding="utf-8")
            # Brief toast notification via status bar
            self.statusBar().showMessage(f"💾  Conversación exportada → {path.name}", 4000)
            print(f"[NEXO] 💾 Transcript exportado: {path}")
        except Exception as _exp_err:
            print(f"[NEXO] Export error: {_exp_err}")

    def set_audio_level(self, level: float):
        self.orb.set_audio(level)

    def _check_cfg(self) -> bool:
        if not API_FILE.exists():
            return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 500, 430
        ov.setGeometry((cw.width() - ow) // 2, (cw.height() - oh) // 2, ow, oh)
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(
            json.dumps({"gemini_api_key": key, "os_system": os_name}, indent=4),
            encoding="utf-8")
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")


# ═══════════════════════════════════════════════════════════
# PUBLIC API  — drop-in replacement for original NexoUI
# ═══════════════════════════════════════════════════════════
class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app

    def mainloop(self):
        self._app.exec()

    def protocol(self, *_):
        pass


def _build_splash(app: "QApplication") -> "QSplashScreen | None":
    """Build and return the NEXO startup splash screen."""
    try:
        from PyQt6.QtGui import QPixmap, QPainter, QFont, QLinearGradient, QBrush
        from PyQt6.QtCore import Qt

        W, H = 560, 320
        pix = QPixmap(W, H)
        pix.fill(QColor(0, 0, 0, 0))  # transparent base

        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background gradient
        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0.0, QColor(5,  12, 20, 255))
        grad.setColorAt(1.0, QColor(3,  10, 16, 255))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, W, H, 18, 18)

        # Border
        pri_hex = C.PRI.lstrip("#")
        pr = int(pri_hex[0:2], 16)
        pg = int(pri_hex[2:4], 16)
        pb = int(pri_hex[4:6], 16)
        p.setPen(QPen(QColor(pr, pg, pb, 180), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(2, 2, W-4, H-4, 16, 16)

        # Logo text
        font_logo = QFont("Segoe UI", 36, QFont.Weight.Bold)
        font_logo.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 10)
        p.setFont(font_logo)
        p.setPen(QColor(pr, pg, pb, 255))
        p.drawText(QRectF(0, 60, W, 70), Qt.AlignmentFlag.AlignCenter, "J·A·R·V·I·S")

        # Subtitle
        font_sub = QFont("Segoe UI", 10)
        p.setFont(font_sub)
        p.setPen(QColor(pr, pg, pb, 160))
        p.drawText(QRectF(0, 140, W, 30), Qt.AlignmentFlag.AlignCenter,
                   "Iniciando asistente de inteligencia artificial…")

        # Dots animation placeholder
        font_dots = QFont("Segoe UI", 9)
        p.setFont(font_dots)
        p.setPen(QColor(pr, pg, pb, 120))
        p.drawText(QRectF(0, 200, W, 28), Qt.AlignmentFlag.AlignCenter,
                   "Cargando módulos y configuración del sistema")

        # AMS Systems credit
        font_small = QFont("Segoe UI", 7)
        p.setFont(font_small)
        p.setPen(QColor(pr, pg, pb, 80))
        p.drawText(QRectF(0, H - 32, W, 20), Qt.AlignmentFlag.AlignCenter,
                   "AMS Systems  •  @amssystems06")

        p.end()

        splash = QSplashScreen(pix)
        splash.setWindowFlags(
            Qt.WindowType.SplashScreen |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        splash.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Center splash on screen
        scr = app.primaryScreen().availableGeometry()
        splash.move((scr.width() - W) // 2, (scr.height() - H) // 2)

        return splash
    except Exception as _se:
        print(f"[Splash] {_se}")
        return None


class NexoUI:
    """Drop-in replacement. Same public API as original."""

    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        # Apply saved theme stylesheet at startup
        _apply_theme_stylesheet(self._app, _load_theme())

        # ── Splash screen — shown while main window loads ──────────────────────
        self._splash: QSplashScreen | None = None
        try:
            self._splash = _build_splash(self._app)
            if self._splash:
                self._splash.show()
                self._app.processEvents()
        except Exception:
            self._splash = None

        self._win = MainWindow(face_path)
        self._win.show()

        # Close splash once main window is ready
        if self._splash:
            try:
                self._splash.finish(self._win)
            except Exception:
                pass
            self._splash = None

        self.root = _RootShim(self._app)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_stop_command(self):
        return self._win.on_stop_command

    @on_stop_command.setter
    def on_stop_command(self, cb):
        self._win.on_stop_command = cb

    @property
    def on_config_saved(self):
        return self._win.on_config_saved

    @on_config_saved.setter
    def on_config_saved(self, cb):
        self._win.on_config_saved = cb

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        import time
        while not self._win._ready:
            time.sleep(0.1)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")

    def set_audio_level(self, level: float):
        self._win.set_audio_level(level)

    def stream_nexo_chunk(self, chunk: str):
        self._win._chunk_sig.emit(chunk)

    def clear_nexo_response(self):
        self._win._chunk_sig.emit("__clear__")

    # ── Widget commands ──────────────────────────────────
    def update_weather(self, city: str, temp: str, desc: str, icon: str = "🌤"):
        self._win._log_sig.emit(f"__weather__:{city}|{temp}|{desc}|{icon}")

    def add_todo(self, task: str):
        self._win._log_sig.emit(f"__todo__:{task}")

    def update_spotify(self, song: str, artist: str = "", album: str = "",
                       duration_ms: int = 0, progress_ms: int = 0,
                       is_playing: bool = True):
        payload = f"{song}|{artist}|{album}|{duration_ms}|{progress_ms}|{'true' if is_playing else 'false'}"
        self._win._log_sig.emit(f"__spotify__:{payload}")

    def show_system(self):
        self._win._log_sig.emit("__system__")

    def show_notes(self):
        self._win._log_sig.emit("__notes__")

    def hide_all_widgets(self):
        self._win._log_sig.emit("__hide__")

    def set_orb_mini(self, mini: bool):
        self._win._log_sig.emit(f"__orb_mini__:{'true' if mini else 'false'}")

    def show_map(self, route_data: dict):
        """Show route data in the dashboard map widget."""
        import json
        self._win._log_sig.emit(f"__maps__:{json.dumps(route_data)}")

    def show_image(self, file_paths: list[str]):
        """Show one or more generated images in the image widget."""
        payload = "|".join(file_paths)
        self._win._log_sig.emit(f"__image__:{payload}")