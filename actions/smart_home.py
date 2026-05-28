"""
smart_home.py — Control de dispositivos del hogar para NEXO.

Protocolos soportados:
  • Tuya / Smart Life  → tinytuya  (más común en Latinoamérica)
  • Philips Hue        → phue
  • LIFX               → lifxlan
  • Yeelight / Xiaomi  → yeelight
  • TPLink / Kasa      → python-kasa
  • Govee              → govee-api-laggat  (beta, local UDP)

Configuración en: config/smart_home.json
"""
from __future__ import annotations

import json
import sys
import re
import time
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_CFG_FILE = _BASE / "config" / "smart_home.json"

# ── Colores nombrados ─────────────────────────────────────────────────────────
_NAMED_COLORS: dict[str, tuple[int, int, int]] = {
    "rojo":    (255, 0,   0),   "red":     (255, 0,   0),
    "verde":   (0,   255, 0),   "green":   (0,   255, 0),
    "azul":    (0,   0,   255), "blue":    (0,   0,   255),
    "blanco":  (255, 255, 255), "white":   (255, 255, 255),
    "cálido":  (255, 180, 80),  "warm":    (255, 180, 80),
    "frio":    (200, 220, 255), "cool":    (200, 220, 255),
    "amarillo":(255, 220, 0),   "yellow":  (255, 220, 0),
    "naranja": (255, 100, 0),   "orange":  (255, 100, 0),
    "rosa":    (255, 80,  150), "pink":    (255, 80,  150),
    "violeta": (128, 0,   255), "purple":  (128, 0,   255),
    "cyan":    (0,   255, 255), "celeste": (0,   200, 255),
    "magenta": (255, 0,   255),
    "negro":   (0,   0,   0),   "black":   (0,   0,   0),
    "apagado": (0,   0,   0),   "off":     (0,   0,   0),
}


def _parse_color(color_str: str) -> tuple[int, int, int]:
    low = color_str.lower().strip()
    if low in _NAMED_COLORS:
        return _NAMED_COLORS[low]
    m = re.match(r"#?([0-9a-fA-F]{6})", low)
    if m:
        h = m.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    m = re.match(r"rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", low)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return (255, 255, 255)


def _rgb_to_hsv(r, g, b) -> tuple[int, int, int]:
    """Convierte RGB (0-255) a HSV (h:0-360, s:0-100, v:0-100)."""
    r_, g_, b_ = r / 255, g / 255, b / 255
    cmax = max(r_, g_, b_)
    cmin = min(r_, g_, b_)
    delta = cmax - cmin
    if delta == 0:
        h = 0
    elif cmax == r_:
        h = 60 * (((g_ - b_) / delta) % 6)
    elif cmax == g_:
        h = 60 * ((b_ - r_) / delta + 2)
    else:
        h = 60 * ((r_ - g_) / delta + 4)
    s = 0 if cmax == 0 else (delta / cmax) * 100
    v = cmax * 100
    return int(h), int(s), int(v)


def _load_cfg() -> dict:
    try:
        return json.loads(_CFG_FILE.read_text("utf-8"))
    except Exception:
        return {}


def _save_cfg(cfg: dict):
    _CFG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CFG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")


def _log(player, msg: str):
    print(f"[SmartHome] {msg}")
    if player:
        player.write_log(f"[home] {msg}")


# ── TUYA / Smart Life ─────────────────────────────────────────────────────────

