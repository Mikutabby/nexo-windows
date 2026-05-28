import asyncio
from beta_config import is_pro_tool, check_daily_limit, increment_calls, pro_tool_message, daily_limit_message
# Nexo 3.0 — Emotional Intelligence
from emotion_detector import analyze_emotion, get_emotional_context
# _actions_wrapped_beta
import os
import random
import re
import threading
import time
import json
import sys
import traceback
from pathlib import Path

try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    try:
        _BA_TZ = _ZoneInfo("America/Argentina/Buenos_Aires")
    except Exception:
        # zoneinfo has no IANA database — install tzdata package
        try:
            import importlib
            importlib.import_module("tzdata")
            _BA_TZ = _ZoneInfo("America/Argentina/Buenos_Aires")
        except Exception:
            from datetime import timezone as _tz, timedelta as _td
            _BA_TZ = _tz(_td(hours=-3))
except ImportError:
    from datetime import timezone as _tz, timedelta as _td
    _BA_TZ = _tz(_td(hours=-3))


def _load_tz():
    """Load timezone from api_keys.json config."""
    global _BA_TZ
    try:
        cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        tz_name = cfg.get("timezone", "")
        if tz_name:
            try:
                _BA_TZ = _ZoneInfo(tz_name)
                print(f"[TZ] Timezone loaded: {tz_name}")
            except Exception as e:
                print(f"[TZ] Failed to load '{tz_name}': {e}")
                # Try installing/importing tzdata (Windows has no built-in IANA DB)
                _tz_ok = False
                try:
                    import importlib as _il
                    _il.import_module("tzdata")
                    _BA_TZ = _ZoneInfo(tz_name)
                    print(f"[TZ] Loaded '{tz_name}' via tzdata package")
                    _tz_ok = True
                except Exception:
                    pass
                if not _tz_ok:
                    # Fuzzy match against available zones
                    import zoneinfo as _zi
                    available = _zi.available_timezones()
                    tz_lower  = tz_name.lower()
                    matched = None
                    for known in available:
                        if known.lower() == tz_lower:
                            matched = known
                            break
                    if matched is None:
                        parts = tz_name.replace("\\", "/").split("/")
                        short = parts[-1].lower() if parts else ""
                        for known in available:
                            if known.lower().endswith("/" + short):
                                matched = known
                                break
                    if matched:
                        _BA_TZ = _ZoneInfo(matched)
                        print(f"[TZ] Matched '{tz_name}' → '{matched}'")
                    else:
                        from datetime import timezone as _tzf, timedelta as _tdf
                        _BA_TZ = _tzf(_tdf(hours=-3))
                        print(f"[TZ] Using UTC-3 fallback for '{tz_name}'")
    except Exception as e:
        print(f"[TZ] Error reading config: {e}")

try:
    import numpy as np
    import sounddevice as sd
    from google import genai
    from google.genai import types
    from ui import NexoUI
    from memory.memory_manager import (
        load_memory, update_memory, format_memory_for_prompt,
    )
except Exception as _critical_import_err:
    try:
        import ctypes as _ct
        _ct.windll.user32.MessageBoxW(
            0,
            f"NEXO no puede iniciarse.\n\n"
            f"Falta un paquete o hay un error de importación:\n{_critical_import_err}\n\n"
            "Solución: volvé a ejecutar el instalador para reinstalar dependencias.",
            "NEXO — Error de inicio",
            0x10 | 0x40000,
        )
    except Exception:
        pass
    sys.exit(1)

try:
    from actions.file_processor import file_processor
except Exception:
    file_processor = None
try:
    from actions.flight_finder     import flight_finder
except Exception:
    flight_finder = None
try:
    from actions.open_app          import open_app
except Exception:
    open_app = None
try:
    from actions.weather_report    import weather_action
except Exception:
    weather_action = None
try:
    from actions.send_message      import send_message
except Exception:
    send_message = None
try:
    from actions.reminder          import reminder
except Exception:
    reminder = None
try:
    from actions.computer_settings import computer_settings
except Exception:
    computer_settings = None
try:
    from actions.screen_processor  import screen_process
except Exception:
    screen_process = None
try:
    from actions.youtube_video     import youtube_video
except Exception:
    youtube_video = None
try:
    from actions.desktop           import desktop_control
except Exception:
    desktop_control = None
try:
    from actions.browser_control   import browser_control
except Exception:
    browser_control = None
try:
    from actions.file_controller   import file_controller
except Exception:
    file_controller = None
try:
    from actions.code_helper       import code_helper
except Exception:
    code_helper = None
try:
    from actions.dev_agent         import dev_agent
except Exception:
    dev_agent = None
try:
    from actions.web_search        import web_search as web_search_action
except Exception:
    web_search_action = None
try:
    from actions.computer_control  import computer_control
except Exception:
    computer_control = None
try:
    from actions.game_updater      import game_updater
except Exception:
    game_updater = None
try:
    from actions.google_calendar   import google_calendar
except Exception:
    google_calendar = None
try:
    from actions.spotify_control   import spotify_control
except Exception:
    spotify_control = None
try:
    from actions.rgb_control       import rgb_control
except Exception:
    rgb_control = None
try:
    from actions.scheduler         import scheduler, start_runner
except Exception:
    scheduler = None; start_runner = None
try:
    from actions.google_drive      import google_drive
except Exception:
    google_drive = None
try:
    from actions.gmail_control     import gmail_control
except Exception:
    gmail_control = None
try:
    from actions.google_maps       import google_maps
except Exception:
    google_maps = None
try:
    from actions.rules_engine      import rules_engine, start_rules_runner, check_phrase_triggers, _run_action as _rules_run_action
except Exception:
    rules_engine = None; start_rules_runner = None; check_phrase_triggers = None; _rules_run_action = None
try:
    from actions.social_media      import social_media
except Exception:
    social_media = None
try:
    from actions.whatsapp          import whatsapp
except Exception:
    whatsapp = None
try:
    from actions.user_profile      import user_profile, record_action
except Exception:
    user_profile = None; record_action = None
try:
    from actions.goals             import goals
except Exception:
    goals = None
try:
    from actions.git_control       import git_control
except Exception:
    git_control = None
try:
    from actions.codebase          import codebase
except Exception:
    codebase = None
try:
    from actions.knowledge_base    import knowledge_base
except Exception:
    knowledge_base = None
try:
    from actions.windows_settings  import windows_settings
except Exception:
    windows_settings = None
try:
    from actions.document_creator  import document_creator
except Exception:
    document_creator = None
try:
    from actions.image_generation  import image_generation
except Exception:
    image_generation = None
try:
    from actions.smart_home        import smart_home
except Exception:
    smart_home = None
try:
    from actions.system_monitor    import system_monitor
except Exception:
    system_monitor = None
try:
    from actions.tiktok_analyzer   import tiktok_analyzer
except Exception:
    tiktok_analyzer = None
try:
    from actions.arca_invoice      import arca_invoice
except Exception:
    arca_invoice = None
try:
    from actions.accessibility          import accessibility
except Exception:
    accessibility = None
try:
    from actions.screen_vision          import screen_vision
except Exception:
    screen_vision = None
try:
    from actions.screen_reader          import screen_reader
except Exception:
    screen_reader = None
try:
    from actions.accessibility_overlay  import accessibility_overlay
except Exception:
    accessibility_overlay = None
try:
    from actions.morning_brief     import morning_brief, already_briefed_today, mark_briefed
except Exception:
    morning_brief = None; already_briefed_today = None; mark_briefed = None
try:
    from actions.vision_guardian   import vision_guardian, start as _start_vision_guardian
except Exception:
    vision_guardian = None; _start_vision_guardian = None


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LOG_PATH        = BASE_DIR / "nexo.log"

# ── Redirect output to log file (pythonw.exe has no console) ─
try:
    import io as _io
    _log_fh = open(LOG_PATH, "w", encoding="utf-8", buffering=1)

    class _TeeStream:
        def __init__(self, *streams):
            self._streams = [s for s in streams if s is not None]
        def write(self, data):
            for s in self._streams:
                try: s.write(data)
                except Exception: pass
        def flush(self):
            for s in self._streams:
                try: s.flush()
                except Exception: pass
        @property
        def encoding(self): return "utf-8"
        def fileno(self): raise _io.UnsupportedOperation("fileno")

    sys.stdout = _TeeStream(sys.stdout, _log_fh)
    sys.stderr = _TeeStream(sys.stderr, _log_fh)
except Exception:
    pass

# ── Suppress console windows from all child subprocesses ─────────────────────
if sys.platform == "win32":
    try:
        import ctypes as _ctypes
        if _ctypes.windll.kernel32.GetConsoleWindow() == 0:
            import subprocess as _sp
            _CREATE_NO_WINDOW = 0x08000000
            _orig_Popen = _sp.Popen
            class _NoCmdPopen(_orig_Popen):
                def __init__(self, *args, **kwargs):
                    kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_NO_WINDOW
                    super().__init__(*args, **kwargs)
            _sp.Popen = _NoCmdPopen
            print("[NEXO] subprocess.Popen patched: CREATE_NO_WINDOW active")
    except Exception as _e:
        print(f"[NEXO] Could not patch subprocess: {_e}")

LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 256      # 16ms chunks — mic input (keep small for low latency)
PLAY_CHUNK_SIZE     = 480      # 20ms chunks — playback (smaller = lower latency)

def _get_api_key() -> str:
    try:
        return json.loads(API_CONFIG_PATH.read_text(encoding="utf-8")).get("gemini_api_key", "")
    except Exception as e:
        print(f"[NEXO] ⚠️ Error leyendo API key: {e}")
        return ""


NEXO_VOICES = {
    "Aoede":  ("Femenina", "Cálida y sofisticada — ideal para asistente IA"),
    "Kore":   ("Femenina", "Suave y precisa"),
    "Leda":   ("Femenina", "Natural y fluida"),
    "Zephyr": ("Femenina", "Dinámica y expresiva"),
    "Charon": ("Masculina", "Profunda y seria — voz original de NEXO"),
    "Puck":   ("Masculina", "Ágil y versátil"),
    "Fenrir": ("Masculina", "Grave y autoritaria"),
    "Orus":   ("Masculina", "Clásica y equilibrada"),
}

