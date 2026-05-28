
from __future__ import annotations

import asyncio
import concurrent.futures
import os
import platform
import shutil
import socket
import subprocess
import threading
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeout,
)
_OS = platform.system()   # "Windows" | "Darwin" | "Linux"

def _normalize_url(url: str) -> str:
    """
    Bare words like "instagram" → "https://instagram.com"
    Domains like "instagram.com" → "https://instagram.com"
    Full URLs pass through unchanged.
    """
    url = url.strip()
    if not url:
        return "about:blank"
    if "://" in url:
        return url
    # No dot at all → assume .com  (e.g. "instagram" → "instagram.com")
    if "." not in url:
        url = url + ".com"
    return "https://" + url


def _user_agent() -> str:
    if _OS == "Windows":
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    if _OS == "Darwin":
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    return (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )


def _load_cfg() -> dict:
    try:
        import json
        p = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _real_profile_dir(browser: str) -> str:
    home  = Path.home()
    local = os.environ.get("LOCALAPPDATA", "")
    roam  = os.environ.get("APPDATA", "")

    candidates: list[Path] = []

    if _OS == "Windows":
        m = {
            "chrome":   [Path(local) / "Google"          / "Chrome"          / "User Data"],
            "edge":     [Path(local) / "Microsoft"        / "Edge"            / "User Data"],
            "brave":    [Path(local) / "BraveSoftware"    / "Brave-Browser"   / "User Data"],
            "vivaldi":  [Path(local) / "Vivaldi"          / "User Data"],
            "opera":    [Path(roam)  / "Opera Software"   / "Opera Stable",
                         Path(local) / "Opera Software"   / "Opera Stable"],
            "operagx":  [Path(roam)  / "Opera Software"   / "Opera GX Stable",
                         Path(local) / "Opera Software"   / "Opera GX Stable"],
        }
        candidates = m.get(browser, [])

    elif _OS == "Darwin":
        lib = home / "Library" / "Application Support"
        m = {
            "chrome":   [lib / "Google"             / "Chrome"],
            "edge":     [lib / "Microsoft Edge"],
            "brave":    [lib / "BraveSoftware"       / "Brave-Browser"],
            "vivaldi":  [lib / "Vivaldi"],
            "opera":    [lib / "com.operasoftware.Opera"],
            "operagx":  [lib / "com.operasoftware.OperaGX"],
        }
        candidates = m.get(browser, [])

    elif _OS == "Linux":
        cfg = home / ".config"
        m = {
            "chrome":   [cfg / "google-chrome", cfg / "chromium"],
            "edge":     [cfg / "microsoft-edge"],
            "brave":    [cfg / "BraveSoftware" / "Brave-Browser"],
            "vivaldi":  [cfg / "vivaldi"],
            "opera":    [cfg / "opera"],
            "operagx":  [cfg / "opera-gx"],
        }
        candidates = m.get(browser, [])

    for p in candidates:
        if p.exists():
            print(f"[Browser] ✅ Real profile found for {browser}: {p}")
            return str(p)

    fallback = home / ".nexo_profiles" / browser
    fallback.mkdir(parents=True, exist_ok=True)
    print(f"[Browser] ⚠️  Real profile not found for {browser}, using: {fallback}")
    return str(fallback)

def _firefox_profile_dir() -> Optional[str]:
    home = Path.home()

    if _OS == "Windows":
        base = Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox"
    elif _OS == "Darwin":
        base = home / "Library" / "Application Support" / "Firefox"
    else:
        base = home / ".mozilla" / "firefox"

    ini = base / "profiles.ini"
    if not ini.exists():
        return None

    current: dict[str, str] = {}
    default_path: Optional[str] = None

    for line in ini.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("["):
            p = current.get("Path", "")
            if p and current.get("Default") == "1":
                is_rel = current.get("IsRelative", "1") == "1"
                default_path = str(base / p) if is_rel else p
            current = {}
        elif "=" in line:
            k, _, v = line.partition("=")
            current[k.strip()] = v.strip()

    p = current.get("Path", "")
    if p and current.get("Default") == "1":
        is_rel = current.get("IsRelative", "1") == "1"
        default_path = str(base / p) if is_rel else p

    if default_path and Path(default_path).exists():
        print(f"[Browser] Firefox real profile: {default_path}")
        return default_path
    return None

def _find_opera_windows() -> Optional[str]:
    local  = os.environ.get("LOCALAPPDATA", "")
    prog   = os.environ.get("PROGRAMFILES", "")
    prog86 = os.environ.get("PROGRAMFILES(X86)", "")

    candidates = [
        Path(local)  / "Programs" / "Opera"    / "opera.exe",
        Path(local)  / "Programs" / "Opera GX" / "opera.exe",
        Path(prog)   / "Opera"    / "opera.exe",
        Path(prog86) / "Opera"    / "opera.exe",
    ]
    for p in candidates:
        if p.exists():
            print(f"[Browser] Opera found at: {p}")
            return str(p)

    try:
        import winreg
        keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\opera.exe",
            r"SOFTWARE\Clients\StartMenuInternet\OperaStable\shell\open\command",
            r"SOFTWARE\Clients\StartMenuInternet\OperaGXStable\shell\open\command",
            r"SOFTWARE\Clients\StartMenuInternet\opera\shell\open\command",
        ]
        for key_path in keys:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k   = winreg.OpenKey(hive, key_path)
                    val = winreg.QueryValue(k, None)
                    winreg.CloseKey(k)
                    exe = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                    if exe and Path(exe).exists():
                        print(f"[Browser] Opera found via registry: {exe}")
                        return exe
                except Exception:
                    continue
    except Exception:
        pass

    return shutil.which("opera") or None

def _find_exe_windows(prog_name: str) -> Optional[str]:
    try:
        import winreg
        paths_to_try = [
            rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{prog_name}.exe",
            rf"SOFTWARE\Clients\StartMenuInternet\{prog_name}\shell\open\command",
        ]
        for key_path in paths_to_try:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k   = winreg.OpenKey(hive, key_path)
                    val = winreg.QueryValue(k, None)
                    winreg.CloseKey(k)
                    exe = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                    if exe and Path(exe).exists():
                        return exe
                except Exception:
                    continue
    except Exception:
        pass
    return None

