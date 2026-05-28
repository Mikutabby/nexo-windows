"""
morning_brief.py — Informe matutino inteligente de NEXO.
Recopila: saludo personalizado, clima, objetivos y contexto del día.
Se auto-ejecuta en el primer arranque del día y es invocable manualmente.
"""
from __future__ import annotations

import json
from datetime import datetime, date
from pathlib import Path

_BASE_DIR   = Path(__file__).resolve().parent.parent
_STATE_FILE = _BASE_DIR / "config" / "morning_brief_state.json"
_GOALS_FILE = _BASE_DIR / "config" / "goals.json"
_API_FILE   = _BASE_DIR / "config" / "api_keys.json"
_MEMORY_FILE = _BASE_DIR / "memory" / "long_term.json"

_GREETINGS = {
    "morning": ["Buenos días", "Buen día"],
    "afternoon": ["Buenas tardes"],
    "evening": ["Buenas noches"],
}

_TIPS = [
    "La regla de los dos minutos: si una tarea toma menos de dos minutos, hacela ahora.",
    "Recordá hidratarte cada hora. La hidratación mejora el foco y la energía.",
    "Bloqueá tiempo en tu calendario para trabajo profundo sin interrupciones.",
    "Empezá el día con la tarea más difícil — el efecto 'eating the frog'.",
    "Revisá tus metas semanales cada lunes para mantener el rumbo.",
    "Hacé pausas activas cada 90 minutos para mantener la productividad alta.",
    "La claridad de objetivos supera a la motivación — sabé exactamente qué querés.",
    "Un ambiente ordenado reduce la carga cognitiva y mejora la concentración.",
]


def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text("utf-8"))
    except Exception:
        return {}


def _save_state(state: dict):
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), "utf-8")
    except Exception:
        pass


def already_briefed_today() -> bool:
    """Returns True if morning brief was already sent today."""
    state = _load_state()
    return state.get("last_date") == str(date.today())


def mark_briefed():
    state = _load_state()
    state["last_date"] = str(date.today())
    _save_state(state)


def _get_username() -> str:
    try:
        data = json.loads(_API_FILE.read_text("utf-8"))
        name = data.get("user_name", "")
        if name:
            return name
    except Exception:
        pass
    try:
        mem = json.loads(_MEMORY_FILE.read_text("utf-8"))
        name = (
            mem.get("personal", {}).get("name", {}).get("value", "")
            or mem.get("user", {}).get("name", {}).get("value", "")
        )
        if name:
            return name.split()[0]
    except Exception:
        pass
    return ""


def _get_greeting(now: datetime) -> str:
    hour = now.hour
    if 5 <= hour < 12:
        return "Buenos días"
    elif 12 <= hour < 19:
        return "Buenas tardes"
    else:
        return "Buenas noches"


def _get_weather_summary(city: str) -> str:
    try:
        import requests
        # Geocode
        geo = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": city, "format": "json", "limit": 1},
            headers={"User-Agent": "NEXO/2.0"},
            timeout=6,
        ).json()
        if not geo:
            return ""
        lat, lon = float(geo[0]["lat"]), float(geo[0]["lon"])

        # Fetch weather
        w = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,weathercode,windspeed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "forecast_days": 1,
                "timezone": "auto",
            },
            timeout=8,
        ).json()

        cur = w.get("current", {})
        temp = cur.get("temperature_2m", "?")
        code = cur.get("weathercode", 0)
        daily = w.get("daily", {})
        rain_prob = (daily.get("precipitation_probability_max") or [0])[0]

        _WMO = {
            0: "cielo despejado", 1: "principalmente despejado",
            2: "parcialmente nublado", 3: "nublado",
            45: "neblina", 48: "escarcha",
            51: "llovizna leve", 53: "llovizna moderada", 55: "llovizna intensa",
            61: "lluvia leve", 63: "lluvia moderada", 65: "lluvia fuerte",
            71: "nevada leve", 73: "nevada moderada", 75: "nevada intensa",
            80: "chaparrón leve", 81: "chaparrón", 82: "chaparrón violento",
            95: "tormenta", 96: "tormenta con granizo",
        }
        desc = _WMO.get(code, "clima variable")
        rain_note = f", {rain_prob}% de probabilidad de lluvia" if rain_prob > 30 else ""
        return f"{desc}, {temp}°C{rain_note} en {city}"
    except Exception as e:
        print(f"[MorningBrief] Weather error: {e}")
        return ""


def _get_goals_summary() -> str:
    try:
        goals = json.loads(_GOALS_FILE.read_text("utf-8"))
        active = [g for g in goals if not g.get("completed")]
        if not active:
            return ""
        names = [g.get("title", g.get("name", "?")) for g in active[:3]]
        if len(active) == 1:
            return f"Tenés 1 objetivo activo: {names[0]}."
        return f"Tenés {len(active)} objetivos activos: {', '.join(names)}."
    except Exception:
        return ""


def _get_daily_tip() -> str:
    import random
    # Use day of year as seed so tip is consistent all day but changes daily
    random.seed(datetime.now().timetuple().tm_yday)
    return random.choice(_TIPS)


def morning_brief(parameters: dict, player=None, **kwargs) -> str:
    """
    Genera el informe matutino completo de NEXO.
    Incluye: saludo, fecha, clima, objetivos activos y consejo del día.
    """
    now  = datetime.now()
    params = parameters or {}
    force = params.get("force", False)

    # Read config for city and username
    try:
        cfg = json.loads(_API_FILE.read_text("utf-8"))
        city = cfg.get("weather_city", cfg.get("city", "Buenos Aires"))
    except Exception:
        city = "Buenos Aires"

    username = _get_username()
    greeting = _get_greeting(now)
    months_es = {
        "January": "enero", "February": "febrero", "March": "marzo",
        "April": "abril", "May": "mayo", "June": "junio",
        "July": "julio", "August": "agosto", "September": "septiembre",
        "October": "octubre", "November": "noviembre", "December": "diciembre",
    }
    day_names_es = {
        "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
        "Thursday": "Jueves", "Friday": "Viernes",
        "Saturday": "Sábado", "Sunday": "Domingo",
    }
    day_name = day_names_es.get(now.strftime("%A"), now.strftime("%A"))
    month    = months_es.get(now.strftime("%B"), now.strftime("%B"))
    date_str = f"{day_name} {now.day} de {month} de {now.year}"

    time_str = now.strftime("%I:%M %p").lstrip("0")

    parts = []
    name_part = f", {username}" if username else ""
    parts.append(f"{greeting}{name_part}. Son las {time_str} del {date_str}.")

    # Weather
    weather = _get_weather_summary(city)
    if weather:
        parts.append(f"El clima en {city}: {weather}.")

    # Goals
    goals_summary = _get_goals_summary()
    if goals_summary:
        parts.append(goals_summary)

    # Tip of the day
    tip = _get_daily_tip()
    parts.append(f"Consejo del día: {tip}")

    parts.append("¿En qué le puedo asistir hoy?")

    # Mark as briefed for today
    mark_briefed()

    result = " ".join(parts)
    if player:
        player.write_log(f"NEXO: {result[:120]}…")
    return result