def _get_nexo_voice() -> str:
    try:
        cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        return cfg.get("nexo_voice", "Charon")
    except Exception:
        return "Charon"


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are NEXO, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "whatsapp",
        "description": (
            "Integración completa con WhatsApp. "
            "SIEMPRE usar para CUALQUIER pedido de WhatsApp: enviar mensajes, "
            "enviar imágenes/archivos, leer conversaciones, ver mensajes sin leer, "
            "guardar/listar contactos con su número de teléfono. "
            "Para enviar, primero verificar si el contacto está guardado con su teléfono. "
            "Si no está, pedir el número al usuario o usar add_contact primero."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "send | send_image | read | unread | add_contact | list_contacts | delete_contact"},
                "receiver":  {"type": "STRING",  "description": "Nombre del contacto o número de teléfono con código de país (ej: 5491155551234)"},
                "message":   {"type": "STRING",  "description": "Texto del mensaje a enviar"},
                "image_path":{"type": "STRING",  "description": "Ruta de la imagen para send_image"},
                "caption":   {"type": "STRING",  "description": "Descripción de la imagen (opcional)"},
                "count":     {"type": "INTEGER", "description": "Cantidad de mensajes a leer (default: 10)"},
                "name":      {"type": "STRING",  "description": "Nombre del contacto para add_contact/delete_contact"},
                "phone":     {"type": "STRING",  "description": "Número de teléfono con código de país (ej: 5491155551234) para add_contact"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via Telegram, Discord, Signal or other messaging platform. For WhatsApp, use the 'whatsapp' tool instead.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: Telegram, Discord, Signal, Messenger (NOT WhatsApp — use whatsapp tool)"}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page, "
            "virtual desktops (create/switch/close), clipboard (read/write), "
            "Windows toast notifications, emoji panel, action center. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform. Examples: volume_up | volume_down | volume_set | brightness_up | screenshot | lock_screen | mute | unmute | read_clipboard | write_clipboard | notify | new_virtual_desktop | next_virtual_desktop | emoji | action_center | type_text | press_key | scroll_up | scroll_down | minimize | maximize | fullscreen | close_app | dark_mode | restart | shutdown"},
                "description": {"type": "STRING", "description": "Natural language description of what to do (used for AI intent detection)"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, notification message, clipboard text, etc."},
                "title":       {"type": "STRING", "description": "Title for notifications (default: NEXO)"},
                "message":     {"type": "STRING", "description": "Message text for notifications"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": (
            "Manages files and folders: list, create, delete (to recycle bin), move, copy, rename, read, write, find, disk usage. "
            "Use action=find with name + path to locate files by name in any directory (desktop, downloads, etc.). "
            "After finding a file, pass the returned path to another tool to act on it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete (mueve a papelera) | move | copy | rename | read | write | edit | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
                "old_text":    {"type": "STRING",  "description": "Texto a reemplazar (para edit)"},
                "new_text":    {"type": "STRING",  "description": "Nuevo texto o contenido (para edit)"},
                "mode":        {"type": "STRING",  "description": "replace | append | prepend | overwrite (para edit)"},
                "confirm":     {"type": "BOOLEAN", "description": "true para confirmar eliminaciones"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": (
            "Controls the desktop: wallpaper, organize, clean, list, stats. "
            "When the user says to use a file from a directory (e.g. 'el archivo X del escritorio'), "
            "use search_name + search_path to auto-find the file before applying the action."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":        {"type": "STRING", "description": "Image path for wallpaper"},
                "url":         {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":        {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":        {"type": "STRING", "description": "Natural language desktop task"},
                "search_name": {"type": "STRING", "description": "Filename to search for in a directory (auto-finds full path)"},
                "search_path": {"type": "STRING", "description": "Directory to search: desktop, downloads, documents, pictures, home (default: desktop)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_nexo",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Nexo. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "google_calendar",
        "description": (
            "Manages the user's Google Calendar: create, list, edit, or delete events. "
            "Use for ANY request about calendar events, appointments, reminders with dates, "
            "scheduling meetings, or checking what's coming up. "
            "ALWAYS call this tool for calendar requests — never simulate. "
            "For 'list': shows upcoming events. "
            "For 'create': needs summary and start (end defaults to +1h). "
            "For 'edit'/'delete': needs event_id (get it from 'list' first)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",  "description": "list | create | edit | delete"},
                "summary":     {"type": "STRING",  "description": "Event title/name"},
                "start":       {"type": "STRING",  "description": "Start date/time: ISO, YYYY-MM-DD HH:MM, or DD/MM/YYYY HH:MM"},
                "end":         {"type": "STRING",  "description": "End date/time (optional — defaults to start + 1 hour)"},
                "description": {"type": "STRING",  "description": "Event notes or description"},
                "location":    {"type": "STRING",  "description": "Event location"},
                "event_id":    {"type": "STRING",  "description": "Event ID (first 8 chars from list) for edit/delete"},
                "days_ahead":  {"type": "INTEGER", "description": "Days to look ahead for list (default: 7)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "spotify_control",
        "description": (
            "Control total de Spotify: reproducir, pausar, siguiente, anterior, volumen, "
            "buscar canciones/artistas/álbumes/playlists, aleatorio, repetir, ver qué suena, "
            "guardar canciones, ver dispositivos. "
            "SIEMPRE llamar esta herramienta para CUALQUIER pedido relacionado con Spotify o música."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | pause | resume | next | previous | volume | shuffle | repeat | current | search | like | devices | playlist"},
                "query":  {"type": "STRING", "description": "Búsqueda para play/search: canción, artista, álbum o playlist"},
                "type":   {"type": "STRING", "description": "track | album | playlist | artist (default: track)"},
                "value":  {"type": "STRING", "description": "Valor para volume (0-100), shuffle (true/false), repeat (off/track/context)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "rgb_control",
        "description": (
            "Controla las luces RGB de periféricos y componentes de la PC (teclado, mouse, GPU, RAM, etc.). "
            "Requiere OpenRGB corriendo con servidor SDK activado. "
            "Usar para: cambiar color, apagar, brillo, efectos, arco iris."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING", "description": "set_color | off | brightness | effect | rainbow | list"},
                "color":      {"type": "STRING", "description": "Color: nombre (rojo, azul, verde, blanco…) o hex #RRGGBB"},
                "brightness": {"type": "INTEGER", "description": "Brillo 0-100 (default: 100)"},
                "device":     {"type": "STRING", "description": "Filtro por nombre de dispositivo (opcional, aplica a todos si se omite)"},
                "effect":     {"type": "STRING", "description": "Nombre del efecto para la acción effect"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "scheduler",
        "description": (
            "Crea, lista, elimina o ejecuta automatizaciones programadas (tareas recurrentes). "
            "Ejemplos: backup diario, notificaciones, scripts automáticos. "
            "Usar para CUALQUIER pedido de 'todos los días a las X', 'cada semana', 'automatizar'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":           {"type": "STRING",  "description": "list | create | delete | enable | disable | run_now"},
                "name":             {"type": "STRING",  "description": "Nombre descriptivo de la tarea"},
                "frequency":        {"type": "STRING",  "description": "daily | weekly | interval | once"},
                "hour":             {"type": "INTEGER", "description": "Hora de ejecución (0-23)"},
                "minute":           {"type": "INTEGER", "description": "Minuto de ejecución (0-59)"},
                "weekday":          {"type": "STRING",  "description": "Día de la semana para frequency=weekly"},
                "interval_minutes": {"type": "INTEGER", "description": "Intervalo en minutos para frequency=interval"},
                "task_action":      {"type": "STRING",  "description": "backup | file_controller | notify | custom_script | browser_control"},
                "task_parameters":  {"type": "OBJECT",  "description": "Parámetros de la tarea (source, destination para backup, etc.)"},
                "task_id":          {"type": "STRING",  "description": "ID de la tarea (primeros 6 chars) para delete/enable/disable/run_now"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "google_drive",
        "description": (
            "Gestiona Google Drive: listar archivos, buscar, subir, descargar, crear carpetas, eliminar, compartir. "
            "SIEMPRE usar para cualquier pedido sobre Google Drive."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | search | upload | download | create_folder | delete | share | info"},
                "folder_id":   {"type": "STRING", "description": "ID de la carpeta (default: root)"},
                "file_id":     {"type": "STRING", "description": "ID del archivo para download/delete/share/info"},
                "path":        {"type": "STRING", "description": "Ruta local para upload"},
                "name":        {"type": "STRING", "description": "Nombre de la nueva carpeta"},
                "query":       {"type": "STRING", "description": "Término de búsqueda"},
                "destination": {"type": "STRING", "description": "Carpeta local de destino para download"},
                "email":       {"type": "STRING", "description": "Email para compartir"},
                "role":        {"type": "STRING", "description": "reader | writer | commenter"},
                "confirm":     {"type": "BOOLEAN", "description": "true para confirmar eliminación"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "gmail_control",
        "description": (
            "Gestiona Gmail: leer bandeja, leer correo, enviar, responder, buscar, archivar, eliminar. "
            "SIEMPRE usar para cualquier pedido sobre correo electrónico o Gmail."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING",  "description": "inbox | read | send | reply | search | archive | delete | mark_read | labels"},
                "count":      {"type": "INTEGER", "description": "Cantidad de correos a listar/buscar (default: 5)"},
                "message_id": {"type": "STRING",  "description": "ID del mensaje para read/reply/archive/delete/mark_read"},
                "to":         {"type": "STRING",  "description": "Destinatario para send"},
                "subject":    {"type": "STRING",  "description": "Asunto para send"},
                "body":       {"type": "STRING",  "description": "Cuerpo del correo para send/reply"},
                "query":      {"type": "STRING",  "description": "Búsqueda Gmail para search (ej: 'from:juan', 'subject:factura')"},
                "confirm":    {"type": "BOOLEAN", "description": "true para confirmar eliminación"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "google_maps",
        "description": (
            "Navegación y mapas interactivos. SIEMPRE usar para CUALQUIER pedido de: "
            "cómo llegar a un lugar, rutas, cuánto tarda ir a algún lado, ver un lugar en el mapa, "
            "guardar una dirección, listar lugares guardados. "
            "Acepta lenguaje completamente natural: 'quiero ir al shopping de Devoto', "
            "'cómo llego al Obelisco', 'llevame a casa de mamá', etc. "
            "NO hace falta dirección exacta — el sistema resuelve el lugar por nombre. "
            "Si el usuario dice 'mi casa', 'el trabajo', 'la facu', etc., "
            "el sistema lo resuelve desde la memoria de NEXO automáticamente. "
            "Si el usuario pide guardar una dirección, usar action=save_place. "
            "IMPORTANTE: si el usuario no especifica origen, dejarlo vacío — "
            "Google Maps usará su ubicación actual."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "directions = calcular ruta (default) | "
                        "search = buscar/mostrar lugar en mapa | "
                        "save_place = guardar dirección en memoria | "
                        "list_places = listar lugares guardados"
                    )
                },
                "origin": {
                    "type": "STRING",
                    "description": (
                        "Punto de partida. Acepta nombre de lugar, dirección, o alias como "
                        "'mi casa', 'el trabajo'. Dejar VACÍO si el usuario no especifica origen."
                    )
                },
                "destination": {
                    "type": "STRING",
                    "description": (
                        "Destino. Acepta nombre de lugar, dirección exacta o descripción natural "
                        "como 'shopping de Devoto', 'el Obelisco', 'terminal de ómnibus', "
                        "'aeropuerto de Ezeiza', etc."
                    )
                },
                "mode": {
                    "type": "STRING",
                    "description": "car (auto, default) | walk (caminando) | bike (bicicleta) | transit (transporte público)"
                },
                "query": {
                    "type": "STRING",
                    "description": "Lugar a buscar en el mapa (para action=search). Acepta nombres naturales."
                },
                "name": {
                    "type": "STRING",
                    "description": "Para save_place: nombre con el que guardar el lugar (ej: 'mi gym', 'casa de mamá')"
                },
                "address": {
                    "type": "STRING",
                    "description": "Para save_place: dirección o descripción del lugar a guardar"
                },
                "save_as": {
                    "type": "STRING",
                    "description": "Nombre con el que guardar el destino en memoria (opcional, para directions)"
                },
            },
            "required": ["action"]
        }
    },
    {
        "name": "rules_engine",
        "description": (
            "Motor de automatizaciones y alertas inteligentes. "
            "USAR SIEMPRE cuando el usuario pida: 'cuando diga X hacé Y', 'cada vez que diga X', "
            "'si digo X abrí/poné/hacé Y', 'quiero que cuando diga X...'. "
            "Soporta: phrase triggers (frase → acción), time triggers (hora → acción), alertas. "
            "Listar, crear, eliminar, habilitar/deshabilitar automaciones. "
            "CONDITION types: phrase (frase del usuario), time (hora del día), file_exists, always. "
            "ACTION types: open_app, spotify_play, browser, smart_home, composite (múltiples), notify, speak, run_script."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING", "description": "list | list_phrases | create | delete | enable | disable | trigger | alert"},
                "name":       {"type": "STRING", "description": "Nombre de la automatización"},
                "rule_id":    {"type": "STRING", "description": "ID de la regla para delete/enable/disable/trigger"},
                "condition":  {
                    "type": "OBJECT",
                    "description": (
                        "Condición. phrase: {type:phrase, trigger:'texto exacto', match:contains|exact|startswith}. "
                        "time: {type:time, hour:8, minute:0, days:[monday,...]}. "
                        "file_exists: {type:file_exists, path:'...'}. always: {type:always}"
                    )
                },
                "action_def": {
                    "type": "OBJECT",
                    "description": (
                        "Acción a ejecutar. "
                        "open_app: {type:open_app, app_name:'Spotify'}. "
                        "spotify_play: {type:spotify_play, query:'Back in Black AC/DC'}. "
                        "browser: {type:browser, url:'https://...'}. "
                        "smart_home: {type:smart_home, device:'living', action:'on'}. "
                        "composite: {type:composite, actions:[{...},{...}]}. "
                        "notify: {type:notify, message:'...'}. speak: {type:speak, message:'...'}. "
                        "run_script: {type:run_script, command:'...'}."
                    )
                },
                "message":    {"type": "STRING", "description": "Mensaje para action=alert"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "user_profile",
        "description": (
            "Perfil dinámico del usuario — hábitos, preferencias, historial de uso. "
            "Ver perfil, configurar preferencias, ver hábitos aprendidos, guardar notas personales. "
            "NEXO aprende automáticamente los patrones del usuario."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "view | set_preference | set_name | add_note | notes | habits | reset"},
                "key":    {"type": "STRING", "description": "Clave de preferencia (ej: idioma, tema, ciudad)"},
                "value":  {"type": "STRING", "description": "Valor de la preferencia"},
                "name":   {"type": "STRING", "description": "Nombre del usuario"},
                "note":   {"type": "STRING", "description": "Nota personal a guardar"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "goals",
        "description": (
            "Sistema de objetivos persistentes a largo plazo. "
            "Crear metas, trackear progreso, marcar pasos completados. "
            "Usar para: metas personales, proyectos, hábitos, objetivos con deadline. "
            "SIEMPRE usar para pedidos de 'quiero lograr X', 'mi objetivo es', 'meta de'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",  "description": "list | create | update_progress | complete | complete_step | add_step | delete | detail"},
                "goal_id":     {"type": "STRING",  "description": "ID del objetivo para update/complete/delete/detail"},
                "title":       {"type": "STRING",  "description": "Título del objetivo"},
                "description": {"type": "STRING",  "description": "Descripción detallada"},
                "deadline":    {"type": "STRING",  "description": "Fecha límite ISO (YYYY-MM-DD)"},
                "progress":    {"type": "INTEGER", "description": "Progreso 0-100"},
                "steps":       {"type": "ARRAY",   "items": {"type": "STRING"}, "description": "Lista de pasos del objetivo"},
                "step":        {"type": "STRING",  "description": "Texto del nuevo paso (add_step)"},
                "step_index":  {"type": "INTEGER", "description": "Índice del paso a completar (0-based)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "git_control",
        "description": (
            "Integración completa con Git: status, log, diff, commit automático, "
            "branches, pull, push, stash, análisis de cambios. "
            "Usar para CUALQUIER pedido relacionado con Git o control de versiones."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",  "description": "status | log | diff | commit | add | branches | branch_create | checkout | pull | push | stash | analyze"},
                "repo_path":   {"type": "STRING",  "description": "Ruta al repositorio Git"},
                "message":     {"type": "STRING",  "description": "Mensaje del commit"},
                "branch_name": {"type": "STRING",  "description": "Nombre de la rama"},
                "remote":      {"type": "STRING",  "description": "Remote (default: origin)"},
                "n":           {"type": "INTEGER", "description": "Número de commits para log"},
                "file":        {"type": "STRING",  "description": "Archivo específico para diff"},
                "staged":      {"type": "BOOLEAN", "description": "Mostrar diff staged"},
                "add_all":     {"type": "BOOLEAN", "description": "Agregar todos los archivos antes del commit (default: true)"},
                "files":       {"type": "ARRAY",   "items": {"type": "STRING"}, "description": "Archivos para add"},
                "sub":         {"type": "STRING",  "description": "Subcomando para stash: push|pop|list"},
            },
            "required": ["action", "repo_path"]
        }
    },
    {
        "name": "codebase",
        "description": (
            "Indexación y búsqueda inteligente de proyectos de código. "
            "Indexar proyectos, buscar en archivos, encontrar símbolos (funciones/clases), "
            "generar documentación automática, búsqueda avanzada de código. "
            "Usar para: 'buscar en mi proyecto', 'dónde está la función X', 'generar docs', 'indexar mi código'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING", "description": "index | list | info | search | find_symbol | generate_docs | remove"},
                "path":      {"type": "STRING", "description": "Ruta del proyecto a indexar"},
                "name":      {"type": "STRING", "description": "Nombre del proyecto (default: nombre de carpeta)"},
                "project":   {"type": "STRING", "description": "Nombre del proyecto para info/search/find_symbol"},
                "query":     {"type": "STRING", "description": "Texto a buscar en el código"},
                "symbol":    {"type": "STRING", "description": "Nombre de función/clase a buscar"},
                "file_path": {"type": "STRING", "description": "Ruta del archivo para generate_docs"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "knowledge_base",
        "description": (
            "Segundo cerebro / base de conocimiento personal. "
            "Guardar notas, ideas, snippets de código, referencias, hechos, preguntas. "
            "Buscar en el conocimiento guardado, exportar. "
            "Usar para: 'recordá que...', 'guardá esta idea', 'anotá este código', 'buscar en mis notas'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING", "description": "add/save/store | search/find | list | get/read/view | update | delete | stats | export"},
                "title":    {"type": "STRING", "description": "Título de la entrada"},
                "content":  {"type": "STRING", "description": "Contenido o texto a guardar"},
                "type":     {"type": "STRING", "description": "note | idea | snippet | reference | fact | task | question"},
                "tags":     {"type": "STRING", "description": "Tags separados por coma (ej: python, nexo, idea)"},
                "query":    {"type": "STRING", "description": "Búsqueda en la base de conocimiento"},
                "entry_id": {"type": "STRING", "description": "ID de la entrada para get/update/delete"},
                "path":     {"type": "STRING", "description": "Ruta para exportar (action=export)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "social_media",
        "description": (
            "Controla redes sociales: Twitter/X, Instagram, TikTok y LinkedIn. "
            "Twitter: publicar tweets, ver timeline, buscar, like, retweet, ver perfil. "
            "Instagram: publicar fotos, subir historias, enviar DMs, ver feed, like, comentar. "
            "TikTok: subir videos, ver perfil/stats, tendencias. "
            "LinkedIn: publicar posts, ver perfil, ver feed, enviar mensajes. "
            "SIEMPRE usar para cualquier pedido de redes sociales. "
            "Para WhatsApp usar la herramienta 'whatsapp'. "
            "Usá action=setup para ver cómo configurar las credenciales."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "platform": {"type": "STRING", "description": "twitter | instagram | tiktok | linkedin | setup"},
                "action":   {"type": "STRING", "description": (
                    "Twitter: tweet, delete_tweet, like, retweet, timeline, search_tweets, my_tweets, profile | "
                    "Instagram: post/upload_photo, story, send_dm, feed, profile, like, comment | "
                    "TikTok: upload/publicar, profile/perfil, trending | "
                    "LinkedIn: post/publicar, profile/perfil, send_message/mensaje, feed"
                )},
                "text":       {"type": "STRING", "description": "Texto del tweet/post/comentario/mensaje"},
                "content":    {"type": "STRING", "description": "Contenido del post (LinkedIn/TikTok)"},
                "tweet_id":   {"type": "STRING", "description": "ID del tweet para like/retweet/delete"},
                "media_id":   {"type": "STRING", "description": "ID del post de Instagram para like/comment"},
                "username":   {"type": "STRING", "description": "Usuario para DM/perfil (Instagram, TikTok, LinkedIn)"},
                "receiver":   {"type": "STRING", "description": "Destinatario del DM de Instagram"},
                "image_path": {"type": "STRING", "description": "Ruta imagen para Instagram/LinkedIn"},
                "video_path": {"type": "STRING", "description": "Ruta del video para TikTok"},
                "caption":    {"type": "STRING", "description": "Descripción/caption de la foto o video"},
                "query":      {"type": "STRING", "description": "Búsqueda de tweets"},
                "count":      {"type": "INTEGER", "description": "Cantidad de resultados (default: 5)"},
            },
            "required": ["platform", "action"]
        }
    },
    {
        "name": "windows_settings",
        "description": (
            "Control TOTAL de configuraciones de Windows. "
            "Usar para CUALQUIER pedido relacionado con configuración del sistema. "
            "Categorías disponibles:\n"
            "• display: brillo, resolución, frecuencia, escala, modo oscuro/noche, HDR, orientación, monitores\n"
            "• audio: volumen, mute, dispositivos de audio/micrófono, mezclador\n"
            "• network: WiFi (listar/conectar/desconectar/on/off), IP, DNS, flush_dns, modo avión, Bluetooth, proxy\n"
            "• power: plan energía, suspender, hibernar, batería, timeouts, inicio rápido\n"
            "• system: info del sistema, nombre PC, fecha/hora, zona horaria, reiniciar, apagar, bloquear, variables de entorno\n"
            "• personalization: fondo de pantalla, tema, transparencia, barra de tareas, protector de pantalla\n"
            "• apps: listar apps, desinstalar, apps de inicio, aplicaciones predeterminadas\n"
            "• security: Windows Defender, firewall, UAC, BitLocker, usuarios del sistema\n"
            "• input: velocidad mouse, doble clic, scroll, botones, velocidad teclado, idioma\n"
            "• storage: discos, espacio, limpieza de archivos temporales, papelera, defrag, chkdsk\n"
            "• services: listar/iniciar/detener/reiniciar servicios de Windows, procesos, kill\n"
            "• privacy: cámara/micrófono privacidad, ubicación, telemetría, notificaciones, portapapeles\n"
            "• registry: leer, escribir, eliminar claves del registro, exportar, backup, búsqueda, importar\n"
            "• accessibility: lupa, narrador, alto contraste, teclado en pantalla\n"
            "• open_settings: abrir panel específico de Configuración de Windows\n"
            "• cpu_temperature: temperatura CPU via WMI/Open Hardware Monitor\n"
            "• virtual_desktops: crear, cerrar, cambiar escritorios virtuales, vista de tareas\n"
            "• printers: listar impresoras, predeterminada, cola de impresión, cancelar impresión\n"
            "• fonts: listar, instalar y eliminar fuentes del sistema\n"
            "• window_control: listar/maximizar/minimizar/mover/enfocar/cerrar ventanas por proceso\n"
            "• system_restore: crear puntos de restauración, listarlos, restaurar sistema\n"
            "• startup_advanced: listar/habilitar/deshabilitar/agregar entradas de inicio\n"
            "SIEMPRE llamar para cualquier pedido de configuración, ajuste o control del sistema Windows."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "La acción a realizar. Ejemplos por categoría:\n"
                        "display: get_brightness | set_brightness | get_resolution | set_resolution | "
                        "set_refresh_rate | get_scaling | set_scaling | night_light_on | night_light_off | "
                        "hdr_on | hdr_off | set_orientation | list_monitors | open\n"
                        "audio: get_volume | set_volume | mute | unmute | toggle_mute | list_devices | "
                        "set_device | get_mic_volume | set_mic_volume | open\n"
                        "network: list_wifi | connect_wifi | disconnect_wifi | wifi_on | wifi_off | "
                        "get_ip | set_dns | flush_dns | airplane_on | airplane_off | "
                        "bluetooth_on | bluetooth_off | set_proxy | disable_proxy | open\n"
                        "power: get_plan | set_plan | list_plans | sleep | hibernate | battery_status | "
                        "set_sleep_timeout | set_screen_timeout | fast_startup_on | fast_startup_off | open\n"
                        "system: info | get_hostname | set_hostname | get_datetime | set_datetime | "
                        "set_timezone | restart | shutdown | lock | get_env | set_env | delete_env | open\n"
                        "personalization: set_wallpaper | get_wallpaper | dark_mode | light_mode | "
                        "transparency_on | transparency_off | taskbar_position | screensaver | open\n"
                        "apps: list | uninstall | startup_apps | set_default | open\n"
                        "security: defender_scan | defender_status | firewall_on | firewall_off | "
                        "firewall_status | uac_level | bitlocker_status | list_users | add_user | open\n"
                        "input: get_mouse_speed | set_mouse_speed | swap_buttons | get_keyboard_speed | "
                        "set_keyboard_speed | list_languages | add_language | open\n"
                        "storage: list_drives | disk_usage | cleanup | empty_trash | clean_temp | "
                        "defrag | chkdsk | open\n"
                        "services: list | start | stop | restart | status | list_processes | kill_process | open\n"
                        "privacy: camera_on | camera_off | mic_on | mic_off | location_on | location_off | "
                        "telemetry_level | notifications_on | notifications_off | clipboard_history_on | "
                        "clipboard_history_off | open\n"
                        "registry: read | write | delete | export | backup_registro | buscar_registro | importar_registro | listar_subclaves\n"
                        "accessibility: magnifier_on | magnifier_off | narrator_on | narrator_off | "
                        "high_contrast_on | high_contrast_off | osk_on | open\n"
                        "open_settings: <nombre del panel, ej: display, sound, wifi, bluetooth, apps>\n"
                        "cpu_temperature: temperatura_cpu | cpu_temp\n"
                        "virtual_desktops: nuevo_escritorio | cerrar_escritorio | siguiente_escritorio | anterior_escritorio | vista_tareas\n"
                        "printers: listar_impresoras | impresora_predeterminada | imprimir_prueba | cola_impresion | cancelar_impresion\n"
                        "fonts: listar_fuentes | instalar_fuente | eliminar_fuente\n"
                        "window_control: listar_ventanas | maximizar_ventana | minimizar_ventana | restaurar_ventana | cerrar_ventana | mover_ventana | enfocar_ventana\n"
                        "system_restore: crear_punto_restauracion | listar_puntos_restauracion | restaurar_sistema\n"
                        "startup_advanced: listar_inicio | habilitar_inicio | deshabilitar_inicio_reg | agregar_inicio"
                    )
                },
                "value":    {"type": "STRING",  "description": "Valor para la acción (ej: 80 para brillo, 'Dark' para tema, SSID para wifi, etc.)"},
                "value2":   {"type": "STRING",  "description": "Segundo valor cuando se necesitan dos parámetros (ej: contraseña de WiFi, valor de registro)"},
                "name":     {"type": "STRING",  "description": "Nombre del servicio, proceso, usuario, app, o variable de entorno"},
                "hive":     {"type": "STRING",  "description": "Para registry: HKLM | HKCU | HKCR | HKU | HKCC"},
                "key":      {"type": "STRING",  "description": "Para registry: ruta de la clave del registro"},
                "reg_name": {"type": "STRING",  "description": "Para registry: nombre del valor del registro"},
                "reg_type": {"type": "STRING",  "description": "Para registry: REG_SZ | REG_DWORD | REG_BINARY | REG_EXPAND_SZ"},
                "path":     {"type": "STRING",  "description": "Ruta de archivo (para wallpaper, export registry, etc.)"},
                "monitor":  {"type": "INTEGER", "description": "Índice del monitor (0, 1, 2…)"},
                "width":    {"type": "INTEGER", "description": "Ancho de resolución"},
                "height":   {"type": "INTEGER", "description": "Alto de resolución"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "image_generation",
        "description": (
            "Genera imágenes con inteligencia artificial a partir de una descripción en texto. "
            "Usa Pollinations.ai (gratis, open-source, sin API key) o Gemini. "
            "SIEMPRE llamar cuando el usuario pide 'generame una imagen', 'crea una foto de', "
            "'dibujame', 'haceme una imagen', 'quiero una foto de', o 'mostrame', etc. "
            "Después de generar, la imagen se muestra automáticamente en el widget de NEXO."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt":       {"type": "STRING",  "description": "Descripción detallada de la imagen a generar"},
                "count":        {"type": "INTEGER", "description": "Cantidad de imágenes (1-4, default: 1)"},
                "aspect_ratio": {"type": "STRING",  "description": "Relación de aspecto: 1:1 | 4:3 | 3:4 | 16:9 | 9:16 (default: 1:1)"},
                "save_path":    {"type": "STRING",  "description": "Carpeta de guardado (default: ~/Pictures/NEXO_Generadas)"},
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "smart_home",
        "description": (
            "Controla las luces y dispositivos inteligentes del hogar. "
            "Soporta Tuya/Smart Life, Philips Hue, LIFX y Yeelight. "
            "SIEMPRE llamar para: encender/apagar luces, cambiar color, brillo, temperatura de color, "
            "activar escenas, consultar estado. "
            "Si no hay dispositivos configurados, usar action=setup para ver instrucciones."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",  "description": "on | off | toggle | color | brightness | temperature | scene | status | list | setup"},
                "device":      {"type": "STRING",  "description": "Nombre o sala del dispositivo (ej: 'sala', 'cuarto', 'lampara principal'). Omitir = todos."},
                "color":       {"type": "STRING",  "description": "Color: nombre (rojo, azul, blanco, cálido…) o hex #RRGGBB"},
                "value":       {"type": "INTEGER", "description": "Valor numérico para brightness (1-100) o temperatura Kelvin (1700-9000)"},
                "brightness":  {"type": "INTEGER", "description": "Brillo 1-100 (alternativa a value)"},
                "scene":       {"type": "STRING",  "description": "Nombre de la escena: relajar, leer, trabajar, noche, fiesta"},
                "protocol":    {"type": "STRING",  "description": "tuya | hue | lifx | yeelight. Omitir = usa el configurado por defecto."},
                "group":       {"type": "STRING",  "description": "Nombre del grupo/sala en Philips Hue"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "system_monitor",
        "description": (
            "Monitorea el rendimiento del sistema en tiempo real: CPU, RAM, GPU, discos, "
            "red, temperatura, batería, procesos activos, uptime. "
            "Usar para: '¿cómo está la PC?', 'qué proceso consume más', 'temperatura del CPU', "
            "'cuánta RAM libre tengo', 'matar proceso X', 'resumen de rendimiento'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING",  "description": "cpu | ram | disk | network | gpu | temperature | battery | uptime | processes | kill | report"},
                "sort_by":  {"type": "STRING",  "description": "Para processes: cpu (default) | ram"},
                "count":    {"type": "INTEGER", "description": "Para processes: cantidad a mostrar (default: 10)"},
                "name":     {"type": "STRING",  "description": "Para kill: nombre o PID del proceso"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "document_creator",
        "description": (
            "Creates Word documents (.docx) or Excel spreadsheets (.xlsx) locally, "
            "OR Google Docs / Google Sheets in the cloud. "
            "Use when the user asks to create a document, report, letter, table, spreadsheet, "
            "budget, list, or any file with structured content. "
            "For documents: provide title and content (use ## for headings, - for bullet lists). "
            "For spreadsheets: provide title and sheets with headers and rows. "
            "Always call this tool — never just say you created it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "word — create a local .docx Word file | "
                        "excel — create a local .xlsx Excel file | "
                        "google_doc — create a Google Doc in the cloud | "
                        "google_sheet — create a Google Sheet in the cloud"
                    )
                },
                "title": {
                    "type": "STRING",
                    "description": "Title or filename of the document/spreadsheet"
                },
                "content": {
                    "type": "STRING",
                    "description": (
                        "For word / google_doc: full text content. "
                        "Use ## Section for main headings, # SubSection for sub-headings, "
                        "- item for bullet points, blank line between paragraphs."
                    )
                },
                "sheets": {
                    "type": "ARRAY",
                    "description": (
                        "For excel / google_sheet: list of sheet objects. "
                        "Each object has: name (string), headers (array of strings), "
                        "rows (array of arrays with cell values)."
                    ),
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "name":    {"type": "STRING", "description": "Sheet tab name"},
                            "headers": {"type": "ARRAY",  "items": {"type": "STRING"}, "description": "Column headers"},
                            "rows":    {"type": "ARRAY",  "items": {"type": "ARRAY", "items": {"type": "STRING"}}, "description": "Data rows"}
                        }
                    }
                },
                "save_path": {
                    "type": "STRING",
                    "description": "Optional: full file path to save locally (e.g. C:/Users/User/Desktop/report.docx). Defaults to ~/Documents/"
                }
            },
            "required": ["action", "title"]
        }
    },
    {
        "name": "tiktok_analyzer",
        "description": (
            "Analiza un perfil público de TikTok dado su URL. "
            "Extrae el nombre, bio, seguidores, y para cada video reciente: "
            "vistas, likes, comentarios y guardados. "
            "Siempre usar cuando el usuario pida analizar un perfil de TikTok "
            "o consultar estadísticas de videos de TikTok."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "profile_url": {"type": "STRING", "description": "URL completa del perfil de TikTok (ej: https://www.tiktok.com/@usuario)"},
                "max_videos":  {"type": "INTEGER", "description": "Cantidad máxima de videos a analizar (default: 8)"},
            },
            "required": ["profile_url"]
        }
    },
    {
        "name": "arca_invoice",
        "description": (
            "Genera comprobantes digitales electrónicos válidos ante ARCA (ex AFIP). "
            "Para Argentina. Soporta Factura A, B, C, Nota de Crédito, Nota de Débito. "
            "Puede operar offline (comprobante local) o conectarse con ARCA si hay certificado. "
            "SIEMPRE usar cuando el usuario pida: 'generame una factura', 'haceme un comprobante', "
            "'necesito una factura A/B/C', 'emití una nota de crédito', o similar. "
            "Usar action='listar' para mostrar los tipos disponibles."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":         {"type": "STRING", "description": "generar | listar | historial"},
                "tipo":           {"type": "INTEGER", "description": "1=Factura A, 5=Factura C (default), 6=Factura B, 3=NC A, 8=NC B, etc. Usá action=listar para ver todos."},
                "razon_social":   {"type": "STRING", "description": "Razón social del receptor (obligatorio para Factura A/B)"},
                "cuit_receptor":  {"type": "STRING", "description": "CUIT del receptor (obligatorio para Factura A/B)"},
                "domicilio":      {"type": "STRING", "description": "Domicilio del receptor (opcional)"},
                "detalle":        {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"descripcion": {"type": "STRING"}, "precio": {"type": "NUMBER"}, "cantidad": {"type": "INTEGER"}}}, "description": "Lista de productos/servicios: [{'descripcion':'...', 'precio':0.0, 'cantidad':1}]"},
                "importe_neto":   {"type": "NUMBER", "description": "Importe neto gravado (se calcula del detalle si no se especifica)"},
                "importe_iva":    {"type": "NUMBER", "description": "Importe de IVA (se calcula al 21% si no se especifica)"},
                "iva_pct":        {"type": "NUMBER", "description": "Porcentaje de IVA (default: 21.0). 0 para exento."},
                "fecha":          {"type": "STRING", "description": "Fecha del comprobante YYYY-MM-DD (default: hoy)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "accessibility",
        "description": (
            "Modulo de accesibilidad universal. "
            "Incluye: task_simplify (descomponer tareas complejas en pasos simples), "
            "emotional (regulacion emocional y analisis de tono de voz), "
            "routine (rutinas diarias gamificadas con racha y progreso), "
            "eye_tracking (control por seguimiento ocular con webcam), "
            "micro_movement (navegacion por movimientos de cabeza), "
            "speech_config (ajustar tolerancia del reconocimiento de voz). "
            "Usar cuando el usuario pida: 'simplificame esto', 'ayudame con mi rutina', "
            "'necesito organizarme', 'activar seguimiento ocular', 'ajusta la tolerancia de voz', "
            "'ejercicio de respiracion', 'complete mi tarea', 'agregar rutina'. "
            "SIEMPRE ofrecer alternativas multimodales."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "task_simplify — descomponer texto en pasos simples | "
                        "emotional — intervencion emocional | "
                        "routine — gestion de rutinas gamificadas | "
                        "eye_tracking — control ocular | "
                        "micro_movement — micromovimientos | "
                        "speech_config — tolerancia de voz | "
                        "feedback — feedback visual/haptico | "
                        "config — ver o cambiar configuracion"
                    )
                },
                "text":     {"type": "STRING", "description": "Texto a simplificar (para task_simplify)"},
                "format":   {"type": "STRING", "description": "Formato: steps (default) | summary | explain"},
                "name":     {"type": "STRING", "description": "Nombre de rutina (para routine add/complete)"},
                "setting":  {"type": "STRING", "description": "Clave de configuracion a ver o cambiar"},
                "value":    {"type": "STRING", "description": "Valor para la configuracion"},
                "level":    {"type": "NUMBER", "description": "Nivel de tolerancia (0.1-1.0) o sensibilidad"},
                "stress_level": {"type": "NUMBER", "description": "Nivel de estres estimado (0.0-1.0)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "screen_vision",
        "description": (
            "NEXO puede VER la pantalla del usuario. Captura lo que está en el monitor "
            "y usa IA (Gemini Vision) para describirlo, responder preguntas, leer texto, "
            "o dar ayuda contextual basada en lo que se está mostrando.\n"
            "SIEMPRE usar cuando el usuario diga: '¿qué estoy viendo?', '¿qué hay en mi pantalla?', "
            "'¿qué dice ahí?', 'ayúdame con esto' (señalando la pantalla), 'leé lo que hay en pantalla', "
            "'¿podés ver mi pantalla?', 'describí lo que tengo abierto', etc."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "describe=describir qué hay en pantalla | question=responder pregunta sobre la pantalla | help=dar ayuda contextual | read=leer todo el texto visible"
                },
                "question": {
                    "type": "STRING",
                    "description": "Pregunta o tarea específica sobre lo que se ve en pantalla (para action=question/help)"
                },
                "monitor": {
                    "type": "INTEGER",
                    "description": "0=toda la pantalla (default), 1=monitor principal, 2=segundo monitor"
                },
            },
            "required": ["action"]
        }
    },
    {
        "name": "nexo_ui_control",
        "description": (
            "Control total sobre los widgets de la interfaz de NEXO. "
            "Permite abrir, cerrar o alternar la visibilidad de cualquier widget del dashboard.\n"
            "Widgets disponibles: weather (clima), spotify (música), system (sistema), "
            "notes (notas), todo (tareas), maps (mapas), image (imágenes), camera (cámara).\n"
            "SIEMPRE usar cuando el usuario pida: 'abrí el widget de clima', 'cerrá la música', "
            "'mostrá el sistema', 'ocultá todo', 'abrí la cámara', etc."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "show=mostrar widget | hide=ocultar widget | hide_all=ocultar todos | toggle=alternar visibilidad"
                },
                "widget": {
                    "type": "STRING",
                    "description": "Nombre del widget: weather | spotify | system | notes | todo | maps | image | camera"
                },
            },
            "required": ["action"]
        }
    },
    {
        "name": "morning_brief",
        "description": (
            "Genera el informe matutino inteligente de NEXO. "
            "Incluye saludo personalizado, hora, fecha, clima actual, objetivos activos y consejo del día. "
            "Usar cuando el usuario pida: 'informe del día', 'brief matutino', 'qué hay hoy', "
            "'resumen del día', 'buenos días NEXO', o al iniciar el día."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "force": {
                    "type": "boolean",
                    "description": "Si True, genera el informe aunque ya se haya dado hoy."
                }
            },
            "required": []
        }
    },
    {
        "name": "vision_guardian",
        "description": (
            "Controla el Guardian de Visión Ambiental de NEXO — monitoreo proactivo de pantalla. "
            "Analiza la pantalla periódicamente con IA y ofrece ayuda contextual cuando detecta algo relevante. "
            "Usar cuando el usuario diga: 'activa el guardian', 'desactiva el guardian', "
            "'vigila mi pantalla', 'deja de vigilar', 'analiza mi pantalla ahora', "
            "'estado del guardian', 'cambia el intervalo'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "enable", "disable", "check_now", "set_interval"],
                    "description": "Acción: status | enable | disable | check_now | set_interval"
                },
                "seconds": {
                    "type": "integer",
                    "description": "Para set_interval: segundos entre análisis (30-600)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "accessibility_overlay",
        "description": (
            "Muestra, oculta o alterna la barra flotante de accesibilidad NEXO sobre el escritorio. "
            "USAR cuando el usuario diga: 'mostrar barra de accesibilidad', 'abrir panel de accesibilidad', "
            "'activar barra para ciegos', 'cerrar barra', 'ocultar barra de accesibilidad', "
            "'alternar barra', 'barra de accesibilidad'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "show — mostrar | hide — cerrar | toggle — alternar | status — estado actual"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "nexo_update",
        "description": (
            "Gestión de actualizaciones de NEXO. "
            "Usar cuando el usuario diga: 'buscar actualización', 'actualizar NEXO', "
            "'hay alguna actualización', 'instalar actualización', 'versión de NEXO', "
            "'qué versión tengo', 'descargar actualización', 'aplicar update'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "check — verificar si hay update disponible | apply — descargar y aplicar update | version — ver versión actual"
                },
                "url": {
                    "type": "STRING",
                    "description": "URL del ZIP de actualización (solo para action=apply si se especifica manualmente)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "ollama_status",
        "description": (
            "Estado y control del modelo Ollama local de NEXO. "
            "Usar cuando el usuario pregunte: 'estado de Ollama', 'qué modelos tengo en Ollama', "
            "'Ollama está funcionando', 'listar modelos locales', 'descargar modelo Ollama'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "status — estado y modelos disponibles | pull — descargar modelo"
                },
                "model": {
                    "type": "STRING",
                    "description": "Nombre del modelo (ej: llama3.2, mistral, phi3)"
                }
            },
            "required": ["action"]
        }
    },
]

class NexoLive:

    def __init__(self, ui: NexoUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        # Iniciar scheduler y motor de reglas en background al arrancar NEXO
        try:
            start_runner(player=ui, speak=None)
        except Exception as _sr_err:
            print(f"[NEXO] start_runner error (non-fatal): {_sr_err}")
        try:
            start_rules_runner(player=ui, speak=None)
        except Exception as _rr_err:
            print(f"[NEXO] start_rules_runner error (non-fatal): {_rr_err}")
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._stop_requested = threading.Event()
        # Barge-in (interruption) state
        self._barge_in_frames   = 0          # consecutive loud mic frames during speaking
        self._BARGE_IN_FRAMES   = 6          # ~96ms de voz sostenida para interrumpir (balance: responde bien, ignora ruido breve)
        self._BARGE_IN_THRESH   = 0.042      # RMS threshold — voz real (~0.04-0.15), rechaza ventilador/eco (~0.001-0.025)
        self._barge_in_cooldown = 0.0        # epoch time after which barge-in is allowed
        self._BARGE_IN_COOLDOWN = 1.5        # 1.5s cooldown tras terminar NEXO (evita eco del speaker)
        self.ui.on_text_command = self._on_text_command
        self.ui.on_stop_command = self._on_stop_pressed
        self.ui.on_config_saved = self._apply_config
        self._turn_done_event: asyncio.Event | None = None
        self._api_1011_tool: str | None = None   # tracks tool name when 1011 hits
        self._reconnect_event: asyncio.Event | None = None
        self._first_connect = True  # flag for auto morning brief + guardian start

    def _inject_text(self, text: str):
        """Thread-safe injection of a text message into the current live session."""
        if self._loop and self.session and not self._is_speaking:
            asyncio.run_coroutine_threadsafe(
                self.session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True
                ),
                self._loop
            )

    def _apply_config(self, cfg: dict):
        """Called from UI thread when user saves settings. Triggers session reconnect."""
        print("[NEXO] ⚙️ Config actualizada — reconectando sesión...")
        self.ui.write_log("SYS: Aplicando nueva configuración...")

        # Apply audio device changes immediately via sounddevice defaults
        # (the new stream opened on reconnect will re-read from config file)
        try:
            mic_idx = cfg.get("mic_device", None)
            spk_idx = cfg.get("spk_device", None)
            if isinstance(mic_idx, int) and isinstance(spk_idx, int):
                sd.default.device = (mic_idx, spk_idx)
                print(f"[NEXO] 🎤 Dispositivos → mic={mic_idx}, spk={spk_idx}")
                self.ui.write_log(f"SYS: Micrófono [{mic_idx}] / Altavoz [{spk_idx}] aplicados.")
        except Exception as _dev_err:
            print(f"[NEXO] ⚠ Audio device change: {_dev_err}")

        if self._reconnect_event and self._loop:
            self._loop.call_soon_threadsafe(self._reconnect_event.set)

    async def _watch_reconnect(self):
        """Task that triggers a graceful reconnect when config changes."""
        if self._reconnect_event:
            await self._reconnect_event.wait()
            raise RuntimeError("Config changed — reconnect requested")

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return

        # Audio file: process with Gemini Vision (not the realtime audio session)
        if text.startswith("[AUDIO_FILE]"):
            m = re.search(r'path=([^\s|]+)', text)
            if m:
                asyncio.run_coroutine_threadsafe(
                    self._process_audio_file(m.group(1)), self._loop
                )
            return

        # ── Nexo Emotional Intelligence ────────────────────────────────────
        emotion_context = get_emotional_context(text)
        if emotion_context:
            # Log emotional state in UI
            self.ui.write_log(f"🧠 {emotion_context.split(chr(10))[0]}")
            # Inject emotion context + user text to Gemini
            enriched_text = f"{emotion_context}\n\nMensaje del usuario:\n{text}"
            asyncio.run_coroutine_threadsafe(
                self.session.send_client_content(
                    turns={"parts": [{"text": enriched_text}]},
                    turn_complete=True
                ),
                self._loop
            )
            return
        # ────────────────────────────────────────────────────────────────────

        # Check phrase triggers — if one fires, don't also send to Gemini
        if self._fire_phrase_triggers(text):
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    async def _process_audio_file(self, path: str):
        """Transcribe and analyze an audio file via Gemini (separate from realtime session)."""
        try:
            p = Path(path)
            if not p.exists():
                self.ui.write_log(f"❌ Archivo no encontrado: {path}")
                return

            self.ui.set_state("THINKING")
            self.ui.write_log(f"🎵 Procesando audio: {p.name}…")

            data = p.read_bytes()
            ext  = p.suffix.lower().lstrip(".")
            mime_map = {
                "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4",
                "ogg": "audio/ogg",  "flac": "audio/flac", "aac": "audio/aac",
                "wma": "audio/x-ms-wma", "opus": "audio/opus", "webm": "audio/webm",
            }
            mime = mime_map.get(ext, "audio/mpeg")

            loop = asyncio.get_event_loop()

            def _analyze():
                client = genai.Client(api_key=_get_api_key())
                resp = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        types.Content(parts=[
                            types.Part(text=(
                                f"El usuario adjuntó un archivo de audio: '{p.name}'.\n"
                                "1. Transcribí el contenido del audio.\n"
                                "2. Si es música, identificá la canción/artista si podés.\n"
                                "3. Describí brevemente qué contiene.\n"
                                "Respondé en español."
                            )),
                            types.Part(
                                inline_data=types.Blob(data=data, mime_type=mime)
                            ),
                        ])
                    ],
                )
                return resp.text.strip()

            result = await loop.run_in_executor(None, _analyze)
            self.ui.write_log(f"NEXO: {result}")

            # Feed result back into the realtime session so NEXO can speak it
            if self.session:
                await self.session.send_client_content(
                    turns={"parts": [{"text": f"[RESULTADO AUDIO '{p.name}']\n{result}"}]},
                    turn_complete=True
                )

        except Exception as e:
            traceback.print_exc()
            self.ui.write_log(f"❌ Error procesando audio: {e}")
        finally:
            if not self.ui.muted:
                self.ui.set_state("LISTENING")

    def _fire_phrase_triggers(self, user_text: str) -> bool:
        """
        Check phrase-based automations. Returns True if any trigger fired
        (caller should skip sending the text to Gemini in that case).
        """
        text_lower = user_text.lower()

        # ── Accessibility quick triggers ──────────────────────────────────────
        if any(p in text_lower for p in ["activar seguimiento ocular", "iniciar eye tracking",
                                          "activar control ocular", "encender seguimiento de ojos"]):
            from actions.accessibility import eye_tracking
            result = eye_tracking({"action": "start"})
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["detener seguimiento ocular", "apagar eye tracking",
                                          "desactivar control ocular"]):
            from actions.accessibility import eye_tracking
            result = eye_tracking({"action": "stop"})
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["activar detector de movimientos", "iniciar movimiento",
                                          "activar micromovimientos", "encender control por cabeza"]):
            from actions.accessibility import micro_movement
            result = micro_movement({"action": "start"})
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["detener detector de movimientos", "apagar micromovimientos"]):
            from actions.accessibility import micro_movement
            result = micro_movement({"action": "stop"})
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["simplifica", "simplificar", "dividir en pasos"]):
            for phrase in ["simplifica ", "simplificar ", "dividir en pasos "]:
                if phrase in text_lower:
                    task_text = user_text[len(phrase):].strip()
                    if task_text:
                        from actions.accessibility import task_simplify
                        result = task_simplify(task_text)
                        self.ui.write_log("⚡ [Simplificado]\n" + result[:300])
                        return True

        if "agregar rutina" in text_lower or "nueva rutina" in text_lower:
            for phrase in ["agregar rutina ", "nueva rutina "]:
                if phrase in text_lower:
                    routine_name = user_text[len(phrase):].strip()
                    if routine_name:
                        from actions.accessibility import routine_gamify
                        result = routine_gamify({"action": "add", "name": routine_name})
                        self.ui.write_log("⚡ " + result)
                        return True

        if "completar rutina" in text_lower or "terminar rutina" in text_lower:
            for phrase in ["completar rutina ", "terminar rutina "]:
                if phrase in text_lower:
                    routine_name = user_text[len(phrase):].strip()
                    if routine_name:
                        from actions.accessibility import routine_gamify
                        result = routine_gamify({"action": "complete", "name": routine_name})
                        self.ui.write_log("⚡ " + result)
                        return True

        if "mis rutinas" in text_lower or "ver rutinas" in text_lower or "listar rutinas" in text_lower:
            from actions.accessibility import routine_gamify
            result = routine_gamify({"action": "list"})
            self.ui.write_log("⚡ [Rutinas]\n" + result)
            return True

        # ── Extended disability quick triggers ─────────────────────────────────
        if any(p in text_lower for p in ["modo visual", "modo sordo", "sin audio", "modo silencioso"]):
            from actions.accessibility import _deaf_mode
            result = _deaf_mode({"action": "on"})
            self.ui.write_log("⚡ " + result[:120])
            return True

        if any(p in text_lower for p in ["modo auditivo", "activar audio", "volver audio"]):
            from actions.accessibility import _deaf_mode
            result = _deaf_mode({"action": "off"})
            self.ui.write_log("⚡ " + result[:120])
            return True

        if any(p in text_lower for p in ["abrir lupa", "activar lupa", "ampliar pantalla", "zoom pantalla"]):
            from actions.accessibility import _magnify
            result = _magnify({"action": "open"})
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["teclado en pantalla", "abrir teclado virtual"]):
            from actions.accessibility import _switch_access
            result = _switch_access({"action": "keyboard"})
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["modo foco", "modo concentración", "sin distracciones", "modo adhd"]):
            from actions.accessibility import _focus_mode
            result = _focus_mode({"action": "on"})
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["desactivar foco", "quitar foco", "salir foco"]):
            from actions.accessibility import _focus_mode
            result = _focus_mode({"action": "off"})
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["modo lectura", "modo dislexia", "leer despacio"]):
            from actions.accessibility import _reading_mode
            result = _reading_mode({"action": "on"})
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["habla más lento", "habla lento", "más despacio", "mas despacio"]):
            from actions.accessibility import _voice_speed
            result = _voice_speed({"level": "0.85"})
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["habla más rápido", "habla rápido", "más rápido", "mas rapido"]):
            from actions.accessibility import _voice_speed
            result = _voice_speed({"level": "1.3"})
            self.ui.write_log("⚡ " + result)
            return True

        # ── User-defined phrase automations ───────────────────────────────────
        try:
            triggered = check_phrase_triggers(user_text)
            if triggered:
                for rule in triggered:
                    action = rule.get("action", {})
                    name   = rule.get("name", "?")
                    self.ui.write_log(f"⚡ Automatización: {name}")
                    threading.Thread(
                        target=_rules_run_action, args=(action,), daemon=True
                    ).start()
                return True  # phrase fired → don't also send to Gemini
        except Exception as e:
            print(f"[NEXO] phrase trigger error: {e}")

        return False

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
            self._barge_in_frames = 0   # reset counter whenever speaking starts
        else:
            # Set cooldown: ignore barge-in for N seconds after speaking ends
            self._barge_in_cooldown = time.monotonic() + self._BARGE_IN_COOLDOWN
            if not self.ui.muted:
                self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        # Only log — Gemini narrates the error naturally from the FunctionResponse result.
        # Calling speak() here would cause double-speech (SAPI + Charon voice).
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        print(f"[NEXO] ❌ Tool error — {tool_name}: {short}")

    def _on_stop_pressed(self):
        """Llamado desde el hilo de la UI al presionar DETENER o ESC."""
        self._stop_requested.set()
        self.set_speaking(False)
        self.ui.write_log("SYS: ⛔ Respuesta detenida.")
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._drain_audio_queue(), self._loop)

    async def _drain_audio_queue(self):
        """Vacía la cola de audio para cortar la reproducción de inmediato."""
        if self.audio_in_queue:
            while not self.audio_in_queue.empty():
                try:
                    self.audio_in_queue.get_nowait()
                except Exception:
                    break
        self.set_speaking(False)
        if not self.ui.muted:
            self.ui.set_state("LISTENING")

    async def _do_barge_in(self):
        """Stop NEXO playback immediately so the user can speak (barge-in)."""
        if not self._is_speaking:
            return   # Already stopped — nothing to interrupt
        self.ui.write_log("SYS: 🎤 Interrumpiendo…")
        self._stop_requested.set()
        await self._drain_audio_queue()
        # Brief pause so the audio output device drains its hardware buffer
        await asyncio.sleep(0.05)
        self._stop_requested.clear()
        # Mic callback now sees _is_speaking=False → starts forwarding audio again

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        # Refresh timezone from config each reconnect
        _load_tz()
        now      = datetime.now(_BA_TZ)
        time_str = now.strftime("%A, %d %B %Y — %I:%M:%S %p")
        utc_off  = now.strftime("%z")
        tz_name  = str(_BA_TZ)
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Timezone: {tz_name} (UTC{utc_off})\n"
            f"The current Unix timestamp is: {int(now.timestamp())}\n"
            f"Use this information to calculate exact times for reminders, scheduling, and answering time-related questions.\n\n"
        )

        parts = [time_ctx]

        # Inject existing automations so NEXO always remembers them across sessions
        try:
            from actions.rules_engine import _load as _load_rules
            _existing_rules = _load_rules()
            if _existing_rules:
                _rule_lines = []
                for _r in _existing_rules:
                    _st   = "ENABLED" if _r.get("enabled", True) else "DISABLED"
                    _c    = _r.get("condition", {})
                    _a    = _r.get("action", {})
                    _c_t  = _c.get("type", "?")
                    _c_desc = _c_t + (
                        f":'{_c.get('trigger','')}'" if _c_t == "phrase" else
                        f":hour={_c.get('hour',0)}:{_c.get('minute',0):02d}" if _c_t == "time" else ""
                    )
                    _a_t  = _a.get("type", "?")
                    _a_val = _a.get("message", _a.get("app_name", _a.get("url", _a.get("query", ""))))
                    _a_desc = _a_t + (f":'{_a_val}'" if _a_val else "")
                    _rule_lines.append(
                        f"  [{_r.get('id','?')}] {_r.get('name','?')} [{_st}]"
                        f" — when {_c_desc} → {_a_desc}"
                    )
                parts.append(
                    "[SAVED AUTOMATIONS — persisted across sessions]\n"
                    + "\n".join(_rule_lines)
                    + "\n\nThese are already saved and active. "
                    "Phrase-type triggers fire automatically when the user says the trigger phrase.\n"
                )
        except Exception:
            pass

        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        # Build SpeechConfig — try to set speaking rate for faster delivery
        _voice_name = _get_nexo_voice()
        _speech_cfg = None
        try:
            _speech_cfg = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=_voice_name
                    )
                )
            )
        except Exception:
            _speech_cfg = None

        cfg_kwargs: dict = dict(
            response_modalities=["AUDIO"],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
        )
        if _speech_cfg:
            cfg_kwargs["speech_config"] = _speech_cfg

        # Speaking rate: try output_audio_config (newer SDK versions)
        try:
            # Respect user-configured voice speed (accessibility setting)
            _voice_spd = 1.15
            try:
                from actions.accessibility import _load_cfg as _acc_cfg
                _voice_spd = float(_acc_cfg().get("voice_speed", 1.15))
                _voice_spd = max(0.5, min(2.0, _voice_spd))
            except Exception:
                pass
            cfg_kwargs["output_audio_config"] = types.OutputAudioConfig(
                audio_encoding="LINEAR16",
                speaking_rate=_voice_spd,
            )
        except Exception:
            pass

        # Temperature directly on LiveConnectConfig (not via deprecated generation_config)
        # Low value = consistent voice tone across reconnects
        try:
            cfg_kwargs["temperature"] = 0.2
        except Exception:
            pass

        # ── VAD: faster end-of-speech detection → lower perceived latency ────
        # Try typed objects first; fall back to raw dict (SDK version resilience)
        _vad_applied = False
        try:
            cfg_kwargs["realtime_input_config"] = types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity="START_SENSITIVITY_HIGH",
                    end_of_speech_sensitivity="END_SENSITIVITY_HIGH",
                    prefix_padding_ms=50,      # menos padding al inicio → respuesta más rápida
                    silence_duration_ms=500,   # 500ms — detecta fin de frase sin cortar frases largas
                )
            )
            _vad_applied = True
            print("[NEXO] VAD config aplicado (typed)")
        except Exception:
            pass

        if not _vad_applied:
            try:
                cfg_kwargs["realtime_input_config"] = {
                    "automatic_activity_detection": {
                        "start_of_speech_sensitivity": "START_SENSITIVITY_HIGH",
                        "end_of_speech_sensitivity": "END_SENSITIVITY_HIGH",
                        "prefix_padding_ms": 50,
                        "silence_duration_ms": 500,
                    }
                }
                print("[NEXO] VAD config aplicado (dict)")
            except Exception:
                print("[NEXO] VAD config no aplicado")

        # ── Context compression: prevent session degradation over time ────────
        try:
            cfg_kwargs["context_window_compression"] = types.ContextWindowCompressionConfig(
                trigger_tokens=12000,
                sliding_window=types.SlidingWindow(target_tokens=6000),
            )
        except Exception:
            pass

        # ── Thinking budget: disable model reasoning for lowest latency ─────────
        # Set directly on LiveConnectConfig (generation_config field is deprecated)
        try:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except Exception:
            pass

        # ── Media resolution: low for faster response on voice-only sessions ──
        try:
            cfg_kwargs["media_resolution"] = "MEDIA_RESOLUTION_LOW"
        except Exception:
            pass

        return types.LiveConnectConfig(**cfg_kwargs)

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[NEXO] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        # ── Beta: PRO + daily-limit guard (wrapped so exceptions never crash the session)
        try:
            if is_pro_tool(name):
                msg = pro_tool_message(name)
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return types.FunctionResponse(
                    id=fc.id, name=name, response={"result": msg}
                )

            _internal = {"shutdown_nexo", "save_memory", "nexo_ui_control"}
            if name not in _internal:
                within_limit, calls_today = check_daily_limit()
                if not within_limit:
                    msg = daily_limit_message(calls_today)
                    if not self.ui.muted:
                        self.ui.set_state("LISTENING")
                    return types.FunctionResponse(
                        id=fc.id, name=name, response={"result": msg}
                    )
                increment_calls()
        except Exception as _beta_check_err:
            print(f"[Beta] check error (non-fatal): {_beta_check_err}")

        if name == "shutdown_nexo":
            self.ui.write_log("SYS: Apagando NEXO...")
            # Must quit from Qt main thread — signals are thread-safe
            self.ui._win._shutdown_sig.emit()
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Apagando NEXO. ¡Hasta luego, señor!"}
            )

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Memory saved."}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                # Run in executor (blocking call) — returns Spanish text for NEXO to speak
                r = await loop.run_in_executor(
                    None,
                    lambda: screen_process(
                        parameters=args, response=None,
                        player=self.ui, session_memory=None
                    )
                )
                result = r or "No pude analizar la imagen."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "google_calendar":
                r = await loop.run_in_executor(None, lambda: google_calendar(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "spotify_control":
                r = await loop.run_in_executor(None, lambda: spotify_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "rgb_control":
                r = await loop.run_in_executor(None, lambda: rgb_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "scheduler":
                r = await loop.run_in_executor(None, lambda: scheduler(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "google_drive":
                r = await loop.run_in_executor(None, lambda: google_drive(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "google_maps":
                r = await loop.run_in_executor(None, lambda: google_maps(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "gmail_control":
                r = await loop.run_in_executor(None, lambda: gmail_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "rules_engine":
                r = await loop.run_in_executor(None, lambda: rules_engine(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "user_profile":
                r = await loop.run_in_executor(None, lambda: user_profile(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "goals":
                r = await loop.run_in_executor(None, lambda: goals(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "git_control":
                r = await loop.run_in_executor(None, lambda: git_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "codebase":
                r = await loop.run_in_executor(None, lambda: codebase(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "knowledge_base":
                r = await loop.run_in_executor(None, lambda: knowledge_base(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "whatsapp":
                r = await loop.run_in_executor(None, lambda: whatsapp(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "social_media":
                r = await loop.run_in_executor(None, lambda: social_media(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "windows_settings":
                r = await loop.run_in_executor(None, lambda: windows_settings(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "document_creator":
                r = await loop.run_in_executor(None, lambda: document_creator(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "image_generation":
                r = await loop.run_in_executor(None, lambda: image_generation(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "smart_home":
                r = await loop.run_in_executor(None, lambda: smart_home(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "system_monitor":
                r = await loop.run_in_executor(None, lambda: system_monitor(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "tiktok_analyzer":
                r = await loop.run_in_executor(None, lambda: tiktok_analyzer(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "arca_invoice":
                r = await loop.run_in_executor(None, lambda: arca_invoice(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "accessibility":
                r = await loop.run_in_executor(None, lambda: accessibility(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "screen_vision":
                r = await loop.run_in_executor(None, lambda: screen_vision(parameters=args, player=self.ui))
                result = r or "No pude analizar la pantalla."

            elif name == "morning_brief":
                r = await loop.run_in_executor(None, lambda: morning_brief(parameters=args, player=self.ui))
                result = r or "Aquí está tu informe del día."

            elif name == "vision_guardian":
                r = await loop.run_in_executor(None, lambda: vision_guardian(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "screen_reader":
                r = await loop.run_in_executor(None, lambda: screen_reader(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "accessibility_overlay":
                r = await loop.run_in_executor(None, lambda: accessibility_overlay(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "nexo_ui_control":
                action_ui = args.get("action", "").lower()
                widget_name = args.get("widget", "").lower()
                if action_ui == "hide_all":
                    self.ui.write_log("__hide__")
                    result = "Todos los widgets ocultados."
                elif action_ui in ("show", "hide", "toggle"):
                    cmd = "__widget_show__" if action_ui in ("show", "toggle") else "__widget_close__"
                    self.ui.write_log(f"{cmd}:{widget_name}")
                    result = f"Widget '{widget_name}' {'mostrado' if 'show' in cmd else 'ocultado'}."
                else:
                    result = f"Acción desconocida: {action_ui}"

            elif name == "nexo_update":
                action_upd = args.get("action", "check").lower()
                try:
                    from core.updater import check_for_update, apply_update, current_version
                    if action_upd == "version":
                        result = f"NEXO v{current_version()} en ejecución."
                    elif action_upd == "check":
                        info = await loop.run_in_executor(None, check_for_update)
                        if info:
                            result = (
                                f"Nueva versión disponible: v{info['version']} "
                                f"(actual: v{info['current']}). "
                                f"Novedades: {info.get('notes', 'Sin detalles')}. "
                                f"Peso: ~{info.get('size_mb', '?')} MB. "
                                f"¿Querés aplicar la actualización ahora?"
                            )
                        else:
                            result = f"NEXO está actualizado (v{current_version()})."
                    elif action_upd == "apply":
                        url = args.get("url", "")
                        if not url:
                            info = await loop.run_in_executor(None, check_for_update)
                            if not info:
                                result = "No hay actualizaciones disponibles en este momento."
                            elif not info.get("url"):
                                result = "No se encontró URL de descarga para la actualización."
                            else:
                                url = info["url"]
                        if url:
                            self.ui.write_log("SYS: Descargando actualización...")
                            ok, msg = await loop.run_in_executor(
                                None, lambda: apply_update(url)
                            )
                            if ok:
                                result = f"{msg} Reiniciá NEXO para aplicar los cambios."
                            else:
                                result = f"Error en la actualización: {msg}"
                    else:
                        result = "Acciones válidas: check | apply | version"
                except Exception as _upd_e:
                    result = f"Error en actualización: {_upd_e}"

            elif name == "ollama_status":
                action_oll = args.get("action", "status").lower()
                try:
                    from actions.ollama_provider import is_available, list_models, pull_model
                    from core.model_router import status as _router_status
                    if action_oll == "status":
                        st = _router_status()
                        ok = st["ollama_reachable"]
                        models = list_models() if ok else []
                        result = (
                            f"Ollama {'✅ disponible' if ok else '❌ no disponible'}. "
                            f"URL: {st['ollama_base_url']}. "
                            f"Modelo configurado: {st['ollama_model']}. "
                            + (f"Modelos instalados: {', '.join(models[:10])}." if models else
                               "No hay modelos instalados localmente." if ok else
                               "Asegurate de que Ollama esté ejecutándose (ollama serve).")
                        )
                    elif action_oll == "pull":
                        model_name = args.get("model", "")
                        if not model_name:
                            result = "Especificá el nombre del modelo (ej: llama3.2, mistral)"
                        else:
                            self.ui.write_log(f"SYS: Descargando modelo Ollama '{model_name}'...")
                            ok, msg = await loop.run_in_executor(
                                None, lambda: pull_model(model_name)
                            )
                            result = msg
                    else:
                        result = "Acciones válidas: status | pull"
                except Exception as _oll_e:
                    result = f"Error Ollama: {_oll_e}"

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        # Record action for habit learning
        try:
            record_action(name, args)
        except Exception:
            pass

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[NEXO] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            try:
                await self.session.send_realtime_input(media=msg)
            except Exception as _e:
                # Network hiccup — log and propagate so TaskGroup can reconnect
                print(f"[NEXO] ❌ send_realtime: {_e}")
                raise

    async def _listen_audio(self):
        print("[NEXO] 🎤 Mic iniciado")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                nexo_speaking = self._is_speaking
            try:
                rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2))) / 32768.0
            except Exception:
                rms = 0.0

            if not nexo_speaking and not self.ui.muted:
                # Normal mode: visualise + forward audio to session
                self.ui.set_audio_level(min(1.0, rms * 18))
                self._barge_in_frames = 0   # reset counter when not speaking
                data = indata.tobytes()
                # Silently drop if queue is full (during long tool calls)
                def _safe_put(q, item):
                    try:
                        q.put_nowait(item)
                    except Exception:
                        pass  # Queue full — discard; prevents QueueFull crash
                loop.call_soon_threadsafe(
                    _safe_put, self.out_queue, {"data": data, "mime_type": "audio/pcm"}
                )
            elif nexo_speaking:
                # NEXO is speaking: update level + check for barge-in
                self.ui.set_audio_level(min(1.0, rms * 15))
                if (
                    not self.ui.muted
                    and rms > self._BARGE_IN_THRESH
                    and time.monotonic() > self._barge_in_cooldown
                ):
                    self._barge_in_frames += 1
                    if self._barge_in_frames >= self._BARGE_IN_FRAMES:
                        self._barge_in_frames = 0
                        # Trigger barge-in on the event loop (coroutine-safe)
                        asyncio.run_coroutine_threadsafe(
                            self._do_barge_in(), loop
                        )
                else:
                    self._barge_in_frames = 0

        # Read mic device index from config (None = sounddevice default)
        _mic_idx: int | None = None
        try:
            _raw_mic = json.loads(API_CONFIG_PATH.read_text("utf-8")).get("mic_device", None)
            if isinstance(_raw_mic, int) and _raw_mic >= 0:
                _mic_idx = _raw_mic
        except Exception:
            pass

        def _try_open_mic(device_idx):
            return sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                device=device_idx,
                callback=callback,
            )

        mic_stream = None
        if _mic_idx is not None:
            try:
                mic_stream = _try_open_mic(_mic_idx)
            except Exception as _e:
                print(f"[NEXO] ⚠️ Mic device {_mic_idx} no soportado ({_e}). Usando dispositivo por defecto.")
                _mic_idx = None
        if mic_stream is None:
            mic_stream = _try_open_mic(None)   # default mic — let this raise if broken

        try:
            with mic_stream:
                print("[NEXO] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.01)  # 10ms — máxima responsividad del mic
        except Exception as e:
            print(f"[NEXO] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[NEXO] 👂 Recv iniciado")
        out_buf, in_buf = [], []
        _first_chunk   = True
        _last_tool     = None   # track which tool was executing when error hit

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if not self._stop_requested.is_set():
                            try:
                                self.audio_in_queue.put_nowait(response.data)
                            except asyncio.QueueFull:
                                # Queue is saturated (>6s of audio buffered) — drop oldest chunk
                                try:
                                    self.audio_in_queue.get_nowait()
                                    self.audio_in_queue.put_nowait(response.data)
                                except Exception:
                                    pass

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)
                                if _first_chunk:
                                    self.ui.clear_nexo_response()
                                    _first_chunk = False
                                self.ui.stream_nexo_chunk(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            self._stop_requested.clear()
                            if self._turn_done_event:
                                self._turn_done_event.set()
                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"Tú: {full_in}")
                                try:
                                    self._fire_phrase_triggers(full_in)
                                except Exception as _pte:
                                    print(f"[NEXO] phrase trigger error (non-fatal): {_pte}")
                            in_buf = []
                            out_buf = []
                            _first_chunk = True

                    if response.tool_call:
                        self.ui.clear_nexo_response()
                        _first_chunk = True
                        fcs = response.tool_call.function_calls
                        for fc in fcs:
                            print(f"[NEXO] 📞 {fc.name}")
                            _last_tool = fc.name
                        # Execute all tool calls in parallel when there are multiple
                        if len(fcs) > 1:
                            tasks = [asyncio.create_task(self._execute_tool(fc)) for fc in fcs]
                            fn_responses = list(await asyncio.gather(*tasks))
                        else:
                            fn_responses = [await self._execute_tool(fcs[0])]
                        try:
                            await self.session.send_tool_response(
                                function_responses=fn_responses
                            )
                            _last_tool = None  # only clear AFTER successful send
                        except Exception as tool_err:
                            print(f"[NEXO] ❌ send_tool_response failed: {tool_err}")
                            raise
        except Exception as e:
            msg  = str(e)
            code = getattr(e, "status_code", 0) or getattr(e, "code", 0) or 0
            # Detect 1011 (internal server error) regardless of exception type
            if code == 1011 or "1011" in msg or "Internal error" in msg:
                tool_info = f" durante '{_last_tool}'" if _last_tool else ""
                print(f"[NEXO] ⚡ API 1011{tool_info} — reconectando...")
                self._api_1011_tool = _last_tool
            else:
                print(f"[NEXO] ❌ Recv: {e}")
                traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[NEXO] 🔊 Play iniciado")

        # Read speaker device index from config (None = sounddevice default)
        _spk_idx: int | None = None
        try:
            _raw_spk = json.loads(API_CONFIG_PATH.read_text("utf-8")).get("spk_device", None)
            if isinstance(_raw_spk, int) and _raw_spk >= 0:
                _spk_idx = _raw_spk
        except Exception:
            pass

        # Open speaker stream with automatic fallback chain:
        #   1. Configured device  →  2. System default  →  3. Silent mode (no crash)
        def _try_open_speaker(device_idx):
            return sd.RawOutputStream(
                samplerate=RECEIVE_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=PLAY_CHUNK_SIZE,
                device=device_idx,
            )

        stream = None
        if _spk_idx is not None:
            try:
                stream = _try_open_speaker(_spk_idx)
            except Exception as _e:
                print(f"[NEXO] ⚠️ Speaker device {_spk_idx} no soportado ({_e}). Usando dispositivo por defecto.")
                _spk_idx = None
        if stream is None:
            try:
                stream = _try_open_speaker(None)
            except Exception as _e:
                print(f"[NEXO] ⚠️ No se pudo abrir el audio ({_e}). Continuando sin audio.")
                stream = None   # silent-drain mode

        if stream is not None:
            stream.start()

        # Jitter buffer: acumular 2 chunks antes de escribir al speaker
        # 2 chunks × 20ms = 40ms buffer — protege contra underruns sin delay audible
        _jitter_buf:     list[bytes] = []
        _JITTER_TARGET   = 2        # escribir al speaker cada ~40ms (balance latencia/estabilidad)
        _last_chunk_time = 0.0      # para el fallback si turn_done nunca llega
        _SILENT_TIMEOUT  = 3.5      # segundos sin chunks → forzar set_speaking(False)

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.05   # 50ms — tick frecuente para detectar turn_done rápido
                    )
                except asyncio.TimeoutError:
                    now = time.monotonic()

                    # ── Caso normal: turn_done recibido y cola vacía ────────────
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        # Vaciar jitter buffer restante al speaker
                        if _jitter_buf and stream is not None:
                            combined = b"".join(_jitter_buf)
                            await asyncio.to_thread(stream.write, combined)
                        _jitter_buf.clear()
                        # Pequeña pausa para que el buffer de hardware drene
                        # antes de abrir el mic (evita capturar eco de NEXO)
                        await asyncio.sleep(0.18)
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                        _last_chunk_time = 0.0

                    # ── Fallback: API nunca mandó turn_complete ─────────────────
                    elif (
                        self._is_speaking
                        and _last_chunk_time > 0
                        and now - _last_chunk_time > _SILENT_TIMEOUT
                        and self.audio_in_queue.empty()
                    ):
                        print("[NEXO] ⚠️  turn_done no llegó — forzando fin de speaking")
                        if _jitter_buf and stream is not None:
                            combined = b"".join(_jitter_buf)
                            await asyncio.to_thread(stream.write, combined)
                        _jitter_buf.clear()
                        await asyncio.sleep(0.18)
                        self.set_speaking(False)
                        if self._turn_done_event:
                            self._turn_done_event.clear()
                        _last_chunk_time = 0.0

                    continue

                # Nuevo chunk recibido
                self.set_speaking(True)
                _last_chunk_time = time.monotonic()
                _jitter_buf.append(chunk)

                # Escribir al speaker cuando el buffer esté lleno (eficiencia)
                if len(_jitter_buf) >= _JITTER_TARGET:
                    if stream is not None:
                        combined = b"".join(_jitter_buf)
                        await asyncio.to_thread(stream.write, combined)
                    _jitter_buf.clear()

        except Exception as e:
            print(f"[NEXO] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        reconnect_delay   = 1.0
        consecutive_fails = 0

        while True:
            try:
                print("[NEXO] 🔌 Conectando...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self._loop            = asyncio.get_event_loop()
                    self.audio_in_queue   = asyncio.Queue(maxsize=300)  # ~6s at 20ms chunks — prevents unbounded growth
                    self.out_queue        = asyncio.Queue(maxsize=2)   # mínimo buffer → descarta audio viejo, menor latencia
                    self._turn_done_event = asyncio.Event()
                    self._reconnect_event = asyncio.Event()

                    print("[NEXO] ✅ Conectado.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: NEXO en línea.")
                    reconnect_delay   = 1.0   # reset backoff on successful connection
                    consecutive_fails = 0
                    self._api_1011_tool = None   # clear 1011 tool tracker

                    # Wire speak_ref for rules engine so "speak" actions work in session
                    try:
                        import actions.rules_engine as _re
                        _re._speak_ref = self.speak
                    except Exception:
                        pass

                    # ── First-connect extras ──────────────────────────────────
                    if self._first_connect:
                        self._first_connect = False
                        # Start Vision Guardian if enabled
                        try:
                            _start_vision_guardian(
                                inject_fn=self._inject_text,
                                speaking_fn=lambda: self._is_speaking,
                            )
                        except Exception as _vge:
                            print(f"[NEXO] VisionGuardian init error: {_vge}")
                        # Auto morning brief (6am–12pm, once per day)
                        try:
                            _hour = __import__("datetime").datetime.now().hour
                            if 6 <= _hour < 12 and not already_briefed_today():
                                async def _auto_brief():
                                    await asyncio.sleep(3)  # let session settle
                                    await self.session.send_client_content(
                                        turns={"parts": [{"text": "[AUTO] Dame el informe matutino del día."}]},
                                        turn_complete=True
                                    )
                                tg.create_task(_auto_brief())
                        except Exception as _mbr_e:
                            print(f"[NEXO] morning brief init error (non-fatal): {_mbr_e}")
                        # Auto update check (background, silent)
                        def _on_update_found(info: dict):
                            try:
                                self.ui.write_log(
                                    f"SYS: 🔄 Nueva versión disponible: v{info['version']} "
                                    f"(actual: v{info['current']}). Decile a NEXO 'actualizar' para instalarla."
                                )
                                self._inject_text(
                                    f"[SISTEMA] Hay una nueva versión de NEXO disponible: "
                                    f"v{info['version']}. Avisale al usuario de forma breve y natural."
                                )
                            except Exception:
                                pass
                        try:
                            from core.updater import check_in_background
                            check_in_background(_on_update_found)
                        except Exception as _upd_e:
                            print(f"[NEXO] Updater init: {_upd_e}")

                        # Auto-arrancar Ollama si está habilitado ─────────────
                        def _ensure_ollama_running():
                            """Arranca ollama serve en background si no está corriendo."""
                            try:
                                import urllib.request as _ur
                                try:
                                    with _ur.urlopen("http://localhost:11434/api/tags", timeout=2):
                                        print("[Ollama] Servidor ya corriendo")
                                        return  # ya está levantado
                                except Exception:
                                    pass  # no está corriendo → arrancar

                                # Buscar ejecutable de Ollama
                                import shutil as _sh, os as _os
                                _local = _os.environ.get("LOCALAPPDATA", "")
                                _candidates = [
                                    Path(_local) / "Programs" / "Ollama" / "ollama.exe",
                                    Path("C:/Program Files/Ollama/ollama.exe"),
                                    Path("C:/Ollama/ollama.exe"),
                                ]
                                _exe = next((p for p in _candidates if p.exists()), None)
                                if _exe is None:
                                    _w = _sh.which("ollama")
                                    if _w:
                                        _exe = Path(_w)

                                if _exe is None:
                                    print("[Ollama] No instalado — saltando auto-start")
                                    return

                                print(f"[Ollama] Arrancando servidor: {_exe}")
                                import subprocess as _sp
                                _sp.Popen(
                                    [str(_exe), "serve"],
                                    stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
                                    creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0),
                                )
                                import time as _t; _t.sleep(3)

                                # Verificar si hay modelos — si no, pull llama3.2:1b
                                try:
                                    import json as _js
                                    with _ur.urlopen("http://localhost:11434/api/tags", timeout=4) as _r:
                                        _tags = _js.loads(_r.read())
                                    if not _tags.get("models"):
                                        print("[Ollama] Sin modelos — descargando llama3.2:1b en background")
                                        _sp.Popen(
                                            [str(_exe), "pull", "llama3.2:1b"],
                                            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
                                            creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0),
                                        )
                                except Exception as _me:
                                    print(f"[Ollama] Check models error: {_me}")

                            except Exception as _oe:
                                print(f"[Ollama] Auto-start error: {_oe}")

                        try:
                            _cfg_keys = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
                            if _cfg_keys.get("ollama_enabled", False):
                                threading.Thread(
                                    target=_ensure_ollama_running, daemon=True
                                ).start()
                        except Exception as _oll_start_e:
                            print(f"[Ollama] Config read error: {_oll_start_e}")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._watch_reconnect())

            except Exception as e:
                exceptions = e.exceptions if isinstance(e, ExceptionGroup) else [e]

                is_handshake_timeout = False
                is_config_reconnect  = False
                for exc in exceptions:
                    msg = str(exc)
                    if "Config changed" in msg:
                        # Intentional reconnect triggered by config change — fast, no backoff
                        is_config_reconnect = True
                        consecutive_fails = 0
                    elif "timed out during opening handshake" in msg or (
                        isinstance(exc, TimeoutError) and "handshake" in msg
                    ):
                        # Timeout de WebSocket al conectar — error de red transitorio.
                        # NO incrementar consecutive_fails: sólo reintento rápido.
                        is_handshake_timeout = True
                        print(f"[NEXO] ⏱️ Timeout al conectar — reintentando en 1s...")
                    elif "1011" in msg or "Internal error" in msg:
                        tool_hint = self._api_1011_tool or ""
                        print(f"[NEXO] ⚡ API 1011{tool_hint and ' durante '+tool_hint} — reconectando...")
                        consecutive_fails += 1
                        if consecutive_fails >= 4:
                            self.ui.write_log(
                                "SYS: ⚠️ Error 1011 repetido. Esperando para no saturar la API...\n"
                                "SYS: Si persiste más de 2 min, reiniciá NEXO."
                            )
                        elif tool_hint:
                            self.ui.write_log(f"SYS: Error de servidor al ejecutar '{tool_hint}'. Reconectando...")
                        else:
                            self.ui.write_log("SYS: Error de servidor 1011. Reconectando...")
                    elif any(kw in msg.lower() for kw in (
                        "quota", "resource_exhausted", "429", "billing",
                        "too many requests", "rate limit", "free tier"
                    )):
                        # Gemini quota / billing exhausted
                        print(f"[NEXO] ⚠️ Gemini quota/billing error: {msg[:120]}")
                        try:
                            from core.model_router import report_gemini_error, ollama_ok
                            report_gemini_error(msg)
                            if ollama_ok():
                                self.ui.write_log(
                                    "SYS: ⚠️ Límite de Gemini alcanzado — activando modo Ollama local."
                                )
                                print("[NEXO] Switching to Ollama fallback for text tasks.")
                            else:
                                self.ui.write_log(
                                    "SYS: ⚠️ Límite de API de Gemini alcanzado. "
                                    "Configurá Ollama como respaldo o esperá al reset del cupo."
                                )
                        except Exception:
                            pass
                        consecutive_fails += 1
                    elif "1008" in msg or "policy violation" in msg.lower() or "not found for API version" in msg:
                        # Model not available / wrong API version — log clearly, retry with same model
                        print(f"[NEXO] ⚠️ Modelo no disponible en esta versión de API: {msg[:120]}")
                        self.ui.write_log("SYS: ⚠️ Modelo no disponible. Reintentando...")
                        consecutive_fails += 1
                    elif "1000" in msg or "going away" in msg.lower():
                        # Cierre normal de la sesión (expiró ~15 min) — silencioso
                        print(f"[NEXO] 🔄 Sesión expirada — reconectando...")
                        consecutive_fails = 0   # reset: no es un fallo
                    else:
                        print(f"[NEXO] ⚠️ {exc}")
                        traceback.print_exc()
                        consecutive_fails += 1

                if is_config_reconnect:
                    self.set_speaking(False)
                    self.ui.set_state("THINKING")
                    await asyncio.sleep(0.5)
                    continue

                if is_handshake_timeout:
                    # Timeout en handshake → reintento fijo de 1s, sin backoff
                    self.set_speaking(False)
                    self.ui.set_state("THINKING")
                    await asyncio.sleep(1.0)
                    continue

            self.set_speaking(False)
            self.ui.set_state("THINKING")

            # Exponential backoff con jitter para evitar thundering herd
            # After 5+ fails: wait up to 90s to let API rate limits recover
            if consecutive_fails > 1:
                max_delay = 90.0 if consecutive_fails >= 5 else 12.0
                reconnect_delay = min(reconnect_delay * 2, max_delay)
            elif consecutive_fails == 0:
                reconnect_delay = 1.0

            jitter = random.uniform(0, reconnect_delay * 0.25)
            total  = reconnect_delay + jitter
            total  = round(total, 1)
            print(f"[NEXO] 🔄 Reconectando en {total:.1f}s...")

            # Improvement 3: Smart reconnect — countdown visible in UI
            # Show "RECONECTANDO en Xs" and tick down so user isn't confused
            if total >= 3.0:
                self.ui.set_state("INITIATING")
                remaining = int(total)
                while remaining > 0:
                    self.ui.write_log(
                        f"SYS: 🔄 Reconectando en {remaining}s…"
                        if remaining % 5 == 0 or remaining <= 5
                        else ""
                    )
                    await asyncio.sleep(min(1.0, total / remaining if remaining else 1.0))
                    remaining -= 1
                    if remaining <= 0:
                        break
            else:
                await asyncio.sleep(total)

def _show_fatal_error(exc: Exception) -> None:
    """Show a visible MessageBox when NEXO fails to start (pythonw has no console)."""
    import traceback as _tb
    _err_text = _tb.format_exc()
    _crash_log = BASE_DIR / "nexo_crash.log"
    try:
        _crash_log.write_text(
            f"NEXO Crash Report\n{'=' * 60}\n{_err_text}",
            encoding="utf-8"
        )
    except Exception:
        pass
    try:
        import ctypes as _ct
        _ct.windll.user32.MessageBoxW(
            0,
            f"NEXO no pudo iniciarse.\n\nError: {exc!s}\n\n"
            f"Revisa el archivo de log:\n{_crash_log}",
            "NEXO — Error de inicio",
            0x10 | 0x40000,  # MB_ICONERROR | MB_TOPMOST
        )
    except Exception:
        pass


def main():

    # Load timezone from config
    _load_tz()

    # ── Runtime security guardian (anti-debug + integrity check cada 2 min) ──
    try:
        from core.security import start_runtime_guardian, security_check
        security_check(silent=True)          # verificación inicial silenciosa
        start_runtime_guardian(check_interval=120)
    except Exception:
        pass  # no bloquear arranque si security.py no está disponible

    try:
        ui = NexoUI("face.png")
    except Exception as _ui_err:
        _show_fatal_error(_ui_err)
        return

    def runner():
        ui.wait_for_api_key()
        try:
            nexo = NexoLive(ui)
            asyncio.run(nexo.run())
        except KeyboardInterrupt:
            print("\n🔴 Apagando...")
        except Exception as _runner_exc:
            print(f"[NEXO] ❌ Runner thread fatal: {_runner_exc}")
            traceback.print_exc()
            try:
                ui.write_log(f"ERROR CRÍTICO: {_runner_exc}\nReiniciá NEXO.")
            except Exception:
                pass

    threading.Thread(target=runner, daemon=True, name="NexoRunner").start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()