def _tuya_control(action: str, params: dict, player=None) -> str:
    try:
        import tinytuya
    except ImportError:
        return "❌ tinytuya no instalado. Ejecutá: pip install tinytuya"

    cfg = _load_cfg().get("tuya", {})
    devices_cfg = cfg.get("devices", [])

    if not devices_cfg:
        return (
            "❌ No hay dispositivos Tuya configurados.\n"
            "Usá action=setup para ver cómo configurar los dispositivos Tuya/Smart Life."
        )

    device_filter = params.get("device", params.get("room", "")).lower().strip()
    targets = [
        d for d in devices_cfg
        if not device_filter
        or device_filter in d.get("name", "").lower()
        or device_filter in d.get("room", "").lower()
    ]
    if not targets:
        names = ", ".join(d.get("name", "?") for d in devices_cfg)
        return f"❌ No se encontró dispositivo '{device_filter}'. Disponibles: {names}"

    results = []
    for dev_cfg in targets:
        dev_id  = dev_cfg.get("id", "")
        dev_ip  = dev_cfg.get("ip", "")
        dev_key = dev_cfg.get("key", "")
        dev_ver = str(dev_cfg.get("version", "3.3"))
        dev_name = dev_cfg.get("name", dev_id)

        if not dev_id or not dev_key:
            results.append(f"  ⚠️ {dev_name}: configuración incompleta (falta id o key).")
            continue

        try:
            d = tinytuya.BulbDevice(dev_id, dev_ip, dev_key)
            d.set_version(float(dev_ver))

            if action in ("on", "encender", "prender"):
                d.turn_on()
                results.append(f"  💡 {dev_name}: encendida.")

            elif action in ("off", "apagar"):
                d.turn_off()
                results.append(f"  🌑 {dev_name}: apagada.")

            elif action in ("toggle", "alternar"):
                status = d.status()
                is_on = status.get("dps", {}).get("1", False)
                if is_on:
                    d.turn_off()
                    results.append(f"  🌑 {dev_name}: apagada.")
                else:
                    d.turn_on()
                    results.append(f"  💡 {dev_name}: encendida.")

            elif action in ("color", "set_color", "colour"):
                color_str = params.get("color", "white")
                r, g, b   = _parse_color(color_str)
                h, s, v   = _rgb_to_hsv(r, g, b)
                d.set_colour(h, s, v)
                results.append(f"  🎨 {dev_name}: color → {color_str.upper()} ({r},{g},{b}).")

            elif action in ("brightness", "brillo"):
                value = max(10, min(1000, int(params.get("value", params.get("brightness", 500)))))
                d.set_brightness(value)
                pct = int(value / 10)
                results.append(f"  💡 {dev_name}: brillo → {pct}%.")

            elif action in ("temperature", "temperatura", "temp_color"):
                value = max(0, min(1000, int(params.get("value", 500))))
                d.set_colourtemp(value)
                desc = "cálida" if value < 400 else ("neutra" if value < 700 else "fría")
                results.append(f"  🌡 {dev_name}: temperatura de color → {desc}.")

            elif action in ("scene", "escena", "modo"):
                scene = params.get("scene", "").lower()
                _scene_map = {
                    "relajar": 1, "relax": 1,
                    "leer": 2,    "read": 2,
                    "trabajar": 3, "work": 3,
                    "noche": 4,   "night": 4,
                    "party": 5,   "fiesta": 5,
                }
                scene_id = _scene_map.get(scene, 1)
                d.set_scene(scene_id)
                results.append(f"  ✨ {dev_name}: escena '{scene}' aplicada.")

            elif action in ("status", "estado"):
                st  = d.status()
                dps = st.get("dps", {})
                on_ = dps.get("1", "?")
                br  = dps.get("3", "?")
                results.append(
                    f"  📊 {dev_name}: {'encendida' if on_ else 'apagada'}"
                    + (f", brillo {int(br)/10:.0f}%" if br != "?" else "")
                    + "."
                )
            else:
                results.append(f"  ❓ Acción desconocida: '{action}'.")

        except Exception as e:
            results.append(f"  ❌ {dev_name}: {e}")

    return "🏠 Tuya/Smart Life:\n" + "\n".join(results) if results else "Sin resultados."


# ── PHILIPS HUE ───────────────────────────────────────────────────────────────