_BROWSER_SPECS: dict[str, dict] = {
    "Windows": {
        "chrome":   {"engine": "chromium", "channel": "chrome",  "bins": []},
        "edge":     {"engine": "chromium", "channel": "msedge",  "bins": []},
        "firefox":  {"engine": "firefox",  "channel": None,      "bins": ["firefox.exe"]},
        "opera":    {"engine": "chromium", "channel": None,      "bins": ["opera.exe"],  "special": "opera_windows"},
        "operagx":  {"engine": "chromium", "channel": None,      "bins": [],             "special": "opera_windows"},
        "brave":    {"engine": "chromium", "channel": None,      "bins": ["brave.exe"]},
        "vivaldi":  {"engine": "chromium", "channel": None,      "bins": ["vivaldi.exe"]},
        "safari":   None,
    },
    "Darwin": {
        "chrome":   {"engine": "chromium", "channel": "chrome",  "bins": []},
        "edge":     {"engine": "chromium", "channel": "msedge",  "bins": ["microsoft-edge"]},
        "firefox":  {"engine": "firefox",  "channel": None,      "bins": ["firefox"]},
        "opera":    {"engine": "chromium", "channel": None,      "bins": ["opera"]},
        "operagx":  {"engine": "chromium", "channel": None,      "bins": ["opera"]},
        "brave":    {"engine": "chromium", "channel": None,      "bins": ["brave browser", "brave"]},
        "vivaldi":  {"engine": "chromium", "channel": None,      "bins": ["vivaldi"]},
        "safari":   {"engine": "webkit",   "channel": None,      "bins": []},
    },
    "Linux": {
        "chrome":   {"engine": "chromium", "channel": None,
                     "bins": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"]},
        "edge":     {"engine": "chromium", "channel": None,
                     "bins": ["microsoft-edge", "microsoft-edge-stable"]},
        "firefox":  {"engine": "firefox",  "channel": None, "bins": ["firefox"]},
        "opera":    {"engine": "chromium", "channel": None, "bins": ["opera", "opera-stable"]},
        "operagx":  {"engine": "chromium", "channel": None, "bins": ["opera", "opera-stable"]},
        "brave":    {"engine": "chromium", "channel": None, "bins": ["brave-browser", "brave"]},
        "vivaldi":  {"engine": "chromium", "channel": None, "bins": ["vivaldi-stable", "vivaldi"]},
        "safari":   None,
    },
}

_ALIASES: dict[str, str] = {
    "google chrome":   "chrome",
    "google-chrome":   "chrome",
    "microsoft edge":  "edge",
    "ms edge":         "edge",
    "msedge":          "edge",
    "mozilla firefox": "firefox",
    "opera gx":        "operagx",
    "opera_gx":        "operagx",
}


_CHROME_EXE_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

def _find_chrome_exe() -> Optional[str]:
    """Find Chrome exe — checks config override first, then known paths."""
    cfg = _load_cfg()
    override = cfg.get("chrome_exe_path", "")
    if override and Path(override).exists():
        return override
    for c in _CHROME_EXE_CANDIDATES:
        if Path(c).exists():
            return c
    local = os.environ.get("LOCALAPPDATA", "")
    candidate = Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe"
    if candidate.exists():
        return str(candidate)
    return shutil.which("chrome") or shutil.which("google-chrome")

def _resolve_browser(name: str) -> dict | None:
    name   = _ALIASES.get(name.lower().strip(), name.lower().strip())
    os_map = _BROWSER_SPECS.get(_OS, {})
    spec   = os_map.get(name)
    if spec is None:
        return None

    engine  = spec["engine"]
    channel = spec.get("channel")
    bins    = spec.get("bins", [])
    exe     = None

    if spec.get("special") == "opera_windows":
        exe = _find_opera_windows()
        if not exe:
            print(f"[Browser] ⚠️  Opera executable not found on Windows.")
        return {"engine": engine, "exe": exe, "channel": channel}

    for b in bins:
        found = shutil.which(b)
        if found:
            exe = found
            break

    if not exe and _OS == "Darwin":
        app_names = {
            "chrome":  ["Google Chrome.app"],
            "edge":    ["Microsoft Edge.app"],
            "firefox": ["Firefox.app"],
            "opera":   ["Opera.app", "Opera GX.app"],
            "brave":   ["Brave Browser.app"],
            "vivaldi": ["Vivaldi.app"],
        }
        for app in app_names.get(name, []):
            app_dir = Path("/Applications") / app / "Contents" / "MacOS"
            if app_dir.exists():
                found_bins = list(app_dir.iterdir())
                if found_bins:
                    exe = str(found_bins[0])
                    break

    if not exe and _OS == "Windows" and not channel:
        if name == "chrome":
            exe = _find_chrome_exe()
        else:
            exe = _find_exe_windows(name)

    # For Chrome on Windows, prefer direct exe over channel to ensure
    # the correct installation is used
    if name == "chrome" and _OS == "Windows":
        chrome_exe = _find_chrome_exe()
        if chrome_exe:
            exe     = chrome_exe
            channel = None   # exe takes priority over channel

    return {"engine": engine, "exe": exe, "channel": channel}


def _detect_default_browser() -> str:
    try:
        if _OS == "Windows":
            import winreg
            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations"
                r"\UrlAssociations\http\UserChoice",
            )
            prog_id = winreg.QueryValueEx(k, "ProgId")[0].lower()
            winreg.CloseKey(k)
            for kw in ("edge", "firefox", "opera", "brave", "vivaldi", "chrome"):
                if kw in prog_id:
                    return kw
        elif _OS == "Darwin":
            out = subprocess.run(
                ["defaults", "read",
                 "com.apple.LaunchServices/com.apple.launchservices.secure",
                 "LSHandlers"],
                capture_output=True, text=True, timeout=5,
            ).stdout.lower()
            for kw in ("firefox", "opera", "brave", "vivaldi", "safari", "chrome", "edge"):
                if kw in out:
                    return kw
        elif _OS == "Linux":
            out = subprocess.run(
                ["xdg-settings", "get", "default-web-browser"],
                capture_output=True, text=True, timeout=5,
            ).stdout.lower()
            for kw in ("firefox", "opera", "brave", "vivaldi", "chrome", "edge"):
                if kw in out:
                    return kw
    except Exception:
        pass
    return "chrome"


_CDP_PORT = 9222   # Remote debugging port used for Chrome CDP connection


def _is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is open (Chrome debugging port)."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except Exception:
        return False


