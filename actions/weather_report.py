"""
weather_report.py — Clima para NEXO con widget integrado en la UI.

- Obtiene datos reales via Open-Meteo (sin API key).
- Geocodifica la ciudad con Nominatim (sin API key).
- Envía los datos al WeatherWidget de la UI usando __weather__: command.
- Fallback gracioso si no hay internet.
"""
from __future__ import annotations

import datetime

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

# ── Mapeo de WMO weather codes → (descripción, icono emoji) ──────────────────
_WMO_MAP: dict[int, tuple[str, str]] = {
    0:  ("Cielo despejado",          "☀"),
    1:  ("Principalmente despejado", "🌤"),
    2:  ("Parcialmente nublado",     "⛅"),
    3:  ("Nublado",                  "☁"),
    45: ("Neblina",                  "🌫"),
    48: ("Escarcha",                 "🌫"),
    51: ("Llovizna leve",            "🌦"),
    53: ("Llovizna moderada",        "🌦"),
    55: ("Llovizna intensa",         "🌧"),
    61: ("Lluvia leve",              "🌧"),
    63: ("Lluvia moderada",          "🌧"),
    65: ("Lluvia fuerte",            "🌧"),
    71: ("Nevada leve",              "❄"),
    73: ("Nevada moderada",          "❄"),
    75: ("Nevada intensa",           "❄"),
    77: ("Granizo",                  "🌨"),
    80: ("Chaparrón leve",           "🌦"),
    81: ("Chaparrón moderado",       "🌧"),
    82: ("Chaparrón violento",       "⛈"),
    85: ("Nevada leve",              "🌨"),
    86: ("Nevada fuerte",            "🌨"),
    95: ("Tormenta",                 "⛈"),
    96: ("Tormenta con granizo",     "⛈"),
    99: ("Tormenta fuerte con granizo", "⛈"),
}

_HEADERS = {"User-Agent": "NEXO/2.0 (weather widget)"}


def _log(message: str, player=None) -> None:
    print(f"[Weather] {message}")
    if player:
        try:
            player.write_log(f"NEXO: {message}")
        except Exception:
            pass


def _geocode(city: str) -> tuple[float, float, str] | None:
    try:
        url = "https://nominatim.openstreetmap.org/search"
        r = _requests.get(
            url,
            params={"q": city, "format": "json", "limit": 1, "accept-language": "es"},
            headers=_HEADERS,
            timeout=8,
        )
        data = r.json()
        if not data:
            return None
        item = data[0]
        return float(item["lat"]), float(item["lon"]), item["display_name"]
    except Exception as e:
        print(f"[Weather] Geocode error: {e}")
        return None


def _fetch_weather(lat: float, lon: float) -> dict | None:
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        r = _requests.get(
            url,
            params={
                "latitude":    lat,
                "longitude":   lon,
                "current":     "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                "daily":       "temperature_2m_max,temperature_2m_min,weather_code",
                "timezone":    "auto",
                "forecast_days": 4,
            },
            headers=_HEADERS,
            timeout=10,
        )
        return r.json()
    except Exception as e:
        print(f"[Weather] Open-Meteo error: {e}")
        return None


def weather_action(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    city   = params.get("city", "").strip()
    when   = params.get("time", "now").strip().lower()

    if not city:
        msg = "Necesito el nombre de la ciudad para mostrar el clima."
        _log(msg, player)
        return msg

    if not _HAS_REQUESTS:
        msg = "❌ Módulo 'requests' no instalado. Ejecutá: pip install requests"
        _log(msg, player)
        return msg

    _log(f"Obteniendo clima para: {city}", player)

    geo = _geocode(city)
    if not geo:
        import webbrowser
        from urllib.parse import quote_plus as qp
        webbrowser.open(f"https://www.google.com/search?q={qp('clima ' + city)}")
        msg = f"No pude geocodificar '{city}'. Abriendo Google."
        _log(msg, player)
        return msg

    lat, lon, display_name = geo
    short_name = display_name.split(",")[0].strip()
    _log(f"Ciudad: {short_name} ({lat:.3f}, {lon:.3f})", player)

    data = _fetch_weather(lat, lon)
    if not data or "current" not in data:
        msg = f"No pude obtener datos de clima para {city}."
        _log(msg, player)
        return msg

    cur   = data["current"]
    temp  = cur.get("temperature_2m", "?")
    feels = cur.get("apparent_temperature", "?")
    humid = cur.get("relative_humidity_2m", "?")
    wind  = cur.get("wind_speed_10m", "?")
    code  = int(cur.get("weather_code", 0))
    desc, icon = _WMO_MAP.get(code, ("Desconocido", "🌡"))

    def _fmt(v, unit): return f"{v:.0f}{unit}" if isinstance(v, (int, float)) else f"{v}{unit}"
    temp_str  = _fmt(temp,  "°C")
    feels_str = _fmt(feels, "°C")
    wind_str  = _fmt(wind,  " km/h")

    # Pronóstico próximos días
    forecast_parts = []
    daily = data.get("daily", {})
    times = daily.get("time", [])
    t_max = daily.get("temperature_2m_max", [])
    t_min = daily.get("temperature_2m_min", [])
    d_cod = daily.get("weather_code", [])
    day_names = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    for i in range(min(4, len(times))):
        try:
            dt = datetime.date.fromisoformat(times[i])
            dn = day_names[dt.weekday()]
            dc = int(d_cod[i]) if i < len(d_cod) else 0
            di = _WMO_MAP.get(dc, ("?", "🌤"))[1]
            mx = _fmt(t_max[i], "°") if i < len(t_max) and isinstance(t_max[i], (int, float)) else "?"
            mn = _fmt(t_min[i], "°") if i < len(t_min) and isinstance(t_min[i], (int, float)) else "?"
            forecast_parts.append(f"{dn}:{di}{mx}/{mn}")
        except Exception:
            pass
    forecast_str = ",".join(forecast_parts)

    # Enviar al widget de NEXO
    # Formato: city|temp|desc|icon|feels|humid_label|wind_label|forecast
    widget_payload = "|".join([
        short_name,
        temp_str,
        desc,
        icon,
        feels_str,
        f"Humedad {humid}%",
        f"Viento {wind_str}",
        forecast_str,
    ])
    if player:
        try:
            player.write_log(f"__weather__:{widget_payload}")
        except Exception as e:
            print(f"[Weather] widget error: {e}")

    msg = (
        f"Clima en {short_name}: {desc} {icon}, {temp_str} "
        f"(sensación {feels_str}). Humedad {humid}%, viento {wind_str}."
    )
    _log(msg, player)

    if session_memory:
        try:
            session_memory.set_last_search(query=f"clima {city}", response=msg)
        except Exception:
            pass

    return msg