def _hue_control(action: str, params: dict, player=None) -> str:
    try:
        from phue import Bridge
    except ImportError:
        return "❌ phue no instalado. Ejecutá: pip install phue"

    cfg     = _load_cfg().get("hue", {})
    hue_ip  = cfg.get("bridge_ip", "")
    if not hue_ip:
        return (
            "❌ No hay IP del Hue Bridge configurada.\n"
            "Agregá 'bridge_ip' en config/smart_home.json bajo la clave 'hue'."
        )

    try:
        bridge = Bridge(hue_ip)
        bridge.connect()
    except Exception as e:
        return (
            f"❌ No se pudo conectar al Hue Bridge ({hue_ip}): {e}\n"
            "Asegurate de que el Bridge esté encendido y en la misma red."
        )

    lights      = bridge.get_light_objects("name")
    room_filter = params.get("device", params.get("room", "")).lower().strip()
    group_filter = params.get("group", "").lower().strip()

    # Seleccionar luces objetivo
    if group_filter:
        groups = bridge.get_group()
        gid    = next(
            (k for k, v in groups.items() if group_filter in v.get("name", "").lower()),
            None,
        )
        if gid:
            light_ids = groups[gid]["lights"]
            targets = {
                n: l for n, l in lights.items()
                if str(bridge.get_light_id_by_name(n)) in light_ids
            }
        else:
            targets = lights
    elif room_filter:
        targets = {n: l for n, l in lights.items() if room_filter in n.lower()}
        if not targets:
            targets = lights
    else:
        targets = lights

    if not targets:
        return "❌ No se encontraron luces Hue. Verificá la configuración."

    results = []
    for light_name, light in targets.items():
        try:
            if action in ("on", "encender", "prender"):
                bridge.set_light(light_name, "on", True)
                results.append(f"  💡 {light_name}: encendida.")

            elif action in ("off", "apagar"):
                bridge.set_light(light_name, "on", False)
                results.append(f"  🌑 {light_name}: apagada.")

            elif action in ("toggle", "alternar"):
                current = light.on
                bridge.set_light(light_name, "on", not current)
                results.append(f"  {'🌑' if current else '💡'} {light_name}: {'apagada' if current else 'encendida'}.")

            elif action in ("color", "set_color"):
                import colorsys
                color_str  = params.get("color", "white")
                r, g, b    = _parse_color(color_str)
                r_, g_, b_ = r / 255, g / 255, b / 255
                h, s, v    = colorsys.rgb_to_hsv(r_, g_, b_)
                bridge.set_light(light_name, {
                    "on":  True,
                    "hue": int(h * 65535),
                    "sat": int(s * 254),
                    "bri": int(v * 254),
                })
                results.append(f"  🎨 {light_name}: color → {color_str.upper()}.")

            elif action in ("brightness", "brillo"):
                pct = max(1, min(100, int(params.get("value", params.get("brightness", 100)))))
                bri = int(pct / 100 * 254)
                bridge.set_light(light_name, {"on": True, "bri": bri})
                results.append(f"  💡 {light_name}: brillo → {pct}%.")

            elif action in ("temperature", "temperatura", "temp_color"):
                # Kelvin a Mired: ct = 1_000_000 / K  (rango Hue: 153-500)
                kelvin = int(params.get("value", 4000))
                ct     = max(153, min(500, int(1_000_000 / kelvin)))
                bridge.set_light(light_name, {"on": True, "ct": ct})
                results.append(f"  🌡 {light_name}: temperatura → {kelvin}K.")

            elif action in ("scene", "escena"):
                # Hue scenes se identifican por nombre
                scene_name = params.get("scene", "")
                all_scenes = bridge.get_scene()
                scene_id   = next(
                    (k for k, v in all_scenes.items()
                     if scene_name.lower() in v.get("name", "").lower()),
                    None,
                )
                if scene_id:
                    bridge.activate_scene("0", scene_id)
                    results.append(f"  ✨ Escena '{scene_name}' activada.")
                else:
                    results.append(f"  ❓ Escena '{scene_name}' no encontrada.")

            elif action in ("status", "estado"):
                state = light.on
                bri   = getattr(light, "brightness", "?")
                results.append(
                    f"  📊 {light_name}: {'encendida' if state else 'apagada'}"
                    + (f", brillo {int(bri)/254*100:.0f}%" if bri != "?" else "") + "."
                )
        except Exception as e:
            results.append(f"  ❌ {light_name}: {e}")

    return "🏠 Philips Hue:\n" + "\n".join(results) if results else "Sin resultados."


# ── LIFX ──────────────────────────────────────────────────────────────────────