class _BrowserSession:
    """
    Browser session. Chrome uses CDP (connect_over_cdp) to attach to the
    user's real Chrome window — no automation banner, no blank tab.
    Other browsers use launch_persistent_context as before.
    """

    def __init__(self, browser_name: str):
        self.browser_name = browser_name
        self._spec        = _resolve_browser(browser_name)

        self._loop:    asyncio.AbstractEventLoop | None = None
        self._thread:  threading.Thread | None          = None
        self._ready    = threading.Event()

        self._pw:         Playwright     | None = None
        self._context:    BrowserContext | None = None
        self._page:       Page           | None = None
        self._cdp_browser                       = None  # only for CDP sessions
        self._chrome_proc: subprocess.Popen | None = None  # launched Chrome process

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name=f"BrowserThread-{self.browser_name}",
        )
        self._thread.start()
        self._ready.wait(timeout=20)

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_init())
        self._ready.set()
        self._loop.run_forever()

    async def _async_init(self):
        self._pw = await async_playwright().start()

    def run(self, coro, timeout: int = 60) -> str:
        if not self._loop:
            raise RuntimeError(f"Session for '{self.browser_name}' not started.")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def close(self):
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._async_close(), self._loop).result(10)

    async def _async_close(self):
        if self._cdp_browser:
            try:
                await self._cdp_browser.close()
            except Exception:
                pass
            self._cdp_browser = None
        elif self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._context = self._page = None
        # Terminate the Chrome process we launched (if any)
        if self._chrome_proc and self._chrome_proc.poll() is None:
            try:
                self._chrome_proc.terminate()
            except Exception:
                pass
            self._chrome_proc = None

    # ── CDP helpers (Chrome) ──────────────────────────────────────────────────

    async def _cdp_connect(self) -> bool:
        """Try to connect to Chrome via CDP. Returns True on success."""
        try:
            browser = await self._pw.chromium.connect_over_cdp(
                f"http://127.0.0.1:{_CDP_PORT}",   # IPv4 — localhost can resolve to ::1
                timeout=6_000,
            )
            self._cdp_browser = browser
            contexts = browser.contexts
            self._context = contexts[0] if contexts else await browser.new_context()
            # Try to pick the most recently used page as active
            pages = [p for p in self._context.pages if not p.is_closed()]
            self._page = pages[-1] if pages else None
            print(f"[Browser] ✅ Connected to Chrome via CDP (port {_CDP_PORT})")
            return True
        except Exception as e:
            print(f"[Browser] CDP connect failed: {e}")
            return False

    async def _launch_chrome_cdp(self, exe: str):
        """
        Attach to or launch a Chrome instance with --remote-debugging-port.
        Uses a NEXO-dedicated user-data-dir to avoid profile lock conflicts.
        """
        # 1. Port already open → try connecting (may be a previous NEXO Chrome)
        if _is_port_open(_CDP_PORT):
            if await self._cdp_connect():
                return
            # Port open but connect failed — kill whatever is using it and retry
            print(f"[Browser] Port {_CDP_PORT} open but CDP failed — killing old process")
            if self._chrome_proc and self._chrome_proc.poll() is None:
                self._chrome_proc.terminate()
                self._chrome_proc = None
            # Wait briefly for port to free
            for _ in range(5):
                await asyncio.sleep(0.5)
                if not _is_port_open(_CDP_PORT):
                    break

        # 2. Launch fresh Chrome with the debugging port
        nexo_dir = str(Path.home() / ".nexo_profiles" / "chrome_cdp")
        Path(nexo_dir).mkdir(parents=True, exist_ok=True)

        print(f"[Browser] Launching Chrome with --remote-debugging-port={_CDP_PORT}...")
        self._chrome_proc = subprocess.Popen([
            exe,
            f"--remote-debugging-port={_CDP_PORT}",
            f"--user-data-dir={nexo_dir}",
            "--no-first-run",
            "--disable-default-apps",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-sync",
            "--start-maximized",
        ])

        # 3. Wait up to 20s for the debugging port to become available
        for _ in range(40):
            await asyncio.sleep(0.5)
            if _is_port_open(_CDP_PORT):
                break
        else:
            raise RuntimeError("Chrome did not open the debugging port in time.")

        # Give Chrome a moment to initialize its DevTools server
        await asyncio.sleep(0.5)

        # 4. Connect via CDP (retry 5× with backoff)
        for attempt in range(5):
            if await self._cdp_connect():
                return
            await asyncio.sleep(0.8)

        raise RuntimeError("Could not connect to Chrome via CDP after launching.")

    # ── main launch ───────────────────────────────────────────────────────────

    async def _launch(self):
        """
        Attach to browser. Chrome uses CDP (real window, no automation banner).
        Other browsers use launch_persistent_context.
        """
        # Liveness check
        if self._context is not None:
            try:
                _ = len(self._context.pages)
            except Exception:
                print(f"[Browser] ⚠️  Context died — resetting {self.browser_name}")
                self._context = None
                self._page = None
                self._cdp_browser = None
        if self._context is not None:
            return

        if self._spec is None:
            raise RuntimeError(
                f"'{self.browser_name}' not supported on {_OS}."
            )

        engine_name = self._spec["engine"]
        exe         = self._spec["exe"]
        channel     = self._spec["channel"]
        engine_obj  = getattr(self._pw, engine_name)

        # ── Firefox ───────────────────────────────────────────────────────────
        if engine_name == "firefox":
            profile = _firefox_profile_dir() or str(
                Path.home() / ".nexo_profiles" / "firefox"
            )
            kwargs: dict = {
                "headless":    False,
                "slow_mo":     0,
                "viewport":    None,
                "no_viewport": True,
            }
            if exe:
                kwargs["executable_path"] = exe
            try:
                self._context = await engine_obj.launch_persistent_context(profile, **kwargs)
            except Exception as e:
                print(f"[Browser] Firefox real profile failed ({e}), using NEXO profile")
                nexo = str(Path.home() / ".nexo_profiles" / "firefox_nexo")
                Path(nexo).mkdir(parents=True, exist_ok=True)
                self._context = await engine_obj.launch_persistent_context(nexo, **kwargs)
            await asyncio.sleep(0.5)
            self._page = await self._context.new_page()
            print(f"[Browser] ✅ Firefox launched")
            return

        # ── WebKit / Safari ───────────────────────────────────────────────────
        if engine_name == "webkit":
            safari_profile = str(Path.home() / ".nexo_profiles" / "safari")
            Path(safari_profile).mkdir(parents=True, exist_ok=True)
            kwargs = {
                "headless":    False,
                "slow_mo":     0,
                "viewport":    None,
                "no_viewport": True,
            }
            self._context = await engine_obj.launch_persistent_context(safari_profile, **kwargs)
            await asyncio.sleep(0.5)
            self._page = await self._context.new_page()
            print(f"[Browser] ✅ Safari launched")
            return

        # ── Chromium-based (Chrome via CDP, others via persistent context) ────
        cfg              = _load_cfg()
        profile_dir_name = cfg.get("chrome_google_profile", "Default")

        # Chrome on Windows → use CDP with a NEXO-dedicated profile
        if self.browser_name == "chrome" and _OS == "Windows" and exe:
            await self._launch_chrome_cdp(exe)
            return

        # All other Chromium browsers → launch_persistent_context
        profile = _real_profile_dir(self.browser_name)
        base_args = [
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--disable-default-apps",
            "--no-default-browser-check",
            f"--profile-directory={profile_dir_name}",
        ]
        kwargs = {
            "headless":    False,
            "slow_mo":     0,
            "viewport":    None,
            "no_viewport": True,
            "args":        base_args,
        }
        if exe:
            kwargs["executable_path"] = exe
        elif channel:
            kwargs["channel"] = channel

        label = f"{self.browser_name}" + (f" @ {exe}" if exe else "")
        try:
            self._context = await engine_obj.launch_persistent_context(profile, **kwargs)
            await asyncio.sleep(0.5)
            self._page = await self._context.new_page()
            print(f"[Browser] ✅ Launched [{label}]")
            return
        except Exception as e:
            print(f"[Browser] ⚠️  Profile launch failed for {label}: {e}")

        nexo_profile = str(Path.home() / ".nexo_profiles" / self.browser_name)
        Path(nexo_profile).mkdir(parents=True, exist_ok=True)
        self._context = await engine_obj.launch_persistent_context(nexo_profile, **kwargs)
        await asyncio.sleep(0.5)
        self._page = await self._context.new_page()
        print(f"[Browser] ✅ Launched [{label}] with NEXO profile")


    async def _get_page(self) -> Page:
        await self._launch()
        try:
            # For CDP sessions: prefer the currently active/focused page
            if self._cdp_browser and self._context:
                pages = [p for p in self._context.pages if not p.is_closed()]
                if pages:
                    # Re-use the last page we interacted with, or the most recent
                    if self._page and not self._page.is_closed() and self._page in pages:
                        return self._page
                    self._page = pages[-1]
                    return self._page
                # No open pages → open a new tab
                self._page = await self._context.new_page()
                return self._page

            # Non-CDP: standard page handling
            if self._page is None or self._page.is_closed():
                self._page = await self._context.new_page()
                await asyncio.sleep(0.2)
            return self._page

        except Exception as e:
            print(f"[Browser] ⚠️  Page/context error ({e}) — full reset")
            self._context     = None
            self._page        = None
            self._cdp_browser = None
            await self._launch()
            if self._cdp_browser and self._context:
                pages = [p for p in self._context.pages if not p.is_closed()]
                self._page = pages[-1] if pages else await self._context.new_page()
            else:
                self._page = await self._context.new_page()
                await asyncio.sleep(0.2)
            return self._page

    async def go_to(self, url: str) -> str:
        url = _normalize_url(url)
        await self._launch()

        async def _do_goto(p: Page) -> str:
            try:
                await p.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(0.3)
            except PlaywrightTimeout:
                pass
            except Exception as e:
                print(f"[Browser] goto exception (non-fatal): {e}")
            return p.url

        # For CDP: always open a new tab so we never overwrite an existing page
        if self._cdp_browser and self._context:
            try:
                new_page   = await self._context.new_page()
                self._page = new_page
                result_url = await _do_goto(new_page)
                if result_url and result_url not in ("about:blank", "", None):
                    return f"Opened: {result_url}"
                return f"Could not open: {url}"
            except Exception as e:
                print(f"[Browser] CDP go_to error: {e}")
                return f"Error opening {url}: {e}"

        # Non-CDP: navigate in current page, fall back to new tab if blank
        page     = await self._get_page()
        prev_url = page.url
        result_url = await _do_goto(page)

        if result_url in ("about:blank", "", None, prev_url) and prev_url in ("about:blank", "", None):
            try:
                new_page   = await self._context.new_page()
                self._page = new_page
                result_url = await _do_goto(new_page)
            except Exception as e:
                print(f"[Browser] New-tab retry failed: {e}")

        if result_url and result_url not in ("about:blank", "", None):
            return f"Opened: {result_url}"
        return f"Could not open: {url}"

    async def search(self, query: str, engine: str = "google") -> str:
        _engines = {
            "google":     "https://www.google.com/search?q=",
            "bing":       "https://www.bing.com/search?q=",
            "duckduckgo": "https://duckduckgo.com/?q=",
            "yandex":     "https://yandex.com/search/?text=",
        }
        base = _engines.get(engine.lower(), _engines["google"])
        return await self.go_to(base + query.replace(" ", "+"))

    async def click(self, selector: str = None, text: str = None) -> str:
        page = await self._get_page()
        try:
            if text:
                await page.get_by_text(text, exact=False).first.click(timeout=8_000)
                return f"Clicked text: '{text}'"
            if selector:
                await page.click(selector, timeout=8_000)
                return f"Clicked selector: {selector}"
            return "No selector or text provided."
        except PlaywrightTimeout:
            return "Element not found (timeout)."
        except Exception as e:
            return f"Click error: {e}"

    async def type_text(self, selector: str = None, text: str = "",
                        clear_first: bool = True) -> str:
        page = await self._get_page()
        try:
            el = page.locator(selector).first if selector else page.locator(":focus")
            if clear_first:
                await el.clear()
            await el.type(text, delay=50)
            return "Text typed."
        except Exception as e:
            return f"Type error: {e}"

    async def scroll(self, direction: str = "down", amount: int = 500) -> str:
        page = await self._get_page()
        try:
            y = amount if direction == "down" else -amount
            # JS scroll is more reliable across CDP and non-CDP sessions
            await page.evaluate(f"window.scrollBy({{top: {y}, left: 0, behavior: 'smooth'}})")
            return f"Scrolled {direction} by {amount}px."
        except Exception:
            try:
                await page.mouse.wheel(0, amount if direction == "down" else -amount)
                return f"Scrolled {direction}."
            except Exception as e:
                return f"Scroll error: {e}"

    async def scroll_element(self, selector: str, direction: str = "down", amount: int = 300) -> str:
        page = await self._get_page()
        try:
            y = amount if direction == "down" else -amount
            await page.evaluate(
                f"document.querySelector('{selector}')?.scrollBy({{top: {y}, behavior: 'smooth'}})"
            )
            return f"Scrolled element '{selector}' {direction}."
        except Exception as e:
            return f"Scroll element error: {e}"

    async def press(self, key: str) -> str:
        page = await self._get_page()
        try:
            await page.keyboard.press(key)
            return f"Pressed: {key}"
        except Exception as e:
            return f"Key error: {e}"

    async def get_text(self) -> str:
        page = await self._get_page()
        try:
            text = await page.inner_text("body")
            return text[:4_000]
        except Exception as e:
            return f"Could not get page text: {e}"

    async def get_url(self) -> str:
        page = await self._get_page()
        return page.url

    async def fill_form(self, fields: dict) -> str:
        page    = await self._get_page()
        results = []
        for selector, value in fields.items():
            try:
                el = page.locator(selector).first
                await el.clear()
                await el.type(str(value), delay=40)
                results.append(f"✓ {selector}")
            except Exception as e:
                results.append(f"✗ {selector}: {e}")
        return "Form filled: " + ", ".join(results)

    async def smart_click(self, description: str) -> str:
        page = await self._get_page()
        for role in ("button", "link", "searchbox", "textbox", "menuitem", "tab"):
            try:
                loc = page.get_by_role(role, name=description)
                if await loc.count() > 0:
                    await loc.first.click(timeout=5_000)
                    return f"Clicked ({role}): '{description}'"
            except Exception:
                pass
        for attempt in (
            lambda: page.get_by_text(description, exact=False).first.click(timeout=5_000),
            lambda: page.get_by_placeholder(description, exact=False).first.click(timeout=5_000),
            lambda: page.locator(
                f'[alt*="{description}" i],[title*="{description}" i],'
                f'[aria-label*="{description}" i]'
            ).first.click(timeout=5_000),
        ):
            try:
                await attempt()
                return f"Clicked: '{description}'"
            except Exception:
                pass
        return f"Could not find element: '{description}'"

    async def smart_type(self, description: str, text: str) -> str:
        page = await self._get_page()
        candidates = [
            ("placeholder", page.get_by_placeholder(description, exact=False)),
            ("label",       page.get_by_label(description, exact=False)),
            ("role",        page.get_by_role("textbox", name=description)),
            ("searchbox",   page.get_by_role("searchbox")),
            ("combobox",    page.get_by_role("combobox", name=description)),
        ]
        for method, loc in candidates:
            try:
                el = loc.first
                if await el.count() == 0:
                    continue
                await el.clear()
                await el.type(text, delay=50)
                return f"Typed into ({method}): '{description}'"
            except Exception:
                continue
        return f"Could not find input: '{description}'"

    async def new_tab(self, url: str = "") -> str:
        page = await self._get_page()
        ctx  = page.context
        new  = await ctx.new_page()
        self._page = new
        if url:
            return await self.go_to(url)
        return "New tab opened."

    async def close_tab(self) -> str:
        page = self._page
        if page and not page.is_closed():
            ctx   = page.context
            await page.close()
            pages = ctx.pages
            self._page = pages[-1] if pages else None
            return "Tab closed."
        return "No active tab to close."

    async def screenshot(self, path: str = None) -> str:
        page = await self._get_page()
        try:
            save_path = path or str(Path.home() / "Desktop" / "nexo_screenshot.png")
            await page.screenshot(path=save_path, full_page=False)
            return f"Screenshot saved: {save_path}"
        except Exception as e:
            return f"Screenshot error: {e}"

    async def back(self) -> str:
        page = await self._get_page()
        try:
            await page.go_back(timeout=10_000)
            return f"Navigated back: {page.url}"
        except Exception as e:
            return f"Back error: {e}"

    async def forward(self) -> str:
        page = await self._get_page()
        try:
            await page.go_forward(timeout=10_000)
            return f"Navigated forward: {page.url}"
        except Exception as e:
            return f"Forward error: {e}"

    async def reload(self) -> str:
        page = await self._get_page()
        try:
            await page.reload(timeout=15_000)
            return f"Page reloaded: {page.url}"
        except Exception as e:
            return f"Reload error: {e}"

    async def get_title(self) -> str:
        page = await self._get_page()
        try:
            return f"Page title: {page.title()}"
        except Exception as e:
            return f"Title error: {e}"

    async def hover(self, selector: str = None, text: str = None) -> str:
        page = await self._get_page()
        try:
            if text:
                await page.get_by_text(text, exact=False).first.hover(timeout=6_000)
                return f"Hovered text: '{text}'"
            if selector:
                await page.hover(selector, timeout=6_000)
                return f"Hovered: {selector}"
            return "No selector or text provided."
        except Exception as e:
            return f"Hover error: {e}"

    async def select_option(self, selector: str, value: str) -> str:
        page = await self._get_page()
        try:
            await page.select_option(selector, value=value, timeout=6_000)
            return f"Selected '{value}' in {selector}."
        except Exception as e:
            # Try by label
            try:
                await page.select_option(selector, label=value, timeout=6_000)
                return f"Selected label '{value}' in {selector}."
            except Exception:
                return f"Select error: {e}"

    async def wait_for_selector(self, selector: str, timeout: int = 10_000) -> str:
        page = await self._get_page()
        try:
            await page.wait_for_selector(selector, timeout=timeout)
            return f"Element appeared: {selector}"
        except Exception as e:
            return f"Wait timeout: {e}"

    async def execute_js(self, script: str) -> str:
        page = await self._get_page()
        try:
            result = await page.evaluate(script)
            return f"JS result: {str(result)[:500]}"
        except Exception as e:
            return f"JS error: {e}"

    async def find_all(self, selector: str) -> str:
        page = await self._get_page()
        try:
            elements = await page.locator(selector).all()
            texts = []
            for el in elements[:10]:
                try:
                    t = await el.inner_text()
                    texts.append(t.strip()[:60])
                except Exception:
                    texts.append("[no text]")
            return f"Found {len(elements)} elements: " + " | ".join(texts)
        except Exception as e:
            return f"Find all error: {e}"

    async def get_page_info(self) -> str:
        page = await self._get_page()
        try:
            url   = page.url
            title = await page.title()
            body  = (await page.inner_text("body"))[:300]
            return f"URL: {url}\nTitle: {title}\nContent preview: {body}"
        except Exception as e:
            return f"Page info error: {e}"

    async def focus_element(self, selector: str) -> str:
        page = await self._get_page()
        try:
            await page.focus(selector, timeout=6_000)
            return f"Focused: {selector}"
        except Exception as e:
            return f"Focus error: {e}"

    async def copy_text(self) -> str:
        page = await self._get_page()
        try:
            await page.keyboard.press("Control+a")
            await asyncio.sleep(0.1)
            await page.keyboard.press("Control+c")
            return "Content copied to clipboard."
        except Exception as e:
            return f"Copy error: {e}"

    async def zoom(self, level: float = 1.0) -> str:
        page = await self._get_page()
        try:
            await page.evaluate(f"document.body.style.zoom = '{level}'")
            return f"Zoom set to {level:.0%}."
        except Exception as e:
            return f"Zoom error: {e}"

    async def submit_form(self, selector: str = "form") -> str:
        page = await self._get_page()
        try:
            await page.locator(selector).first.evaluate("el => el.submit()")
            return "Form submitted."
        except Exception:
            try:
                await page.keyboard.press("Enter")
                return "Form submitted via Enter."
            except Exception as e:
                return f"Submit error: {e}"

    async def get_links(self) -> str:
        page = await self._get_page()
        try:
            links = await page.evaluate("""
                Array.from(document.querySelectorAll('a[href]'))
                  .slice(0, 15)
                  .map(a => a.href + ' — ' + (a.innerText || '').trim().slice(0, 40))
            """)
            return "Links:\n" + "\n".join(links)
        except Exception as e:
            return f"Get links error: {e}"

    async def download_screenshot(self, path: str = None) -> str:
        return await self.screenshot(path)

    # ── Cookies ───────────────────────────────────────────────────────────────

    async def get_cookies(self, url: str = None) -> str:
        await self._launch()
        try:
            ctx = self._context
            if url:
                cookies = await ctx.cookies([url])
            else:
                page = await self._get_page()
                cookies = await ctx.cookies([page.url])
            if not cookies:
                return "No cookies found for the current page."
            lines = [f"{c['name']}={c['value'][:40]} (domain:{c.get('domain','')})"
                     for c in cookies[:20]]
            return f"Cookies ({len(cookies)} total):\n" + "\n".join(lines)
        except Exception as e:
            return f"Get cookies error: {e}"

    async def clear_cookies(self, url: str = None) -> str:
        await self._launch()
        try:
            ctx = self._context
            if url:
                await ctx.clear_cookies(domain=None)  # clear all; filtering by url not directly supported
            else:
                await ctx.clear_cookies()
            return "Cookies cleared."
        except Exception as e:
            return f"Clear cookies error: {e}"

    async def set_cookie(self, name: str, value: str, domain: str = None, path: str = "/") -> str:
        await self._launch()
        try:
            page = await self._get_page()
            ctx  = self._context
            parsed_domain = domain
            if not parsed_domain:
                import urllib.parse
                parsed_domain = urllib.parse.urlparse(page.url).hostname or "localhost"
            await ctx.add_cookies([{
                "name": name, "value": value,
                "domain": parsed_domain, "path": path,
            }])
            return f"Cookie set: {name}={value} on {parsed_domain}"
        except Exception as e:
            return f"Set cookie error: {e}"

    # ── Local Storage ─────────────────────────────────────────────────────────

    async def get_local_storage(self, key: str = None) -> str:
        page = await self._get_page()
        try:
            if key:
                val = await page.evaluate(f"localStorage.getItem({repr(key)})")
                return f"localStorage[{key}] = {val}"
            data = await page.evaluate("""
                (() => {
                    const out = {};
                    for (let i = 0; i < localStorage.length; i++) {
                        const k = localStorage.key(i);
                        out[k] = localStorage.getItem(k);
                    }
                    return out;
                })()
            """)
            if not data:
                return "localStorage is empty."
            lines = [f"{k}: {str(v)[:60]}" for k, v in list(data.items())[:20]]
            return f"localStorage ({len(data)} keys):\n" + "\n".join(lines)
        except Exception as e:
            return f"LocalStorage error: {e}"

    async def set_local_storage(self, key: str, value: str) -> str:
        page = await self._get_page()
        try:
            await page.evaluate(f"localStorage.setItem({repr(key)}, {repr(value)})")
            return f"localStorage[{key}] set."
        except Exception as e:
            return f"Set localStorage error: {e}"

    # ── File Download ─────────────────────────────────────────────────────────

    async def download_file(self, url: str, save_path: str = None) -> str:
        page = await self._get_page()
        try:
            url = _normalize_url(url)
            dest = save_path or str(Path.home() / "Downloads")
            async with page.expect_download(timeout=60_000) as dl_info:
                await page.evaluate(f"""
                    (() => {{
                        const a = document.createElement('a');
                        a.href = {repr(url)};
                        a.download = '';
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                    }})()
                """)
            download = await dl_info.value
            if save_path:
                await download.save_as(save_path)
                return f"Downloaded to: {save_path}"
            else:
                name = download.suggested_filename
                full = str(Path(dest) / name)
                await download.save_as(full)
                return f"Downloaded: {full}"
        except Exception as e:
            return f"Download error: {e}"

    # ── History & Bookmarks ───────────────────────────────────────────────────

    async def get_history(self, limit: int = 20) -> str:
        """Get browser history from current CDP session (Chrome only)."""
        page = await self._get_page()
        try:
            # Works on Chrome/Chromium via CDP session
            client = await page.context.new_cdp_session(page)
            result = await client.send("History.getEntries", {})
            entries = result.get("entries", [])[-limit:]
            if not entries:
                return "No history entries found (CDP session required)."
            lines = [f"{e.get('url','')[:80]} — {e.get('title','')[:40]}" for e in reversed(entries)]
            return f"Recent history ({len(entries)} entries):\n" + "\n".join(lines)
        except Exception:
            # Fallback: use page.evaluate to read current session history
            try:
                hist = await page.evaluate("""
                    (() => {
                        const items = [];
                        for (let i = 0; i < Math.min(window.history.length, 20); i++) {
                            items.push(document.referrer || window.location.href);
                        }
                        return items;
                    })()
                """)
                return f"Session history: {hist}"
            except Exception as e2:
                return f"History not accessible: {e2}"

    async def get_bookmarks(self) -> str:
        """Read Chrome bookmarks from the profile file."""
        try:
            cfg = _load_cfg()
            profile = cfg.get("chrome_google_profile", "Default")
            local = os.environ.get("LOCALAPPDATA", "")
            bm_file = Path(local) / "Google" / "Chrome" / "User Data" / profile / "Bookmarks"
            if not bm_file.exists():
                return "Bookmarks file not found (Chrome profile may differ)."
            import json as _json
            data = _json.loads(bm_file.read_text(encoding="utf-8"))
            results = []
            def _collect(node, depth=0):
                if depth > 6 or len(results) >= 30:
                    return
                t = node.get("type", "")
                if t == "url":
                    results.append(f"  {node.get('name','')[:40]} → {node.get('url','')[:60]}")
                elif t == "folder":
                    results.append(f"[{node.get('name','')}]")
                    for child in node.get("children", []):
                        _collect(child, depth + 1)
            roots = data.get("roots", {})
            for rk in ("bookmark_bar", "other", "synced"):
                if rk in roots:
                    _collect(roots[rk])
            return f"Bookmarks ({len(results)} items):\n" + "\n".join(results[:30])
        except Exception as e:
            return f"Bookmarks error: {e}"

    # ── Tab Management ────────────────────────────────────────────────────────

    async def list_tabs(self) -> str:
        await self._launch()
        try:
            ctx = self._context
            if not ctx:
                return "No active browser context."
            pages = [p for p in ctx.pages if not p.is_closed()]
            if not pages:
                return "No open tabs."
            lines = []
            for i, p in enumerate(pages):
                marker = " ◀ active" if p == self._page else ""
                try:
                    title = await p.title()
                except Exception:
                    title = "?"
                lines.append(f"  [{i}] {title[:50]} — {p.url[:60]}{marker}")
            return f"Open tabs ({len(pages)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"List tabs error: {e}"

    async def switch_tab(self, index: int = 0) -> str:
        await self._launch()
        try:
            ctx = self._context
            pages = [p for p in ctx.pages if not p.is_closed()]
            if not pages:
                return "No open tabs."
            idx = max(0, min(index, len(pages) - 1))
            self._page = pages[idx]
            try:
                await self._page.bring_to_front()
            except Exception:
                pass
            title = await self._page.title()
            return f"Switched to tab [{idx}]: {title}"
        except Exception as e:
            return f"Switch tab error: {e}"

    async def close_browser(self) -> str:
        await self._async_close()
        return f"{self.browser_name} closed."

