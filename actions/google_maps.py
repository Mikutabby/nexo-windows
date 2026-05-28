"""
google_maps.py — Navegación y mapas para NEXO.

Características:
  • Lenguaje humano: resuelve "shopping de Devoto", "el Obelisco", "la plaza de mi barrio".
  • Geocodificación inteligente con múltiples estrategias de búsqueda (Nominatim).
  • Memoria de lugares: guardá "mi gym = Av. Corrientes 1234" y NEXO lo recuerda.
  • Alias predefinidos: mi casa, el trabajo, la facu, el gimnasio, etc.
  • Ciudad predeterminada: Buenos Aires (CABA + GBA).
  • Indicaciones siempre en español, lenguaje natural.
  • Modos: auto | caminando | bicicleta | transporte público.
  • Cache de geocodificación en memoria (evita llamadas repetidas a Nominatim).
  • Geocodificación concurrente de origen y destino.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import time
import urllib.parse
from pathlib import Path
import sys

try:
    import requests
    _REQ = True
except ImportError:
    _REQ = False

# ── Memoria de NEXO ─────────────────────────────────────────────────────────
try:
    import os as _os
    sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from memory.memory_manager import load_memory, update_memory
    _HAS_MEMORY = True
except Exception:
    _HAS_MEMORY = False
    def load_memory(): return {}
    def update_memory(_d): pass

# ── Config path ───────────────────────────────────────────────────────────────
_BASE = Path(__file__).resolve().parent.parent
_CFG  = _BASE / "config" / "api_keys.json"

def _get_cfg() -> dict:
    try:
        return json.loads(_CFG.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════
# Geocoding cache (process-level, evita llamadas duplicadas)
# ═══════════════════════════════════════════════════════════
_GEO_CACHE: dict[str, tuple[float, float, str]] = {}
_GEO_CACHE_TTL: dict[str, float] = {}
_GEO_CACHE_SECONDS = 3600  # 1 hora


def _cache_get(key: str) -> tuple[float, float, str] | None:
    if key in _GEO_CACHE:
        if time.time() - _GEO_CACHE_TTL.get(key, 0) < _GEO_CACHE_SECONDS:
            return _GEO_CACHE[key]
    return None


def _cache_set(key: str, val: tuple[float, float, str]):
    _GEO_CACHE[key] = val
    _GEO_CACHE_TTL[key] = time.time()


# ═══════════════════════════════════════════════════════════
# Buenos Aires — palabras clave para detección de ciudad
# ═══════════════════════════════════════════════════════════
_BA_KEYWORDS = {
    "buenos aires", "caba", "capital federal", "b.a.",
    "la matanza", "ramos mejia", "haedo", "moron", "san justo",
    "palermo", "belgrano", "caballito", "flores", "recoleta",
    "villa crespo", "almagro", "boedo", "balvanera", "monserrat",
    "once", "liniers", "villa del parque", "nuñez", "saavedra",
    "villa urquiza", "coghlan", "colegiales", "chacarita",
    "paternal", "floresta", "lugano", "pompeya", "barracas",
    "boca", "san telmo", "puerto madero", "microcentro", "retiro",
    "congreso", "san isidro", "tigre", "quilmes", "lomas de zamora",
    "avellaneda", "lanus", "banfield", "temperley", "san martin",
    "tres de febrero", "hurlingham", "ituzaingo", "merlo", "moreno",
    "general rodriguez", "lujan", "san miguel", "jose c paz",
    "malvinas argentinas", "vicente lopez", "olivos", "florida",
    "munro", "boulogne", "martinez", "beccar", "devoto",
    "villa devoto", "villa del parque", "villa urquiza", "villa pueyrredon",
    "liniers", "ciudadela", "ramos", "haedo", "castelar",
}

_ARGENTINA_CITIES = {
    "argentina", "rosario", "cordoba", "mendoza", "tucuman",
    "la plata", "mar del plata", "salta", "santa fe", "san luis",
    "neuquen", "bariloche", "ushuaia", "corrientes", "resistencia",
}


def _needs_city(address: str) -> bool:
    addr_l = address.lower()
    if any(k in addr_l for k in _BA_KEYWORDS):
        return False
    if any(k in addr_l for k in _ARGENTINA_CITIES):
        return False
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if len(parts) >= 2:
        return False
    return True


def _add_ba(address: str) -> str:
    if _needs_city(address):
        return f"{address}, Buenos Aires, Argentina"
    return address


# ═══════════════════════════════════════════════════════════
# Alias predefinidos (mi casa, el trabajo, etc.)
# ═══════════════════════════════════════════════════════════
_BUILTIN_ALIASES: dict[str, list[str]] = {
    "mi casa":             ["home_address", "casa", "home", "mi_casa"],
    "casa":                ["home_address", "casa", "home"],
    "mi depto":            ["home_address", "depto", "departamento"],
    "mi departamento":     ["home_address", "departamento", "depto"],
    "mi trabajo":          ["work_address", "trabajo", "work", "oficina"],
    "trabajo":             ["work_address", "trabajo", "work"],
    "mi oficina":          ["office_address", "oficina", "work_address"],
    "la oficina":          ["office_address", "oficina"],
    "mi estudio":          ["studio_address", "estudio"],
    "la facu":             ["university", "facultad", "universidad"],
    "la facultad":         ["university", "facultad", "universidad"],
    "la uni":              ["university", "universidad"],
    "el colegio":          ["school_address", "colegio", "escuela"],
    "la escuela":          ["school_address", "escuela"],
    "el gimnasio":         ["gym_address", "gimnasio", "gym"],
    "mi gym":              ["gym_address", "gimnasio", "gym"],
    "el supermercado":     ["supermarket_address", "supermercado"],
    "el club":             ["club_address", "club"],
    "mi club":             ["club_address", "club"],
    "el médico":           ["doctor_address", "medico", "doctor"],
    "el doctor":           ["doctor_address", "medico", "doctor"],
    "la iglesia":          ["church_address", "iglesia"],
    "el banco":            ["bank_address", "banco"],
    "mi banco":            ["bank_address", "banco"],
}


def _resolve_alias(text: str) -> str:
    """
    Resuelve alias de memoria ('mi casa' → 'Av. Rivadavia 123, CABA').
    También busca en la categoría 'places' de la memoria de NEXO.
    """
    if not _HAS_MEMORY:
        return text

    text_lower = text.lower().strip()

    # 1. Buscar en la memoria → categoría "places" (lugares guardados por el usuario)
    try:
        memory = load_memory()
        places = memory.get("places", {})
        if isinstance(places, dict):
            for place_key, place_val in places.items():
                pk = place_key.lower().replace("_", " ")
                if pk == text_lower or pk in text_lower or text_lower in pk:
                    value = (place_val.get("value", "")
                             if isinstance(place_val, dict) else str(place_val))
                    if value and len(value.strip()) > 3:
                        return value.strip()
    except Exception:
        pass

    # 2. Alias predefinidos
    keys_to_try: list[str] | None = _BUILTIN_ALIASES.get(text_lower)
    if keys_to_try is None:
        for alias, keys in _BUILTIN_ALIASES.items():
            if text_lower.startswith(alias) or alias in text_lower:
                keys_to_try = keys
                break

    if not keys_to_try:
        return text

    try:
        memory = load_memory()
        for category in memory.values():
            if not isinstance(category, dict):
                continue
            for mem_key, mem_val in category.items():
                mem_key_l = mem_key.lower()
                if mem_key_l in keys_to_try or any(k in mem_key_l for k in keys_to_try):
                    value = (mem_val.get("value", "")
                             if isinstance(mem_val, dict) else str(mem_val))
                    if value and len(value.strip()) > 3:
                        return value.strip()
    except Exception:
        pass

    return text


# ═══════════════════════════════════════════════════════════
# Construcción de URLs de Google Maps
# ═══════════════════════════════════════════════════════════
_MODE_MAP_GOOGLE = {
    "car":         "driving",   "auto":        "driving",
    "carro":       "driving",   "driving":     "driving",
    "manejar":     "driving",   "en auto":     "driving",
    "en coche":    "driving",
    "walk":        "walking",   "walking":     "walking",
    "caminando":   "walking",   "a pie":       "walking",
    "caminar":     "walking",
    "bike":        "bicycling", "bicycle":     "bicycling",
    "bicicleta":   "bicycling", "cycling":     "bicycling",
    "en bici":     "bicycling",
    "transit":     "transit",   "transporte":  "transit",
    "subte":       "transit",   "tren":        "transit",
    "colectivo":   "transit",   "bus":         "transit",
    "en colectivo":"transit",   "en subte":    "transit",
    "en tren":     "transit",   "transporte público": "transit",
}

_MODE_ICON = {
    "driving":   "🚗",
    "walking":   "🚶",
    "bicycling": "🚲",
    "transit":   "🚌",
}

_MODE_NAME_ES = {
    "driving":   "en auto",
    "walking":   "caminando",
    "bicycling": "en bicicleta",
    "transit":   "en transporte público",
}


def _build_gmaps_url(origin: str, destination: str, mode: str = "car") -> str:
    travelmode = _MODE_MAP_GOOGLE.get(mode.lower(), "driving")
    params = urllib.parse.urlencode({
        "api":         "1",
        "origin":      origin,
        "destination": destination,
        "travelmode":  travelmode,
        "hl":          "es",
    })
    return f"https://www.google.com/maps/dir/?{params}"


def _build_gmaps_search_url(query: str) -> str:
    params = urllib.parse.urlencode({"api": "1", "query": query, "hl": "es"})
    return f"https://www.google.com/maps/search/?{params}"


# ═══════════════════════════════════════════════════════════
# Geocodificación inteligente (Nominatim con fallback)
# ═══════════════════════════════════════════════════════════
_NOMINATIM_HEADERS = {"User-Agent": "NEXO-AI/3.0 (contact@amssystems.com)"}


def _nominatim_search(query: str, limit: int = 1) -> list[dict]:
    """Busca en Nominatim y retorna la lista de resultados."""
    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": query, "format": "json", "limit": limit,
            "accept-language": "es", "addressdetails": "1",
        },
        headers=_NOMINATIM_HEADERS,
        timeout=10,
    )
    r.raise_for_status()
    return r.json() or []


def _geocode(address: str) -> tuple[float, float, str]:
    """
    Geocodifica una dirección con múltiples estrategias de búsqueda.
    Retorna (lat, lon, display_name). Usa cache para evitar llamadas repetidas.
    """
    cache_key = address.lower().strip()
    cached = _cache_get(cache_key)
    if cached:
        return cached

    # Estrategias de búsqueda en orden de especificidad
    search_candidates = [address]

    # Si parece ser un lugar (sin número de calle), probamos variaciones
    addr_l = address.lower()
    if _needs_city(address):
        search_candidates.append(f"{address}, Buenos Aires, Argentina")

    # Agregar "Argentina" como fallback
    if "argentina" not in addr_l:
        search_candidates.append(f"{address}, Argentina")

    last_exc: Exception | None = None
    for candidate in search_candidates:
        try:
            results = _nominatim_search(candidate, limit=1)
            if results:
                item = results[0]
                result = (float(item["lat"]), float(item["lon"]), item["display_name"])
                _cache_set(cache_key, result)
                return result
        except Exception as e:
            last_exc = e
            continue

    raise ValueError(
        f"No pude encontrar '{address}' en el mapa. "
        "Probá siendo más específico, por ejemplo: "
        f"'{address.split(',')[0]}, Buenos Aires, Argentina'"
    ) if last_exc is None else last_exc


def _smart_geocode(query: str, player=None) -> tuple[float, float, str]:
    """
    Geocodificación NLP-aware: maneja lenguaje natural como
    'el shopping de Devoto', 'el Obelisco', 'la Terminal de Ómnibus'.
    """
    cache_key = query.lower().strip()
    cached = _cache_get(cache_key)
    if cached:
        return cached

    # 1. Resolver alias de memoria
    resolved = _resolve_alias(query)
    if resolved != query and resolved:
        _log(player, f"Alias resuelto: '{query}' → '{resolved}'")
        query = resolved

    # 2. Agregar ciudad si falta
    query_with_city = _add_ba(query)

    # 3. Estrategias de búsqueda (de más a menos específica)
    candidates: list[str] = []

    # Búsqueda directa con ciudad
    candidates.append(query_with_city)

    # Si tiene prefijo artículo ("el", "la", "los", "las"), probamos sin él
    clean = re.sub(r'^(el|la|los|las|un|una)\s+', '', query, flags=re.IGNORECASE).strip()
    if clean != query:
        candidates.append(_add_ba(clean))

    # Si tiene "de" intermediario ("shopping de Devoto" → "Shopping Devoto")
    no_de = re.sub(r'\bde\s+', '', query, count=1).strip()
    if no_de != query:
        candidates.append(_add_ba(no_de))

    # Variación sin artículo y sin "de"
    no_art_no_de = re.sub(r'^(el|la|los|las|un|una)\s+', '', no_de, flags=re.IGNORECASE).strip()
    if no_art_no_de not in candidates:
        candidates.append(_add_ba(no_art_no_de))

    # Fallback: sólo "Argentina"
    if "argentina" not in query.lower():
        candidates.append(f"{query}, Argentina")

    last_exc: Exception | None = None
    for candidate in candidates:
        try:
            results = _nominatim_search(candidate, limit=3)
            if results:
                # Prefer results that are in Argentina
                for item in results:
                    disp = item.get("display_name", "")
                    if "argentina" in disp.lower() or not results[1:]:
                        result = (float(item["lat"]), float(item["lon"]), disp)
                        _cache_set(cache_key, result)
                        return result
                # Take first if none match Argentina
                item = results[0]
                result = (float(item["lat"]), float(item["lon"]), item["display_name"])
                _cache_set(cache_key, result)
                return result
        except Exception as e:
            last_exc = e
            continue

    raise ValueError(
        f"No encontré '{query}'. "
        "Tratá de ser más específico, por ejemplo incluyendo el barrio o la ciudad."
    )


# ═══════════════════════════════════════════════════════════
# OSRM — rutas y pasos de navegación
# ═══════════════════════════════════════════════════════════
_OSRM_PROFILES = {
    "driving": "driving", "car": "driving", "auto": "driving",
    "walking": "walking", "walk": "walking", "caminando": "walking", "a pie": "walking",
    "bicycling": "cycling", "bike": "cycling", "bicicleta": "cycling",
    "transit": "driving",   # OSRM no tiene transit, usamos driving como aprox.
}


def _get_route_osrm(orig: tuple[float, float], dest: tuple[float, float],
                    mode: str = "driving") -> dict:
    profile = _OSRM_PROFILES.get(mode.lower(), "driving")
    url = (
        f"https://router.project-osrm.org/route/v1/{profile}/"
        f"{orig[1]},{orig[0]};{dest[1]},{dest[0]}"
        f"?overview=full&geometries=geojson&steps=true"
    )
    r = requests.get(url, headers=_NOMINATIM_HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise ValueError(f"No pude calcular la ruta: {data.get('message', 'error desconocido')}")
    return data["routes"][0]


def _fmt_duration(seconds: int) -> str:
    h, m = divmod(int(seconds) // 60, 60)
    if h and m:
        return f"{h}h {m}min"
    elif h:
        return f"{h}h"
    return f"{m} min"


def _fmt_distance(meters: float) -> str:
    if meters >= 1000:
        return f"{meters/1000:.1f} km"
    return f"{int(meters)} m"


# ═══════════════════════════════════════════════════════════
# Resumen de pasos en español, lenguaje natural
# ═══════════════════════════════════════════════════════════
_STEP_TYPE_ES = {
    "depart":       "Partí",
    "arrive":       "¡Llegaste a tu destino!",
    "turn":         "Girá",
    "merge":        "Incorporate",
    "roundabout":   "Tomá la rotonda",
    "fork":         "En el cruce",
    "straight":     "Seguí recto",
    "end of road":  "Al final de la calle",
    "new name":     "Continuás por",
    "notification": "Atención",
}

_STEP_MOD_ES = {
    "left":         "a la izquierda",
    "right":        "a la derecha",
    "slight left":  "levemente a la izquierda",
    "slight right":  "levemente a la derecha",
    "sharp left":   "fuerte a la izquierda",
    "sharp right":  "fuerte a la derecha",
    "uturn":        "con media vuelta",
    "straight":     "recto",
}


def _steps_to_text(steps: list[dict], max_steps: int = 6) -> list[str]:
    lines = []
    for step in steps[:max_steps]:
        m    = step.get("maneuver", {})
        typ  = m.get("type", "")
        mod  = m.get("modifier", "")
        name = (step.get("name", "") or "").strip()
        d    = _fmt_distance(step.get("distance", 0))

        if typ == "depart":
            via = f" por {name}" if name else ""
            lines.append(f"Partí{via} ({d})")
        elif typ == "arrive":
            lines.append("¡Llegaste a tu destino!")
        else:
            act  = _STEP_TYPE_ES.get(typ, "Continuás")
            mod_s = _STEP_MOD_ES.get(mod, "")
            via  = f" por {name}" if name else ""
            parts = [act]
            if mod_s:
                parts.append(mod_s)
            parts_str = " ".join(parts)
            lines.append(f"{parts_str}{via} ({d})")
    remaining = len(steps) - max_steps
    if remaining > 0:
        lines.append(f"… y {remaining} pasos más.")
    return lines


def _log(player, msg: str):
    print(f"[Maps] {msg}")
    if player:
        try:
            player.write_log(f"[maps] {msg}")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
# Guardar / listar lugares en memoria
# ═══════════════════════════════════════════════════════════
def _save_place_to_memory(name: str, address: str) -> str:
    """Guarda un lugar en la categoría 'places' de la memoria de NEXO."""
    if not _HAS_MEMORY:
        return "❌ El sistema de memoria no está disponible."
    try:
        key = name.lower().strip().replace(" ", "_")
        update_memory({"places": {key: {"value": address, "display": name}}})
        return f"✅ Guardé '{name}' como: {address}"
    except Exception as e:
        return f"❌ No pude guardar el lugar: {e}"


def _list_saved_places() -> str:
    """Lista los lugares guardados en la memoria."""
    if not _HAS_MEMORY:
        return "El sistema de memoria no está disponible."
    try:
        memory = load_memory()
        places = memory.get("places", {})
        if not isinstance(places, dict) or not places:
            return "No tenés lugares guardados. Podés pedirme que guarde uno diciendo 'guardá mi casa como Av. Rivadavia 1234, Flores'."
        lines = ["📍 Tus lugares guardados:\n"]
        for key, val in places.items():
            if isinstance(val, dict):
                display = val.get("display", key.replace("_", " ").title())
                address = val.get("value", "—")
            else:
                display = key.replace("_", " ").title()
                address = str(val)
            lines.append(f"  • {display}: {address}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error listando lugares: {e}"


# ═══════════════════════════════════════════════════════════
# Función principal
# ═══════════════════════════════════════════════════════════
def google_maps(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    if not _REQ:
        return (
            "❌ El módulo 'requests' no está instalado. "
            "Ejecutá: pip install requests"
        )

    params = parameters or {}
    action = params.get("action", "directions").lower().strip()

    # ── Guardar lugar en memoria ──────────────────────────
    if action in ("save_place", "guardar_lugar", "save", "guardar", "remember_place"):
        name    = params.get("name", params.get("place_name", "")).strip()
        address = params.get("address", params.get("destination", "")).strip()

        if not name:
            return "❌ Decime cómo querés llamar a este lugar. Ejemplo: 'mi gym', 'la facu', 'casa de mamá'."
        if not address:
            return f"❌ Decime la dirección de '{name}'. Ejemplo: 'Av. Corrientes 1234, CABA'."

        # Si tiene dirección, geocodificarla para validarla y obtener nombre oficial
        try:
            _log(player, f"Validando dirección: {address}")
            _, _, display = _smart_geocode(_add_ba(address), player)
            # Usar la dirección original del usuario (más legible) pero validada
            result = _save_place_to_memory(name, address)
            return f"{result}\n📍 Verificado: {display[:80]}"
        except Exception:
            # Guardar igual sin validar
            result = _save_place_to_memory(name, address)
            return result

    # ── Listar lugares guardados ──────────────────────────
    if action in ("list_places", "listar_lugares", "mis_lugares", "places",
                  "lista", "ver_lugares", "saved_places"):
        return _list_saved_places()

    # ── Buscar lugar / mostrar en mapa ────────────────────
    if action in ("search", "buscar", "lugar", "place", "ver", "mostrar"):
        query = params.get("query", params.get("place", params.get("destination", ""))).strip()
        if not query:
            return "❌ Decime qué lugar querés ver en el mapa."

        _log(player, f"Buscando: {query}")
        query_resolved = _resolve_alias(query)
        query_with_city = _add_ba(query_resolved)
        gmaps_url = _build_gmaps_search_url(query_with_city)

        if player:
            try:
                player.write_log(f"__maps__:{json.dumps({
                    'origin': '', 'destination': query,
                    'origin_display': '', 'dest_display': query_resolved[:60],
                    'duration': '', 'distance': '', 'mode': '📍',
                    'steps': [], 'url': gmaps_url,
                })}")
            except Exception as e:
                print(f"[Maps] search dashboard error: {e}")

        try:
            lat, lon, display = _smart_geocode(query_with_city, player)
            # Extraer ciudad/barrio del display name para respuesta corta
            parts = display.split(",")
            short = ", ".join(parts[:3]) if len(parts) >= 3 else display[:70]
            return (
                f"📍 Encontré '{query_resolved}': {short}\n"
                f"   Coordenadas: {lat:.5f}, {lon:.5f}\n"
                f"   El mapa ya está abierto en NEXO."
            )
        except ValueError as e:
            return f"❌ {e}"

    # ── Directions / Ruta ─────────────────────────────────
    if action in ("directions", "route", "navigate", "ruta", "navegar",
                  "como llegar", "cómo llegar", "ir", "llegar"):

        origin      = params.get("origin", "").strip()
        destination = params.get("destination", "").strip()
        mode        = params.get("mode", "car").strip().lower()
        save_dest   = params.get("save_as", "").strip()   # opcional: guardar destino en memoria

        if not destination:
            return (
                "❌ Necesito saber a dónde querés ir. "
                "Decime algo como: 'Llevame al Obelisco' o "
                "'Cómo llego de Palermo al shopping de Flores'."
            )

        # Si no hay origen, intentar "mi casa" o dejar en blanco (Google Maps usa ubicación actual)
        if not origin:
            # Intentar desde memoria
            origin_from_memory = _resolve_alias("mi casa")
            if origin_from_memory != "mi casa":
                origin = origin_from_memory
                _log(player, f"Usando casa como origen: {origin}")
            # Si no hay casa guardada, dejar vacío → Google Maps pedirá ubicación actual

        _log(player, f"Ruta: '{origin or '(ubicación actual)'}' → '{destination}' [{mode}]")

        # Geocodificar en paralelo para mayor velocidad
        travelmode = _MODE_MAP_GOOGLE.get(mode, "driving")
        mode_icon  = _MODE_ICON.get(travelmode, "🚗")
        mode_name  = _MODE_NAME_ES.get(travelmode, "en auto")

        # Origen y destino con ciudad agregada
        origin_q      = _add_ba(origin)      if origin else ""
        destination_q = _add_ba(destination)

        # Geocodificar concurrentemente
        geo_err_o = geo_err_d = None
        olat = olon = dlat = dlon = 0.0
        o_display = d_display = ""

        def _geo_origin():
            if not origin_q:
                return None
            return _smart_geocode(origin_q, player)

        def _geo_dest():
            return _smart_geocode(destination_q, player)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            fut_o = ex.submit(_geo_origin)
            fut_d = ex.submit(_geo_dest)
            try:
                res_o = fut_o.result(timeout=12)
                if res_o:
                    olat, olon, o_display = res_o
            except Exception as e:
                geo_err_o = str(e)
            try:
                dlat, dlon, d_display = fut_d.result(timeout=12)
            except Exception as e:
                geo_err_d = str(e)

        if geo_err_d:
            return (
                f"❌ No pude encontrar '{destination}' en el mapa. "
                f"Probá con el nombre más específico, por ejemplo incluyendo el barrio.\n"
                f"Detalle: {geo_err_d}"
            )
        if origin and geo_err_o:
            return f"❌ No pude encontrar el origen '{origin}'.\nDetalle: {geo_err_o}"

        # Construir URL de Google Maps (usa display names reales para mayor precisión)
        gmaps_origin = o_display.split(",")[0] + ", " + (
            origin_q if not o_display else ", ".join(o_display.split(",")[:2])
        ) if o_display else origin_q
        gmaps_dest   = ", ".join(d_display.split(",")[:2]) if d_display else destination_q
        gmaps_url    = _build_gmaps_url(
            gmaps_origin or origin_q or "Mi ubicación",
            gmaps_dest or destination_q,
            mode
        )

        # Obtener ruta con OSRM (para datos de voz / texto)
        route_data = dur_str = dist_str = None
        ui_steps: list[dict] = []

        if origin_q:  # Solo calculamos OSRM si tenemos origen concreto
            try:
                route_data = _get_route_osrm(
                    (olat, olon), (dlat, dlon), mode
                )
                dur_str  = _fmt_duration(int(route_data["duration"]))
                dist_str = _fmt_distance(route_data["distance"])

                steps_raw = []
                for leg in route_data.get("legs", [{}]):
                    steps_raw.extend(leg.get("steps", []))

                for step in steps_raw:
                    m = step.get("maneuver", {})
                    ui_steps.append({
                        "type":         m.get("type", ""),
                        "modifier":     m.get("modifier", ""),
                        "name":         (step.get("name", "") or "").strip(),
                        "distance_str": _fmt_distance(step.get("distance", 0)),
                    })
            except Exception as osrm_err:
                _log(player, f"OSRM no disponible: {osrm_err}")
                # No es crítico — la URL de Google Maps igual funciona

        # Nombre corto de origen/destino para la respuesta
        def _short_name(query_orig: str, display: str) -> str:
            """Nombre legible: usa el query original si es corto, si no el primer campo del display."""
            if len(query_orig) <= 40:
                return query_orig
            return display.split(",")[0].strip() if display else query_orig

        orig_name = _short_name(origin or "tu ubicación", o_display)
        dest_name = _short_name(destination, d_display)

        # Enviar datos al widget del dashboard
        if player:
            try:
                player.write_log(f"__maps__:{json.dumps({
                    'origin':         orig_name,
                    'destination':    dest_name,
                    'origin_display': o_display[:70],
                    'dest_display':   d_display[:70],
                    'duration':       dur_str or "",
                    'distance':       dist_str or "",
                    'mode':           mode_icon,
                    'mode_name':      mode_name,
                    'steps':          ui_steps,
                    'url':            gmaps_url,
                })}")
            except Exception as map_err:
                print(f"[Maps] dashboard error: {map_err}")

        # Guardar destino en memoria si el usuario lo pidió
        if save_dest:
            _save_place_to_memory(save_dest, destination)

        # ── Respuesta en lenguaje natural ──────────────────
        if dur_str and dist_str:
            step_lines = _steps_to_text(
                [s for s in ui_steps if s.get("type") not in ("depart",)],
                max_steps=5
            )
            resp = (
                f"¡Listo! La ruta de {orig_name} a {dest_name} {mode_name} "
                f"te lleva {dur_str} y son {dist_str}.\n\n"
                f"Indicaciones principales:\n"
            )
            resp += "\n".join(f"  {i+1}. {s}" for i, s in enumerate(step_lines))
            resp += "\n\nEl mapa completo ya está abierto en NEXO."
        else:
            # Sin OSRM (sin origen concreto o falla de red)
            resp = (
                f"¡Listo! Abrí Google Maps con la ruta hacia {dest_name} {mode_name}. "
                f"Fijate en el widget del mapa para ver las indicaciones completas."
            )

        return resp

    # ── Acción no reconocida ──────────────────────────────
    return (
        f"No entendí la acción de Maps '{action}'. "
        "Podés pedirme: '¿cómo llego a [lugar]?', 'mostrá [lugar] en el mapa', "
        "'guardá mi gym como [dirección]', o 'listá mis lugares guardados'."
    )
