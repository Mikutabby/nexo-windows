"""sounds.py — NEXO ambient sound player.

Reproduce 'sonido_nexo.mp3' en loop continuo mientras NEXO piensa,
y se detiene en cuanto NEXO empieza a hablar.

Sin dependencias externas:
  Windows  → MCI (winmm.dll, built-in en todas las versiones de Windows)
  macOS    → afplay (nativo)
  Linux    → mpg123 / ffplay / vlc
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading

_lock:          threading.Lock                  = threading.Lock()
_active_stop:   threading.Event | None          = None
_active_thread: threading.Thread | None         = None

_MP3_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "sonido_nexo.MP3")


# ── Windows: MCI via ctypes ───────────────────────────────────────────────────

def _play_loop_windows_mci(stop: threading.Event) -> bool:
    """
    Loop de reproducción usando Windows MCI (winmm.dll).
    Detecta el fin del archivo consultando su estado real ('mode: stopped')
    en lugar de medir tiempo — así el loop es 100% confiable.
    """
    try:
        import ctypes
        winmm    = ctypes.windll.winmm          # type: ignore[attr-defined]
        abs_path = os.path.abspath(_MP3_PATH)
        alias    = "nexo_ambient"

        # Abrir el archivo
        if winmm.mciSendStringW(
            f'open "{abs_path}" type mpegvideo alias {alias}', None, 0, None
        ) != 0:
            return False

        buf = ctypes.create_unicode_buffer(64)

        def mci(cmd: str) -> str:
            winmm.mciSendStringW(cmd, buf, 64, None)
            return buf.value.strip().lower()

        try:
            # Primera reproducción
            winmm.mciSendStringW(f"play {alias}", None, 0, None)

            while not stop.is_set():
                stop.wait(timeout=0.2)          # chequear cada 200 ms

                if stop.is_set():
                    break

                # Si el archivo terminó, reiniciar desde el principio
                if mci(f"status {alias} mode") == "stopped":
                    winmm.mciSendStringW(f"seek {alias} to start", None, 0, None)
                    winmm.mciSendStringW(f"play {alias}", None, 0, None)

        finally:
            # Detener y liberar recursos siempre, pase lo que pase
            winmm.mciSendStringW(f"stop {alias}",  None, 0, None)
            winmm.mciSendStringW(f"close {alias}", None, 0, None)

        return True

    except Exception:
        return False


# ── macOS / Linux: subprocess ─────────────────────────────────────────────────

def _subprocess_players() -> list[list[str]]:
    p = _MP3_PATH
    if sys.platform == "darwin":
        return [
            ["afplay", p],
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", p],
            ["mpg123", "--quiet", p],
        ]
    else:
        return [
            ["mpg123", "--quiet", p],
            ["mpg321", "-q", p],
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", p],
            ["vlc", "--intf", "dummy", "--play-and-exit", p],
            ["mplayer", "-really-quiet", p],
        ]


def _play_loop_subprocess(stop: threading.Event) -> bool:
    while not stop.is_set():
        success = False
        for cmd in _subprocess_players():
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                # Esperar a que termine el archivo o se pida detener
                while proc.poll() is None:
                    if stop.is_set():
                        proc.terminate()
                        try:
                            proc.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        return True
                    stop.wait(timeout=0.2)
                success = True
                break
            except FileNotFoundError:
                continue
            except Exception as e:
                print(f"[NEXO Sound] Error ({cmd[0]}): {e}")
                continue

        if not success:
            return False

    return True


# ── Dispatcher principal ──────────────────────────────────────────────────────

def _play_loop(stop: threading.Event) -> None:
    if not os.path.isfile(_MP3_PATH):
        print(
            f"[NEXO Sound] Archivo no encontrado: {_MP3_PATH}\n"
            f"  → Ponelo como 'sonido_nexo.mp3' en la misma carpeta que sounds.py"
        )
        return

    if sys.platform == "win32":
        if _play_loop_windows_mci(stop):
            return
        print("[NEXO Sound] MCI falló, probando players externos...")

    if not _play_loop_subprocess(stop):
        msg = {
            "win32":  "  → winget install mpg123   (o)   winget install ffmpeg",
            "darwin": "  → afplay debería estar disponible. Probá: which afplay",
        }.get(sys.platform, "  → sudo apt install mpg123")
        print(f"[NEXO Sound] No se encontró player de MP3.\n{msg}")


# ── Public API ────────────────────────────────────────────────────────────────

def start_thinking_sound() -> None:
    """Inicia el loop de sonido en segundo plano (no bloquea)."""
    global _active_stop, _active_thread
    with _lock:
        if _active_thread and _active_thread.is_alive():
            return
        stop = threading.Event()
        t    = threading.Thread(target=_play_loop, args=(stop,), daemon=True)
        _active_stop   = stop
        _active_thread = t
        t.start()


def stop_thinking_sound() -> None:
    """Detiene el sonido inmediatamente (llamar cuando NEXO empieza a hablar)."""
    global _active_stop, _active_thread
    with _lock:
        if _active_stop:
            _active_stop.set()
        _active_stop   = None
        _active_thread = None