class _SessionRegistry:
    """Tüm aktif tarayıcı oturumlarını yönetir."""

    def __init__(self):
        self._sessions:       dict[str, _BrowserSession] = {}
        self._active_browser: str                        = ""
        self._lock            = threading.Lock()

    def _get_or_create(self, browser_name: str) -> _BrowserSession:
        with self._lock:
            if browser_name not in self._sessions:
                sess = _BrowserSession(browser_name)
                sess.start()
                self._sessions[browser_name] = sess
                print(f"[Registry] New session: {browser_name}")
            return self._sessions[browser_name]

    def get(self, browser_name: str | None = None) -> _BrowserSession:
        if not browser_name:
            browser_name = self._active_browser or _detect_default_browser()
        browser_name = _ALIASES.get(browser_name.lower().strip(), browser_name.lower().strip())
        sess = self._get_or_create(browser_name)
        self._active_browser = browser_name
        return sess

    def switch(self, browser_name: str) -> str:
        browser_name = _ALIASES.get(browser_name.lower().strip(), browser_name.lower().strip())
        self._get_or_create(browser_name)
        self._active_browser = browser_name
        return f"Active browser → {browser_name}"

    def close_one(self, browser_name: str) -> str:
        with self._lock:
            sess = self._sessions.pop(browser_name, None)
        if sess:
            sess.close()
            if self._active_browser == browser_name:
                self._active_browser = ""
            return f"{browser_name} closed."
        return f"No active session for: {browser_name}"

    def close_all(self) -> str:
        with self._lock:
            names    = list(self._sessions.keys())
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._active_browser = ""
        for s in sessions:
            try:
                s.close()
            except Exception:
                pass
        return "All browsers closed: " + (", ".join(names) if names else "none")

    def list_sessions(self) -> str:
        with self._lock:
            if not self._sessions:
                return "No active browser sessions."
            lines = []
            for name in self._sessions:
                marker = " ◀ active" if name == self._active_browser else ""
                lines.append(f"  • {name}{marker}")
            return "Open browsers:\n" + "\n".join(lines)


