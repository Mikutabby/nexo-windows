"""
_chrome_launch.py — Abre URLs en Google Chrome con el perfil correcto del usuario.
Usado por google_maps, google_drive, gmail, etc.
"""
from __future__ import annotations
import json
import subprocess
import webbrowser
from pathlib import Path


def _load_cfg() -> dict:
    try:
        p = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return {}


def open_in_chrome(url: str) -> bool:
    """
    Abre `url` en Chrome con el perfil configurado de Google.
    Retorna True si pudo abrirlo en Chrome, False si usó fallback.
    """
    cfg      = _load_cfg()
    exe      = cfg.get("chrome_exe_path", "")
    profile  = cfg.get("chrome_google_profile", "Default")

    # Candidatos si no está en config
    if not exe or not Path(exe).exists():
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for c in candidates:
            if Path(c).exists():
                exe = c
                break

    if exe and Path(exe).exists():
        try:
            import os
            user_data = str(
                Path(os.environ.get("LOCALAPPDATA", ""))
                / "Google" / "Chrome" / "User Data"
            )
            subprocess.Popen([
                exe,
                f"--profile-directory={profile}",
                f"--user-data-dir={user_data}",
                url,
            ])
            return True
        except Exception as e:
            print(f"[Chrome] ⚠️ Error lanzando Chrome: {e}")

    webbrowser.open(url)
    return False
