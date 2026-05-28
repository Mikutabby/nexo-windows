"""
spotify_control.py — Control total de Spotify para NEXO.
Requiere: pip install spotipy
Configurar en config/api_keys.json:
  "spotify_client_id": "...",
  "spotify_client_secret": "...",
  "spotify_redirect_uri": "http://127.0.0.1:8888/callback"
"""
from __future__ import annotations
import json
import sys
import platform
import subprocess
import time
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def _load_cfg() -> dict:
    try:
        return json.loads((_base_dir() / "config" / "api_keys.json").read_text("utf-8"))
    except Exception:
        return {}

def _save_cfg(key: str, value) -> None:
    try:
        p = _base_dir() / "config" / "api_keys.json"
        cfg = _load_cfg()
        cfg[key] = value
        p.write_text(json.dumps(cfg, indent=4), "utf-8")
    except Exception:
        pass

def _get_sp():
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
    except ImportError:
        raise RuntimeError("spotipy no está instalado. Ejecutá: pip install spotipy")

    cfg = _load_cfg()
    cid  = cfg.get("spotify_client_id", "")
    csec = cfg.get("spotify_client_secret", "")
    ruri = cfg.get("spotify_redirect_uri", "http://127.0.0.1:8888/callback")

    if not cid or not csec:
        raise RuntimeError(
            "Faltan spotify_client_id y spotify_client_secret en config/api_keys.json. "
            "Creá una app en developer.spotify.com y pegá las credenciales.\n"
            "IMPORTANTE: En tu app de Spotify → Edit Settings → Redirect URIs, "
            "agregá exactamente: http://127.0.0.1:8888/callback"
        )

    cache_path = str(_base_dir() / "config" / "spotify_token.json")
    scope = (
        "user-read-playback-state user-modify-playback-state "
        "user-read-currently-playing playlist-read-private "
        "playlist-modify-public playlist-modify-private "
        "user-library-read user-library-modify user-top-read"
    )
    auth = SpotifyOAuth(
        client_id=cid, client_secret=csec,
        redirect_uri=ruri, scope=scope,
        cache_path=cache_path, open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth)


def _active_device(sp):
    devs = sp.devices().get("devices", [])
    if not devs:
        return None
    for d in devs:
        if d.get("is_active"):
            return d["id"]
    return devs[0]["id"]


def _open_spotify():
    """Intenta abrir la app de Spotify según el SO."""
    os_name = platform.system()
    try:
        if os_name == "Windows":
            # Intenta con el protocolo URI primero (abre la app si está instalada)
            subprocess.Popen(["cmd", "/c", "start", "spotify:"], shell=False,
                             creationflags=0x08000000)
        elif os_name == "Darwin":
            subprocess.Popen(["open", "-a", "Spotify"])
        else:
            subprocess.Popen(["spotify"])
    except Exception:
        pass


def _get_device_waiting(sp, player=None, timeout: int = 35) -> str | None:
    """
    Devuelve un device_id activo. Si no hay ninguno, abre Spotify y espera
    hasta `timeout` segundos a que aparezca un dispositivo.
    """
    dev = _active_device(sp)
    if dev:
        return dev

    _log(player, "No hay dispositivos Spotify activos. Abriendo Spotify…")
    _open_spotify()

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        dev = _active_device(sp)
        if dev:
            _log(player, f"Dispositivo Spotify detectado: {dev[:8]}…")
            # Pequeña pausa extra para que el cliente esté listo
            time.sleep(1.5)
            return dev

    return None


def _log(player, msg: str):
    print(f"[Spotify] {msg}")
    if player:
        player.write_log(f"[spotify] {msg}")


def _send_spotify_widget(sp, player, is_playing: bool = True):
    """Fetch current playback and send widget update to the NEXO UI."""
    if not player:
        return
    try:
        cur = sp.current_playback()
        if not cur or not cur.get("item"):
            return
        item     = cur["item"]
        song     = item.get("name", "")
        artists  = ", ".join(a["name"] for a in item.get("artists", []))
        album    = item.get("album", {}).get("name", "")
        dur_ms   = item.get("duration_ms", 0)
        prog_ms  = cur.get("progress_ms", 0)
        playing  = cur.get("is_playing", is_playing)
        payload  = f"{song}|{artists}|{album}|{dur_ms}|{prog_ms}|{'true' if playing else 'false'}"
        player.write_log(f"__spotify__:{payload}")
    except Exception as e:
        print(f"[Spotify] widget update error: {e}")