_registry = _SessionRegistry()


def _quick_chrome_open(action: str, params: dict) -> str:
    """
    Open a URL / search in the user's REAL Chrome via subprocess.
    No Playwright, no automation banner, instant (< 1 second).
    Used for simple go_to / search / new_tab that need no interaction.
    """
    cfg     = _load_cfg()
    exe     = cfg.get("chrome_exe_path", "")
    profile = cfg.get("chrome_google_profile", "Default")

    if not exe or not Path(exe).exists():
        for c in _CHROME_EXE_CANDIDATES:
            if Path(c).exists():
                exe = c
                break

    if action == "search":
        query   = params.get("query", "")
        engine  = params.get("engine", "google")
        _engines = {
            "google":     "https://www.google.com/search?q=",
            "bing":       "https://www.bing.com/search?q=",
            "duckduckgo": "https://duckduckgo.com/?q=",
            "yandex":     "https://yandex.com/search/?text=",
        }
        url = _engines.get(engine.lower(), _engines["google"]) + query.replace(" ", "+")
    else:
        url = _normalize_url(params.get("url", ""))

    if not url or url == "about:blank":
        return "No URL provided."

    local     = os.environ.get("LOCALAPPDATA", "")
    user_data = str(Path(local) / "Google" / "Chrome" / "User Data")

    if exe and Path(exe).exists():
        subprocess.Popen([
            exe,
            f"--profile-directory={profile}",
            f"--user-data-dir={user_data}",
            url,
        ])
        return f"Opened: {url}"

    # Fallback: system default browser
    import webbrowser
    webbrowser.open(url)
    return f"Opened: {url}"


