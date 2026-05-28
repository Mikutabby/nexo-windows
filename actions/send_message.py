"""
send_message.py — Envío de mensajes para NEXO.

WhatsApp  → WhatsApp Web vía Playwright (browser_control) — más confiable,
            soporta múltiples perfiles de Chrome, no requiere app de escritorio.
Telegram  → App de escritorio vía pyautogui (búsqueda Ctrl+F).
Discord   → App de escritorio vía pyautogui.
Signal    → App de escritorio vía pyautogui.
Instagram → Web vía webbrowser + pyautogui.
Messenger → Web vía webbrowser + pyautogui.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.06
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_os() -> str:
    try:
        cfg = json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
        return cfg.get("os_system", "windows").lower()
    except Exception:
        return "windows"


def _log(player, msg: str) -> None:
    print(f"[SendMessage] {msg}")
    if player:
        player.write_log(f"[msg] {msg}")


# ─────────────────────── pyautogui helpers ──────────────────────────────────

def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI no está instalado. Ejecutá: pip install pyautogui")


def _paste_text(text: str) -> None:
    _require_pyautogui()
    paste_hotkey = ("command", "v") if _get_os() == "mac" else ("ctrl", "v")
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey(*paste_hotkey)
        time.sleep(0.1)
    else:
        pyautogui.write(text, interval=0.03)


def _clear_and_paste(text: str) -> None:
    _require_pyautogui()
    select_all = ("command", "a") if _get_os() == "mac" else ("ctrl", "a")
    pyautogui.hotkey(*select_all)
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.1)
    _paste_text(text)


def _open_app(app_name: str) -> bool:
    _require_pyautogui()
    os_name = _get_os()
    try:
        if os_name == "windows":
            pyautogui.press("win")
            time.sleep(0.5)
            _paste_text(app_name)
            time.sleep(0.6)
            pyautogui.press("enter")
            time.sleep(2.5)
            return True
        elif os_name == "mac":
            result = subprocess.run(["open", "-a", app_name],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                result = subprocess.run(["open", "-a", f"{app_name}.app"],
                                        capture_output=True, text=True, timeout=10)
            time.sleep(2.5)
            return result.returncode == 0
        else:
            for launcher in [["gtk-launch", app_name.lower()], [app_name.lower()]]:
                try:
                    subprocess.Popen(launcher,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    time.sleep(2.5)
                    return True
                except FileNotFoundError:
                    continue
            return False
    except Exception as e:
        print(f"[SendMessage] ⚠️ No se pudo abrir {app_name}: {e}")
        return False


def _search_in_app(query: str) -> None:
    _require_pyautogui()
    search_hotkey = ("command", "f") if _get_os() == "mac" else ("ctrl", "f")
    pyautogui.hotkey(*search_hotkey)
    time.sleep(0.5)
    _clear_and_paste(query)
    time.sleep(1.0)


def _desktop_send(app_name: str, receiver: str, message: str, player=None) -> str:
    _log(player, f"Abriendo {app_name}...")
    if not _open_app(app_name):
        return f"No se pudo abrir {app_name}."

    _log(player, f"Buscando contacto: {receiver}...")
    time.sleep(1.0)
    _search_in_app(receiver)
    pyautogui.press("enter")
    time.sleep(0.8)

    _log(player, "Enviando mensaje...")
    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.5)

    result = f"✅ Mensaje enviado a {receiver} por {app_name}."
    _log(player, result)
    return result


# ─────────────────────── WhatsApp Web (Playwright) ──────────────────────────

_WA_SEARCH_SELECTORS = [
    '[data-testid="chat-list-search"]',
    '[title="Search input textbox"]',
    'div[contenteditable="true"][data-tab="3"]',
    '[aria-label*="Search"]',
    '[placeholder*="Search"]',
]

_WA_COMPOSE_SELECTORS = [
    '[data-testid="conversation-compose-box-input"]',
    'div[contenteditable="true"][data-tab="10"]',
    'footer div[contenteditable="true"]',
    '[title*="message"]',
    '[aria-label*="message"]',
]

_WA_CONTACT_SELECTORS = [
    '[data-testid="cell-frame-container"]',
    '[data-testid="list-item-0"]',
    'div[role="listitem"]',
]


def _bc(params: dict, player=None) -> str:
    """Wrapper: fuerza Chrome Playwright (NEXO profile) para todas las acciones de WhatsApp."""
    from actions.browser_control import browser_control
    params = {**params, "browser": "chrome", "_force_playwright": True}
    return browser_control(params, player=None) or ""


def _wa_try_click(page_func, selectors: list[str]) -> tuple[bool, str]:
    """Intenta hacer click en el primer selector que funcione."""
    for sel in selectors:
        r = page_func(sel)
        if r and "not found" not in r.lower() and "error" not in r.lower() and "timeout" not in r.lower():
            return True, sel
    return False, ""


def _send_whatsapp(receiver: str, message: str, player=None) -> str:
    """Envía un mensaje de WhatsApp usando el módulo dedicado whatsapp.py."""
    from actions.whatsapp import whatsapp as wa_action
    return wa_action(
        parameters={"action": "send", "receiver": receiver, "message": message},
        player=player,
    )

def _send_whatsapp_legacy(receiver: str, message: str, player=None) -> str:
    """Legado — ya no se usa directamente."""
    _log(player, "Abriendo WhatsApp Web...")
    nav = _bc({"action": "go_to", "url": "https://web.whatsapp.com"})
    print(f"[SendMessage] Nav result: {nav}")

    # Esperar a que cargue WhatsApp Web (hasta 25s)
    _log(player, "Esperando que cargue WhatsApp Web...")
    deadline = time.time() + 25
    loaded = False
    while time.time() < deadline:
        time.sleep(2.5)
        text = _bc({"action": "get_text"}) or ""
        low  = text.lower()
        if any(kw in low for kw in ("chats", "search", "buscar", "new chat",
                                    "nuevo chat", "archivados", "archived")):
            loaded = True
            _log(player, "✅ WhatsApp Web cargado.")
            break
        remaining = int(deadline - time.time())
        _log(player, f"Cargando... ({remaining}s restantes)")

    if not loaded:
        page_text = _bc({"action": "get_text"}) or ""
        if "qr" in page_text.lower() or "scan" in page_text.lower() or len(page_text) < 100:
            return ("⚠️ WhatsApp Web necesita autenticación. "
                    "Por favor abrí Chrome y escaneá el código QR en web.whatsapp.com")
        return "⚠️ WhatsApp Web no respondió a tiempo. Intentá de nuevo."

    # ── Buscar contacto ──────────────────────────────────────────────────────
    _log(player, f"Buscando contacto: {receiver}...")

    # Click en la barra de búsqueda
    ok, _ = _wa_try_click(
        lambda sel: _bc({"action": "click", "selector": sel}),
        _WA_SEARCH_SELECTORS,
    )
    if not ok:
        _bc({"action": "smart_click", "description": "Search or start new chat"})
    time.sleep(0.5)

    # Limpiar y escribir el nombre del contacto
    _bc({"action": "press", "key": "Control+a"})
    time.sleep(0.1)
    wrote = False
    for sel in _WA_SEARCH_SELECTORS:
        r = _bc({"action": "type", "selector": sel, "text": receiver, "clear_first": True})
        if r and "error" not in r.lower() and "timeout" not in r.lower():
            wrote = True
            break
    if not wrote:
        _bc({"action": "smart_type", "description": "Search", "text": receiver})

    _log(player, "Esperando resultados de búsqueda...")
    time.sleep(2.5)

    # Verificar que aparecieron resultados
    page_text = _bc({"action": "get_text"}) or ""
    # Buscar nombre exacto o parcial en resultados
    receiver_words = receiver.lower().split()
    found_in_page  = any(w in page_text.lower() for w in receiver_words if len(w) > 2)
    if not found_in_page and len(page_text) < 300:
        return (f"⚠️ No se encontró el contacto '{receiver}' en WhatsApp. "
                f"Verificá que el nombre coincida exactamente con el guardado en la app.")

    # Hacer click en el contacto correcto filtrando por nombre
    _log(player, f"Seleccionando contacto: {receiver}...")
    # Intentar click por texto del contacto primero
    r = _bc({"action": "click", "text": receiver})
    if "not found" in r.lower() or "error" in r.lower() or "timeout" in r.lower():
        # Fallback: primer resultado en la lista
        ok, _ = _wa_try_click(
            lambda sel: _bc({"action": "click", "selector": sel}),
            _WA_CONTACT_SELECTORS,
        )
        if not ok:
            _bc({"action": "press", "key": "Enter"})
    time.sleep(1.2)

    # Hacer click en el campo de escritura de mensaje
    _log(player, "Escribiendo mensaje...")
    ok, _ = _wa_try_click(
        lambda sel: _bc({"action": "click", "selector": sel}),
        _WA_COMPOSE_SELECTORS,
    )
    if not ok:
        _bc({"action": "smart_click", "description": "Type a message"})
    time.sleep(0.3)

    # Escribir el mensaje
    wrote = False
    for sel in _WA_COMPOSE_SELECTORS:
        r = _bc({"action": "type", "selector": sel, "text": message, "clear_first": False})
        if r and "error" not in r.lower():
            wrote = True
            break
    if not wrote:
        _bc({"action": "smart_type", "description": "message", "text": message})

    time.sleep(0.4)
    _bc({"action": "press", "key": "Enter"})
    time.sleep(1.0)

    # Verificar que el mensaje fue enviado (buscar en el texto de la página)
    page_text = _bc({"action": "get_text"}) or ""
    msg_snippet = message[:30].lower()
    if msg_snippet in page_text.lower():
        result = f"✅ Mensaje enviado a {receiver} por WhatsApp."
    else:
        result = f"✅ Mensaje enviado a {receiver} por WhatsApp (no se pudo verificar en pantalla)."

    _log(player, result)
    return result


# ─────────────────────── plataformas desktop ────────────────────────────────

def _send_telegram(receiver: str, message: str, player=None) -> str:
    return _desktop_send("Telegram", receiver, message, player)


def _send_signal(receiver: str, message: str, player=None) -> str:
    return _desktop_send("Signal", receiver, message, player)


def _send_discord(receiver: str, message: str, player=None) -> str:
    return _desktop_send("Discord", receiver, message, player)


def _send_instagram(receiver: str, message: str, player=None) -> str:
    _require_pyautogui()
    _log(player, "Abriendo Instagram DMs...")
    import webbrowser
    webbrowser.open("https://www.instagram.com/direct/new/")
    time.sleep(4.0)

    _paste_text(receiver)
    time.sleep(1.5)
    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(0.4)
    for _ in range(4):
        pyautogui.press("tab")
        time.sleep(0.15)
    pyautogui.press("enter")
    time.sleep(2.0)

    _log(player, f"Enviando mensaje a {receiver}...")
    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.5)

    result = f"✅ Mensaje enviado a {receiver} por Instagram."
    _log(player, result)
    return result


def _send_messenger(receiver: str, message: str, player=None) -> str:
    _require_pyautogui()
    _log(player, "Abriendo Messenger...")
    import webbrowser
    webbrowser.open("https://www.messenger.com/")
    time.sleep(4.0)

    os_name = _get_os()
    pyautogui.hotkey("command" if os_name == "mac" else "ctrl", "f")
    time.sleep(0.5)
    _clear_and_paste(receiver)
    time.sleep(0.5)
    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1.0)

    _log(player, f"Enviando mensaje a {receiver}...")
    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.5)

    result = f"✅ Mensaje enviado a {receiver} por Messenger."
    _log(player, result)
    return result


# ─────────────────────── router ─────────────────────────────────────────────

_PLATFORM_MAP = [
    ({"whatsapp", "wp", "wapp"},          _send_whatsapp),
    ({"telegram", "tg"},                  _send_telegram),
    ({"instagram", "ig", "insta"},        _send_instagram),
    ({"signal"},                          _send_signal),
    ({"discord"},                         _send_discord),
    ({"messenger", "facebook", "fb"},     _send_messenger),
]


def _resolve_platform(platform_str: str):
    key = platform_str.lower().strip()
    for keywords, handler in _PLATFORM_MAP:
        if any(k in key for k in keywords):
            return handler
    return lambda r, m, p=None: _desktop_send(platform_str.strip().title(), r, m, p)


def send_message(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params       = parameters or {}
    receiver     = params.get("receiver", "").strip()
    message_text = params.get("message_text", "").strip()
    platform     = params.get("platform", "whatsapp").strip()

    if not receiver:
        return "Por favor especificá el destinatario."
    if not message_text:
        return "Por favor especificá el contenido del mensaje."

    preview = message_text[:60] + ("…" if len(message_text) > 60 else "")
    _log(player, f"📨 {platform} → {receiver}: {preview}")

    try:
        handler = _resolve_platform(platform)
        result  = handler(receiver, message_text, player)
    except Exception as e:
        result = f"❌ No se pudo enviar el mensaje: {e}"
        _log(player, result)

    return result