def _lifx_control(action: str, params: dict, player=None) -> str:
    try:
        from lifxlan import LifxLAN, Light
    except ImportError:
        return "❌ lifxlan no instalado. Ejecutá: pip install lifxlan"

    device_filter = params.get("device", params.get("room", "")).lower().strip()

    try:
        lan    = LifxLAN()
        lights = lan.get_lights()
        if not lights:
            return "❌ No se encontraron bombillas LIFX en la red."

        if device_filter:
            targets = [l for l in lights if device_filter in (l.get_label() or "").lower()]
            if not targets:
                targets = lights
        else:
            targets = lights

        results = []
        for light in targets:
            label = light.get_label() or "LIFX"
            try:
                if action in ("on", "encender", "prender"):
                    light.set_power("on")
                    results.append(f"  💡 {label}: encendida.")

                elif action in ("off", "apagar"):
                    light.set_power("off")
                    results.append(f"  🌑 {label}: apagada.")

                elif action in ("color", "set_color"):
                    color_str = params.get("color", "white")
                    r, g, b   = _parse_color(color_str)
                    h, s, v   = _rgb_to_hsv(r, g, b)
                    # LIFX: hue 0-65535, sat 0-65535, bri 0-65535, kelvin 2500-9000
                    hue_val = int(h / 360 * 65535)
                    sat_val = int(s / 100 * 65535)
                    bri_val = int(v / 100 * 65535)
                    light.set_color([hue_val, sat_val, bri_val, 4000])
                    results.append(f"  🎨 {label}: color → {color_str.upper()}.")

                elif action in ("brightness", "brillo"):
                    pct     = max(1, min(100, int(params.get("value", params.get("brightness", 100)))))
                    bri_val = int(pct / 100 * 65535)
                    color   = list(light.get_color())
                    color[2] = bri_val
                    light.set_color(color)
                    results.append(f"  💡 {label}: brillo → {pct}%.")

                elif action in ("status", "estado"):
                    pwr = light.get_power()
                    results.append(f"  📊 {label}: {'encendida' if pwr else 'apagada'}.")

            except Exception as e:
                results.append(f"  ❌ {label}: {e}")

        return "🏠 LIFX:\n" + "\n".join(results)

    except Exception as e:
        return f"❌ Error LIFX: {e}"


# ── YEELIGHT ──────────────────────────────────────────────────────────────────

def _yeelight_control(action: str, params: dict, player=None) -> str:
    try:
        from yeelight import Bulb, discover_bulbs
    except ImportError:
        return "❌ yeelight no instalado. Ejecutá: pip install yeelight"

    cfg           = _load_cfg().get("yeelight", {})
    device_filter = params.get("device", params.get("room", "")).lower().strip()
    configured    = cfg.get("bulbs", [])

    # Intentar descubrimiento si no hay config manual
    if not configured:
        try:
            discovered = discover_bulbs(timeout=3)
            configured = [{"ip": b["ip"], "name": b.get("capabilities", {}).get("id", b["ip"])}
                          for b in discovered]
        except Exception:
            pass

    if not configured:
        return (
            "❌ No se encontraron bombillas Yeelight. "
            "Agregá las IPs en config/smart_home.json bajo 'yeelight.bulbs', "
            "o asegurate de que las bombillas estén en la misma red con 'LAN Control' activado."
        )

    targets = [
        b for b in configured
        if not device_filter or device_filter in b.get("name", b.get("ip", "")).lower()
    ]
    if not targets:
        targets = configured

    results = []
    for bulb_cfg in targets:
        ip    = bulb_cfg.get("ip", "")
        name  = bulb_cfg.get("name", ip)
        if not ip:
            continue
        try:
            bulb = Bulb(ip)
            if action in ("on", "encender", "prender"):
                bulb.turn_on()
                results.append(f"  💡 {name}: encendida.")
            elif action in ("off", "apagar"):
                bulb.turn_off()
                results.append(f"  🌑 {name}: apagada.")
            elif action in ("color", "set_color"):
                color_str = params.get("color", "white")
                r, g, b   = _parse_color(color_str)
                bulb.set_rgb(r, g, b)
                results.append(f"  🎨 {name}: color → {color_str.upper()}.")
            elif action in ("brightness", "brillo"):
                pct = max(1, min(100, int(params.get("value", params.get("brightness", 100)))))
                bulb.set_brightness(pct)
                results.append(f"  💡 {name}: brillo → {pct}%.")
            elif action in ("temperature", "temperatura", "temp_color"):
                k = max(1700, min(6500, int(params.get("value", 4000))))
                bulb.set_color_temp(k)
                results.append(f"  🌡 {name}: temperatura → {k}K.")
            elif action in ("status", "estado"):
                props = bulb.get_properties()
                pwr   = props.get("power", "?")
                bri   = props.get("bright", "?")
                results.append(f"  📊 {name}: {pwr}, brillo {bri}%.")
            else:
                results.append(f"  ❓ Acción desconocida: '{action}'.")
        except Exception as e:
            results.append(f"  ❌ {name} ({ip}): {e}")

    return "🏠 Yeelight:\n" + "\n".join(results) if results else "Sin resultados."


# ── SETUP GUIDE ───────────────────────────────────────────────────────────────

