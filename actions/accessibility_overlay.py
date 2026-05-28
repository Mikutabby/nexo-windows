"""
accessibility_overlay.py — Barra flotante de accesibilidad para NEXO.
Lanzada como subproceso independiente (OS-level), siempre visible sobre todo.
Botones: Narrar Pantalla, Clic por Voz, Dwell Click, Alto Contraste, Ayuda.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

# ── Subprocess launcher ───────────────────────────────────────────────────────

_BASE = Path(__file__).resolve().parent.parent
_OVERLAY_SCRIPT = Path(__file__).resolve().parent / "_accessibility_overlay_proc.py"
_overlay_proc: subprocess.Popen | None = None
_CREATE_NO_WINDOW = 0x08000000


def _launch_overlay():
    global _overlay_proc
    if _overlay_proc and _overlay_proc.poll() is None:
        return  # already running
    _write_overlay_script()
    py = _find_python()
    _overlay_proc = subprocess.Popen(
        [py, str(_OVERLAY_SCRIPT)],
        creationflags=_CREATE_NO_WINDOW,
    )


def _stop_overlay():
    global _overlay_proc
    if _overlay_proc:
        try:
            _overlay_proc.terminate()
        except Exception:
            pass
        _overlay_proc = None


def _find_python() -> str:
    import shutil
    for candidate in ["pythonw.exe", "python.exe", sys.executable]:
        p = shutil.which(candidate)
        if p:
            return p
    return sys.executable


def _write_overlay_script():
    """Write the standalone overlay script to disk so it can be run as subprocess."""
    script_content = r'''"""Standalone floating accessibility toolbar — NEXO aesthetic."""
import sys, os, time, json, threading, subprocess, ctypes
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont

BASE = Path(__file__).resolve().parent.parent
CFG  = BASE / "config" / "api_keys.json"

# ── Colors (NEXO palette) ────────────────────────────────────────────────────
BG       = "#040d15"
BORDER   = "#00d4ff"
TEXT     = "#e0f7ff"
BTN_BG   = "#071826"
BTN_ACT  = "#00d4ff"
BTN_HOV  = "#0a2535"
DIM      = "#1a3545"

# ── State ─────────────────────────────────────────────────────────────────────
_dwell_active    = False
_monitor_active  = False
_contrast_active = False

# ── TTS ───────────────────────────────────────────────────────────────────────
def _speak(text: str):
    try:
        script = (
            f"Add-Type -AssemblyName System.Speech; "
            f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Rate = 1; "
            f"$s.Speak('{text.replace(chr(39), '')}');"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            creationflags=0x08000000,
        )
    except Exception:
        pass


# ── Overlay window ────────────────────────────────────────────────────────────
root = tk.Tk()
root.title("NEXO Accessibility")
root.overrideredirect(True)
root.attributes("-topmost", True)
root.attributes("-alpha", 0.93)
root.configure(bg=BG)

# Position: bottom-right corner
SW = root.winfo_screenwidth()
SH = root.winfo_screenheight()
W, H = 310, 42
X = SW - W - 12
Y = SH - H - 56   # above taskbar
root.geometry(f"{W}x{H}+{X}+{Y}")

# Click-through disabled (toolbar needs mouse interaction)
# Make it draggable
_drag_x = _drag_y = 0

def _on_drag_start(e):
    global _drag_x, _drag_y
    _drag_x, _drag_y = e.x, e.y

def _on_drag_move(e):
    dx = e.x - _drag_x
    dy = e.y - _drag_y
    nx = root.winfo_x() + dx
    ny = root.winfo_y() + dy
    root.geometry(f"+{nx}+{ny}")

# ── Call screen_reader actions ────────────────────────────────────────────────
def _call_screen_reader(action: str, **kwargs):
    params = {"action": action, **kwargs}
    py = sys.executable
    cmd = [py, "-c", (
        f"import sys; sys.path.insert(0,r'{BASE}');"
        f"from actions.screen_reader import screen_reader;"
        f"r=screen_reader({repr(params)}, None, None, None);"
        f"print(r)"
    )]
    try:
        subprocess.Popen(cmd, creationflags=0x08000000)
    except Exception as e:
        print(f"[overlay] {e}")


def _btn_narrar():
    _speak("Narrando pantalla")
    _call_screen_reader("describe")

def _btn_dwell():
    global _dwell_active
    _dwell_active = not _dwell_active
    if _dwell_active:
        btn_dwell.configure(bg=BTN_ACT, fg=BG)
        _speak("Dwell click activado. Mantene el cursor quieto 2 segundos para hacer clic.")
        _call_screen_reader("dwell_start")
    else:
        btn_dwell.configure(bg=BTN_BG, fg=TEXT)
        _speak("Dwell click desactivado.")
        _call_screen_reader("dwell_stop")

def _btn_monitor():
    global _monitor_active
    _monitor_active = not _monitor_active
    if _monitor_active:
        btn_monitor.configure(bg=BTN_ACT, fg=BG)
        _speak("Monitoreo de pantalla activado.")
        _call_screen_reader("monitor_start")
    else:
        btn_monitor.configure(bg=BTN_BG, fg=TEXT)
        _speak("Monitoreo de pantalla desactivado.")
        _call_screen_reader("monitor_stop")

def _btn_contrast():
    global _contrast_active
    _contrast_active = not _contrast_active
    if _contrast_active:
        btn_contrast.configure(bg=BTN_ACT, fg=BG)
        _speak("Alto contraste activado.")
        subprocess.Popen(["powershell","-c","Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' -Name HighContrast -Value 1"],creationflags=0x08000000)
    else:
        btn_contrast.configure(bg=BTN_BG, fg=TEXT)
        _speak("Alto contraste desactivado.")
        subprocess.Popen(["powershell","-c","Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' -Name HighContrast -Value 0"],creationflags=0x08000000)

def _btn_help():
    _speak(
        "Barra de accesibilidad NEXO. "
        "Narrar: describe lo que hay en la pantalla. "
        "Dwell: activa el clic automático al mantener el cursor quieto dos segundos. "
        "Monitor: anuncia cuando cambia la ventana activa. "
        "Contraste: activa el modo de alto contraste. "
        "Podés cerrar esta barra diciendo: cerrar barra de accesibilidad."
    )

def _btn_close():
    _speak("Cerrando barra de accesibilidad.")
    root.after(800, root.destroy)


# ── Layout ────────────────────────────────────────────────────────────────────
f = tkfont.Font(family="Segoe UI", size=8, weight="bold")

outer = tk.Frame(root, bg=BORDER, bd=0)
outer.pack(fill="both", expand=True, padx=1, pady=1)

inner = tk.Frame(outer, bg=BG, bd=0)
inner.pack(fill="both", expand=True, padx=1, pady=1)

def _make_btn(parent, text, cmd, width=48):
    b = tk.Button(
        parent, text=text, command=cmd,
        bg=BTN_BG, fg=TEXT, activebackground=BTN_HOV, activeforeground=BORDER,
        font=f, relief="flat", bd=0, padx=4, pady=3, cursor="hand2",
        width=width // 8,
    )
    b.bind("<Enter>", lambda e: b.configure(bg=BTN_HOV))
    b.bind("<Leave>", lambda e: b.configure(
        bg=(BTN_ACT if b.cget("fg") == BG else BTN_BG)
    ))
    return b


row = tk.Frame(inner, bg=BG)
row.pack(fill="both", expand=True, padx=4, pady=3)

# Drag handle
drag_lbl = tk.Label(row, text="⣿", bg=BG, fg=DIM, font=tkfont.Font(size=10), cursor="fleur")
drag_lbl.pack(side="left", padx=(0,4))
drag_lbl.bind("<ButtonPress-1>", _on_drag_start)
drag_lbl.bind("<B1-Motion>", _on_drag_move)
inner.bind("<ButtonPress-1>", _on_drag_start)
inner.bind("<B1-Motion>", _on_drag_move)

btn_narrar   = _make_btn(row, "👁 Narrar",   _btn_narrar,  56)
btn_dwell    = _make_btn(row, "🖱 Dwell",    _btn_dwell,   48)
btn_monitor  = _make_btn(row, "📡 Monitor",  _btn_monitor, 56)
btn_contrast = _make_btn(row, "◐ Contraste", _btn_contrast,64)
btn_help     = _make_btn(row, "? Ayuda",     _btn_help,    48)
btn_close    = _make_btn(row, "✕",           _btn_close,   20)
btn_close.configure(fg="#ff4444", activeforeground="#ff8888")

for b in [btn_narrar, btn_dwell, btn_monitor, btn_contrast, btn_help]:
    b.pack(side="left", padx=2)
btn_close.pack(side="right", padx=(4, 0))

# ── Separator glow effect (redraw border) ─────────────────────────────────────
_glow_phase = 0.0
def _animate_border():
    global _glow_phase
    _glow_phase = (_glow_phase + 0.05) % (2 * 3.14159)
    import math
    alpha = 0.7 + 0.3 * math.sin(_glow_phase)
    val   = int(alpha * 255)
    r, g, b_ = 0, int(min(255, val * 0.83)), int(min(255, val))
    color = f"#{r:02x}{g:02x}{b_:02x}"
    outer.configure(bg=color)
    root.after(60, _animate_border)

_animate_border()
_speak("Barra de accesibilidad NEXO activada.")

root.mainloop()
'''
    _OVERLAY_SCRIPT.write_text(script_content, encoding="utf-8")


# ── Public action handler ─────────────────────────────────────────────────────

def accessibility_overlay(parameters: dict, response=None, player=None, session_memory=None) -> str:
    action = (parameters or {}).get("action", "show").lower().strip()

    running = bool(_overlay_proc and _overlay_proc.poll() is None)

    if action in ("show", "open", "start", "activar", "mostrar"):
        if running:
            return "✅ La barra de accesibilidad ya está activa."
        _launch_overlay()
        return "✅ Barra de accesibilidad activada — aparece en la esquina inferior derecha."

    elif action in ("hide", "close", "stop", "cerrar", "ocultar", "desactivar"):
        if not running:
            return "⚪ La barra de accesibilidad ya estaba cerrada."
        _stop_overlay()
        return "🔲 Barra de accesibilidad cerrada."

    elif action in ("toggle", "alternar"):
        if running:
            _stop_overlay()
            return "🔲 Barra de accesibilidad cerrada."
        else:
            _launch_overlay()
            return "✅ Barra de accesibilidad activada."

    elif action == "status":
        if running:
            return "✅ Barra de accesibilidad activa (esquina inferior derecha)."
        return "⚪ Barra de accesibilidad inactiva. Decí 'activar barra de accesibilidad' para mostrarla."

    return f"Acción desconocida: '{action}'. Opciones: show, hide, toggle, status."