def spotify_control(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "current").lower().strip()

    try:
        sp = _get_sp()
    except RuntimeError as e:
        return f"❌ {e}"

    try:
        # Para play usamos _get_device_waiting que abre Spotify si es necesario.
        # Para el resto de acciones (pause, next, etc.) basta con _active_device.
        if action == "play":
            dev = _get_device_waiting(sp, player=player, timeout=35)
        else:
            dev = _active_device(sp)

        # ── PLAY ──────────────────────────────────────────────
        if action == "play":
            if not dev:
                return (
                    "❌ Spotify no respondió después de 35 segundos. "
                    "Abrí la app manualmente y volvé a pedirme la canción."
                )
            query = params.get("query", "").strip()
            if query:
                stype = params.get("type", "track").lower()
                res = sp.search(q=query, type=stype, limit=1)
                key = stype + "s"
                items = res.get(key, {}).get("items", [])
                if not items:
                    return f"❌ No encontré '{query}' en Spotify."
                item = items[0]
                uri  = item["uri"]
                name = item.get("name", uri)
                if stype == "track":
                    sp.start_playback(device_id=dev, uris=[uri])
                else:
                    sp.start_playback(device_id=dev, context_uri=uri)
                msg = f"▶ Reproduciendo: {name}"
            else:
                sp.start_playback(device_id=dev)
                msg = "▶ Reproducción reanudada."
            _log(player, msg)
            # Update widget with full playback info
            import time as _t; _t.sleep(0.8)
            _send_spotify_widget(sp, player)
            return msg

        # ── PAUSE ─────────────────────────────────────────────
        elif action in ("pause", "stop"):
            sp.pause_playback(device_id=dev)
            msg = "⏸ Spotify pausado."
            _log(player, msg)
            _send_spotify_widget(sp, player, is_playing=False)
            return msg

        # ── RESUME ────────────────────────────────────────────
        elif action == "resume":
            sp.start_playback(device_id=dev)
            msg = "▶ Reproducción reanudada."
            _log(player, msg)
            import time as _t; _t.sleep(0.5)
            _send_spotify_widget(sp, player)
            return msg

        # ── NEXT ──────────────────────────────────────────────
        elif action in ("next", "siguiente"):
            sp.next_track(device_id=dev)
            import time; time.sleep(0.6)
            cur = sp.current_playback()
            name = cur["item"]["name"] if cur and cur.get("item") else "siguiente canción"
            msg = f"⏭ Siguiente: {name}"
            _log(player, msg)
            _send_spotify_widget(sp, player)
            return msg

        # ── PREVIOUS ──────────────────────────────────────────
        elif action in ("previous", "anterior", "prev"):
            sp.previous_track(device_id=dev)
            import time; time.sleep(0.6)
            cur = sp.current_playback()
            name = cur["item"]["name"] if cur and cur.get("item") else "canción anterior"
            msg = f"⏮ Anterior: {name}"
            _log(player, msg)
            _send_spotify_widget(sp, player)
            return msg

        # ── VOLUME ────────────────────────────────────────────
        elif action == "volume":
            vol = int(params.get("value", 50))
            vol = max(0, min(100, vol))
            sp.volume(vol, device_id=dev)
            msg = f"🔊 Volumen de Spotify: {vol}%"
            _log(player, msg)
            return msg

        # ── SHUFFLE ───────────────────────────────────────────
        elif action == "shuffle":
            state = str(params.get("value", "true")).lower() != "false"
            sp.shuffle(state=state, device_id=dev)
            msg = f"🔀 Aleatorio {'activado' if state else 'desactivado'}."
            _log(player, msg)
            return msg

        # ── REPEAT ────────────────────────────────────────────
        elif action == "repeat":
            mode = params.get("value", "track").lower()  # off | track | context
            sp.repeat(state=mode, device_id=dev)
            msg = f"🔁 Repetición: {mode}"
            _log(player, msg)
            return msg

        # ── CURRENT ───────────────────────────────────────────
        elif action in ("current", "info", "que_suena", "qué suena"):
            cur = sp.current_playback()
            if not cur or not cur.get("item"):
                return "No hay nada reproduciéndose en Spotify ahora mismo."
            item   = cur["item"]
            track  = item.get("name", "?")
            artist = ", ".join(a["name"] for a in item.get("artists", []))
            album  = item.get("album", {}).get("name", "")
            prog   = cur.get("progress_ms", 0) // 1000
            dur    = item.get("duration_ms", 0) // 1000
            playing = "▶" if cur.get("is_playing") else "⏸"
            msg = f"{playing} {track} — {artist} | {album} [{prog//60}:{prog%60:02d}/{dur//60}:{dur%60:02d}]"
            _log(player, msg)
            return msg

        # ── SEARCH ────────────────────────────────────────────
        elif action == "search":
            query = params.get("query", "")
            stype = params.get("type", "track")
            res   = sp.search(q=query, type=stype, limit=5)
            items = res.get(stype + "s", {}).get("items", [])
            if not items:
                return f"Sin resultados para '{query}'."
            lines = [f"🎵 Resultados para '{query}':"]
            for i, it in enumerate(items, 1):
                artists = ", ".join(a["name"] for a in it.get("artists", [])) if "artists" in it else ""
                lines.append(f"  {i}. {it['name']}" + (f" — {artists}" if artists else ""))
            msg = "\n".join(lines)
            _log(player, msg)
            return msg

        # ── LIKE ──────────────────────────────────────────────
        elif action in ("like", "guardar", "save"):
            cur = sp.current_playback()
            if not cur or not cur.get("item"):
                return "No hay canción activa para guardar."
            tid = cur["item"]["id"]
            sp.current_user_saved_tracks_add([tid])
            name = cur["item"]["name"]
            msg = f"❤️ '{name}' guardada en tu biblioteca."
            _log(player, msg)
            return msg

        # ── DEVICES ───────────────────────────────────────────
        elif action == "devices":
            devs = sp.devices().get("devices", [])
            if not devs:
                return "No hay dispositivos Spotify activos."
            lines = ["📱 Dispositivos disponibles:"]
            for d in devs:
                active = " ◀ activo" if d.get("is_active") else ""
                lines.append(f"  • {d['name']} ({d['type']}){active}")
            msg = "\n".join(lines)
            _log(player, msg)
            return msg

        # ── PLAYLIST ──────────────────────────────────────────
        elif action in ("playlist", "playlists"):
            pls = sp.current_user_playlists(limit=10).get("items", [])
            if not pls:
                return "No tenés playlists guardadas."
            lines = ["📋 Tus playlists:"]
            for pl in pls:
                lines.append(f"  • {pl['name']} ({pl['tracks']['total']} canciones)")
            msg = "\n".join(lines)
            _log(player, msg)
            return msg

        else:
            return f"Acción de Spotify desconocida: '{action}'. Opciones: play, pause, next, previous, volume, shuffle, repeat, current, search, like, devices, playlist."

    except Exception as e:
        err = f"❌ Error Spotify: {e}"
        _log(player, err)
        return err