def _show_setup() -> str:
    template = {
        "protocol": "tuya",
        "tuya": {
            "devices": [
                {
                    "name": "Lámpara sala",
                    "room": "sala",
                    "id": "TU_DEVICE_ID",
                    "ip": "192.168.1.100",
                    "key": "TU_LOCAL_KEY",
                    "version": "3.3"
                }
            ]
        },
        "hue": {
            "bridge_ip": "192.168.1.50"
        },
        "yeelight": {
            "bulbs": [
                {"ip": "192.168.1.101", "name": "Lampara cuarto"}
            ]
        }
    }
    return (
        "⚙️ Configuración Smart Home — config/smart_home.json:\n\n"
        f"{json.dumps(template, indent=2, ensure_ascii=False)}\n\n"
        "📌 TUYA/Smart Life:\n"
        "  1. Instalá la app Smart Life y agrega los dispositivos.\n"
        "  2. Usá 'tinytuya wizard' o IoT Platform (iot.tuya.com) para obtener device_id y local_key.\n"
        "  3. La IP la encontrás en el router o con 'python -m tinytuya scan'.\n\n"
        "📌 PHILIPS HUE:\n"
        "  1. Encontrá la IP del Bridge en la app Hue → Configuración → Hue Bridges.\n"
        "  2. La primera vez, presioná el botón del Bridge cuando NEXO intente conectar.\n\n"
        "📌 YEELIGHT:\n"
        "  1. En la app Yeelight → dispositivo → Ajustes → LAN Control → Activar.\n"
        "  2. La IP aparece en la misma sección o en el router.\n\n"
        "📌 LIFX:\n"
        "  No requiere configuración — las bombillas se descubren automáticamente en la red local."
    )


# ── DISPATCHER ────────────────────────────────────────────────────────────────

def smart_home(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params   = parameters or {}
    action   = params.get("action", "").lower().strip()
    protocol = params.get("protocol", "").lower().strip()

    if action in ("setup", "configurar", "config", "help", "ayuda"):
        return _show_setup()

    if action in ("list", "listar", "dispositivos", "devices"):
        cfg      = _load_cfg()
        proto    = cfg.get("protocol", "")
        lines    = [f"📋 Protocolo activo: {proto or 'no configurado'}"]
        tuya_devs = cfg.get("tuya", {}).get("devices", [])
        if tuya_devs:
            lines.append("\nTuya/Smart Life:")
            for d in tuya_devs:
                lines.append(f"  • {d.get('name','?')} ({d.get('room','sin sala')}) — IP {d.get('ip','?')}")
        hue_ip   = cfg.get("hue", {}).get("bridge_ip", "")
        if hue_ip:
            lines.append(f"\nPhilips Hue Bridge: {hue_ip}")
        yeelight = cfg.get("yeelight", {}).get("bulbs", [])
        if yeelight:
            lines.append("\nYeelight:")
            for b in yeelight:
                lines.append(f"  • {b.get('name','?')} ({b.get('ip','?')})")
        if len(lines) == 1:
            lines.append("\n(Ningún dispositivo configurado. Usá action=setup para ver cómo configurar.)")
        return "\n".join(lines)

    # Determinar protocolo a usar
    cfg = _load_cfg()
    if not protocol:
        protocol = cfg.get("protocol", "tuya")

    if not action:
        return "❌ Especificá action: on, off, toggle, color, brightness, temperature, scene, status, list, setup."

    _log(player, f"[{protocol}] {action} — params: {params}")

    if protocol in ("tuya", "smart_life", "smartlife"):
        return _tuya_control(action, params, player)
    elif protocol in ("hue", "philips", "philips_hue"):
        return _hue_control(action, params, player)
    elif protocol in ("lifx",):
        return _lifx_control(action, params, player)
    elif protocol in ("yeelight", "xiaomi", "mi"):
        return _yeelight_control(action, params, player)
    else:
        # Intentar todos los protocolos configurados
        results = []
        if cfg.get("tuya", {}).get("devices"):
            r = _tuya_control(action, params, player)
            results.append(r)
        if cfg.get("hue", {}).get("bridge_ip"):
            r = _hue_control(action, params, player)
            results.append(r)
        if cfg.get("yeelight", {}).get("bulbs"):
            r = _yeelight_control(action, params, player)
            results.append(r)
        if results:
            return "\n\n".join(results)
        return (
            "❌ No hay dispositivos de hogar configurados. "
            "Usá action=setup para ver cómo configurar tus luces."
        )