def browser_control(
    parameters:    dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params  = parameters or {}
    action  = params.get("action", "").lower().strip()
    browser = (params.get("browser", "") or "").lower().strip() or None
    # Internal flag: force Playwright even for go_to/search (used by WhatsApp etc.)
    force_pw = params.get("_force_playwright", False)
    result  = "Unknown action."

    if action == "switch":
        target = browser or params.get("target", "").lower().strip()
        result = _registry.switch(target) if target else "Please specify a browser."
        _log(player, result)
        return result

    if action == "list_browsers":
        result = _registry.list_sessions()
        _log(player, result)
        return result

    if action == "close_all":
        result = _registry.close_all()
        _log(player, result)
        return result

    # ── Fast path: go_to / search / new_tab for Chrome → subprocess (instant) ─
    # Bypasses Playwright entirely. No timeout, no automation banner, real profile.
    if (not force_pw
            and action in ("go_to", "search", "new_tab")
            and (not browser or browser in ("chrome", "google chrome"))
            and _OS == "Windows"):
        result = _quick_chrome_open(action, params)
        _log(player, result)
        return result

    # ── Playwright session ────────────────────────────────────────────────────
    try:
        sess = _registry.get(browser)
    except Exception as e:
        result = f"Could not start browser session: {e}"
        _log(player, result)
        return result

    # Per-action timeouts (seconds) — keeps NEXO responsive
    _T_FAST   = 15   # scroll, press, click, hover, js
    _T_NAV    = 35   # navigation, new_tab
    _T_INPUT  = 20   # type, fill_form, smart_type
    _T_SCRAPE = 20   # get_text, get_links, find_all, page_info
    _T_WAIT   = 30   # wait_for_selector, screenshot

    try:
        if action == "go_to":
            result = sess.run(sess.go_to(params.get("url", "")), timeout=_T_NAV)
        elif action == "search":
            result = sess.run(sess.search(params.get("query", ""), params.get("engine", "google")), timeout=_T_NAV)
        elif action == "click":
            result = sess.run(sess.click(params.get("selector"), params.get("text")), timeout=_T_FAST)
        elif action == "type":
            result = sess.run(sess.type_text(
                params.get("selector"), params.get("text", ""), params.get("clear_first", True)), timeout=_T_INPUT)
        elif action == "scroll":
            result = sess.run(sess.scroll(params.get("direction", "down"), int(params.get("amount", 500))), timeout=_T_FAST)
        elif action == "scroll_element":
            result = sess.run(sess.scroll_element(
                params.get("selector", "body"), params.get("direction", "down"),
                int(params.get("amount", 300))), timeout=_T_FAST)
        elif action == "fill_form":
            result = sess.run(sess.fill_form(params.get("fields", {})), timeout=_T_INPUT)
        elif action == "smart_click":
            result = sess.run(sess.smart_click(params.get("description", "")), timeout=_T_FAST)
        elif action == "smart_type":
            result = sess.run(sess.smart_type(params.get("description", ""), params.get("text", "")), timeout=_T_INPUT)
        elif action == "get_text":
            result = sess.run(sess.get_text(), timeout=_T_SCRAPE)
        elif action == "get_url":
            result = sess.run(sess.get_url(), timeout=_T_FAST)
        elif action == "get_title":
            result = sess.run(sess.get_title(), timeout=_T_FAST)
        elif action == "get_page_info":
            result = sess.run(sess.get_page_info(), timeout=_T_SCRAPE)
        elif action == "get_links":
            result = sess.run(sess.get_links(), timeout=_T_SCRAPE)
        elif action == "find_all":
            result = sess.run(sess.find_all(params.get("selector", "a")), timeout=_T_SCRAPE)
        elif action == "press":
            result = sess.run(sess.press(params.get("key", "Enter")), timeout=_T_FAST)
        elif action == "new_tab":
            result = sess.run(sess.new_tab(params.get("url", "")), timeout=_T_NAV)
        elif action == "close_tab":
            result = sess.run(sess.close_tab(), timeout=_T_FAST)
        elif action == "screenshot":
            result = sess.run(sess.screenshot(params.get("path")), timeout=_T_WAIT)
        elif action == "back":
            result = sess.run(sess.back(), timeout=_T_NAV)
        elif action == "forward":
            result = sess.run(sess.forward(), timeout=_T_NAV)
        elif action == "reload":
            result = sess.run(sess.reload(), timeout=_T_NAV)
        elif action == "hover":
            result = sess.run(sess.hover(params.get("selector"), params.get("text")), timeout=_T_FAST)
        elif action == "select_option":
            result = sess.run(sess.select_option(params.get("selector", ""), params.get("value", "")), timeout=_T_FAST)
        elif action == "wait_for_selector":
            result = sess.run(sess.wait_for_selector(
                params.get("selector", ""), int(params.get("timeout", 10_000))), timeout=_T_WAIT)
        elif action == "execute_js":
            result = sess.run(sess.execute_js(params.get("script", "null")), timeout=_T_FAST)
        elif action == "focus":
            result = sess.run(sess.focus_element(params.get("selector", "")), timeout=_T_FAST)
        elif action == "copy":
            result = sess.run(sess.copy_text(), timeout=_T_FAST)
        elif action == "zoom":
            result = sess.run(sess.zoom(float(params.get("level", 1.0))), timeout=_T_FAST)
        elif action == "submit":
            result = sess.run(sess.submit_form(params.get("selector", "form")), timeout=_T_FAST)
        elif action == "close":
            target = browser or _registry._active_browser
            result = _registry.close_one(target) if target else "No browser specified."
        # ── New cookie/storage/download/history actions ──────────────────────
        elif action == "get_cookies":
            result = sess.run(sess.get_cookies(params.get("url")), timeout=_T_FAST)
        elif action == "clear_cookies":
            result = sess.run(sess.clear_cookies(params.get("url")), timeout=_T_FAST)
        elif action == "set_cookie":
            result = sess.run(sess.set_cookie(
                params.get("name", ""), params.get("value", ""),
                params.get("domain"), params.get("path", "/")), timeout=_T_FAST)
        elif action == "get_local_storage":
            result = sess.run(sess.get_local_storage(params.get("key")), timeout=_T_FAST)
        elif action == "set_local_storage":
            result = sess.run(sess.set_local_storage(
                params.get("key", ""), params.get("value", "")), timeout=_T_FAST)
        elif action == "download_file":
            result = sess.run(sess.download_file(
                params.get("url", ""), params.get("path")), timeout=60)
        elif action == "get_history":
            result = sess.run(sess.get_history(int(params.get("limit", 20))), timeout=_T_SCRAPE)
        elif action == "get_bookmarks":
            result = sess.run(sess.get_bookmarks(), timeout=_T_FAST)
        elif action == "list_tabs":
            result = sess.run(sess.list_tabs(), timeout=_T_FAST)
        elif action == "switch_tab":
            result = sess.run(sess.switch_tab(int(params.get("index", 0))), timeout=_T_FAST)
        else:
            result = f"Unknown browser action: '{action}'"

    except concurrent.futures.TimeoutError:
        result = f"Browser action '{action}' timed out."
    except Exception as e:
        result = f"Browser error ({action}): {e}"

    _log(player, result)
    return result


def _log(player, text: str):
    short = str(text)[:80]
    print(f"[Browser] {short}")
    if player:
        player.write_log(f"[browser] {short[:60]}")