"""
windows_settings.py — Control total de configuraciones de Windows para NEXO.

Categorías:
  pantalla      → brillo, resolución, escalado, monitores, noche, HDR
  audio         → volumen, dispositivos, spatial audio, mic
  red           → WiFi, Bluetooth, VPN, modo avión, proxy, DNS
  energia       → plan de energía, suspensión, hibernación, batería
  sistema       → info, nombre PC, fecha/hora, zona horaria, idioma
  apps          → inicio, predeterminadas, desinstalar, listar
  personalizacion → fondo, tema, colores, barra de tareas, pantalla bloqueo
  seguridad     → Defender, firewall, UAC, BitLocker
  accesibilidad → lupa, narrador, contraste, puntero, teclas
  mouse         → velocidad, botones, doble click, rueda
  teclado       → velocidad, layout, idioma
  almacenamiento→ discos, limpieza, papelera, temp
  servicios     → listar, iniciar, detener, reiniciar
  procesos      → listar, terminar, prioridad
  actualizaciones → verificar, historial
  notificaciones → no molestar, focus assist
  registro      → leer, escribir, eliminar clave
  variables     → env vars get/set/delete
  portapapeles  → limpiar, historial
  fuentes       → listar, instalar
  impresoras    → listar, predeterminar
  privacidad    → cámara, micrófono, ubicación, telemetría
  rendimiento   → efectos visuales, memoria virtual
"""
from __future__ import annotations

import os
import subprocess
import winreg
from pathlib import Path

# Native Win32 API modules (optional — graceful fallback to PowerShell)
try:
    from pycaw.pycaw import AudioUtilities
    _HAS_PYCAW = True
except Exception:
    _HAS_PYCAW = False

try:
    import wmi
    _HAS_WMI = True
except Exception:
    _HAS_WMI = False

try:
    import psutil
    _HAS_PSUTIL = True
except Exception:
    _HAS_PSUTIL = False


def _ps(cmd: str, timeout: int = 15) -> str:
    """Ejecuta PowerShell y retorna stdout limpio."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode != 0 and not out and err:
            return f"[Error] {err[:300]}"
        return out
    except subprocess.TimeoutExpired:
        return "[Error] Timeout al ejecutar PowerShell."
    except Exception as e:
        return f"[Error] {e}"


def _cmd(cmd: str, timeout: int = 10) -> str:
    """Ejecuta cmd.exe y retorna stdout."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        return (r.stdout or "").strip()
    except Exception as e:
        return f"[Error] {e}"


def _reg_read(hive, key_path: str, value_name: str):
    hive_map = {
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKCR": winreg.HKEY_CLASSES_ROOT,
    }
    h = hive_map.get(hive.upper(), winreg.HKEY_CURRENT_USER)
    try:
        key = winreg.OpenKey(h, key_path, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, value_name)
        winreg.CloseKey(key)
        return val
    except Exception as e:
        return None


def _reg_write(hive, key_path: str, value_name: str, value, reg_type=winreg.REG_SZ):
    hive_map = {
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKCR": winreg.HKEY_CLASSES_ROOT,
    }
    h = hive_map.get(hive.upper(), winreg.HKEY_CURRENT_USER)
    try:
        key = winreg.CreateKeyEx(h, key_path, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, value_name, 0, reg_type, value)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        return str(e)


def _log(player, msg: str):
    print(f"[WinSettings] {msg}")
    if player:
        player.write_log(f"[win] {msg}")


# ══════════════════════════════════════════════════════════════════════════════
# PANTALLA / DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

def _brightness_get_native() -> int | None:
    """Get current brightness via native WMI."""
    if not _HAS_WMI:
        return None
    try:
        c = wmi.WMI(namespace="root/WMI")
        for b in c.WmiMonitorBrightness():
            return b.CurrentBrightness
    except Exception:
        return None


def _brightness_set_native(val: int) -> bool:
    """Set brightness via native WMI."""
    if not _HAS_WMI:
        return False
    try:
        c = wmi.WMI(namespace="root/WMI")
        for m in c.WmiMonitorBrightnessMethods():
            m.WmiSetBrightness(1, max(0, min(100, val)))
            return True
    except Exception:
        return False
    return False


def _display(action: str, params: dict) -> str:
    if action in ("brillo", "brightness"):
        val = params.get("value")
        if val is None:
            v = _brightness_get_native()
            if v is not None:
                return f"💡 Brillo actual: {v}%"
            # Fallback — PowerShell
            out = _ps("(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness")
            return f"💡 Brillo actual: {out}%" if out and not out.startswith("[Error]") else "No se pudo leer el brillo (puede no estar soportado en este monitor)."
        v = int(val)
        if _brightness_set_native(v):
            return f"💡 Brillo ajustado a {v}%."
        _ps(f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{v})")
        return f"💡 Brillo ajustado a {v}%."

    if action in ("resolucion", "resolution"):
        if params.get("value"):
            # Set resolution e.g. "1920x1080"
            parts = str(params["value"]).lower().replace("x", " ").split()
            if len(parts) == 2:
                w, h = parts
                _ps(f"""
Add-Type -AssemblyName System.Windows.Forms
$dm = New-Object System.Windows.Forms.Screen
""")
                # Use Display Settings via pinvoke
                result = _ps(f"""
Add-Type @'
using System;using System.Runtime.InteropServices;
public class Display {{
    [DllImport("user32.dll")] public static extern int ChangeDisplaySettings(ref DEVMODE dm,int flags);
    [StructLayout(LayoutKind.Sequential)] public struct DEVMODE {{
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)] public string dmDeviceName;
        public short dmSpecVersion,dmDriverVersion,dmSize,dmDriverExtra;
        public int dmFields; public short dmOrientation,dmPaperSize,dmPaperLength,dmPaperWidth;
        public short dmScale,dmCopies,dmDefaultSource,dmPrintQuality;
        public short dmColor,dmDuplex,dmYResolution,dmTTOption,dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)] public string dmFormName;
        public short dmLogPixels; public int dmBitsPerPel,dmPelsWidth,dmPelsHeight,dmDisplayFlags,dmDisplayFrequency;
    }}
}}
'@
$d=New-Object Display+DEVMODE; $d.dmSize=[System.Runtime.InteropServices.Marshal]::SizeOf($d);
$d.dmPelsWidth={w}; $d.dmPelsHeight={h}; $d.dmFields=0x180000;
[Display]::ChangeDisplaySettings([ref]$d,0)
""")
                return f"🖥 Resolución cambiada a {w}x{h} (puede tardar un segundo)."
        # List current
        out = _ps("(Get-WmiObject Win32_VideoController | Select-Object CurrentHorizontalResolution,CurrentVerticalResolution,CurrentRefreshRate | Format-List | Out-String).Trim()")
        return f"🖥 Resolución actual:\n{out}"

    if action in ("frecuencia", "refresh_rate", "hz"):
        val = params.get("value")
        if val:
            result = _ps(f"""
Add-Type @'
using System;using System.Runtime.InteropServices;
public class Disp2 {{
    [DllImport("user32.dll")] public static extern int ChangeDisplaySettings(ref DEVMODE2 dm,int flags);
    [StructLayout(LayoutKind.Sequential)] public struct DEVMODE2 {{
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)] public string dmDeviceName;
        public short dmSpecVersion,dmDriverVersion,dmSize,dmDriverExtra;
        public int dmFields; public short dmOrientation,dmPaperSize,dmPaperLength,dmPaperWidth;
        public short dmScale,dmCopies,dmDefaultSource,dmPrintQuality;
        public short dmColor,dmDuplex,dmYResolution,dmTTOption,dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)] public string dmFormName;
        public short dmLogPixels; public int dmBitsPerPel,dmPelsWidth,dmPelsHeight,dmDisplayFlags,dmDisplayFrequency;
    }}
}}
'@
$d=New-Object Disp2+DEVMODE2; $d.dmSize=[System.Runtime.InteropServices.Marshal]::SizeOf($d);
$d.dmDisplayFrequency={val}; $d.dmFields=0x400000;
[Disp2]::ChangeDisplaySettings([ref]$d,0)
""")
            return f"🖥 Frecuencia de refresco ajustada a {val} Hz."
        out = _ps("(Get-WmiObject Win32_VideoController).CurrentRefreshRate")
        return f"🖥 Frecuencia actual: {out} Hz"

    if action in ("escalado", "scaling", "dpi"):
        val = params.get("value", "")
        if val:
            # DPI scaling via registry (100%=96, 125%=120, 150%=144, 175%=168, 200%=192)
            pct_map = {"100": 0, "125": 1, "150": 2, "175": 3, "200": 4,
                       "100%": 0, "125%": 1, "150%": 2, "175%": 3, "200%": 4}
            scale   = pct_map.get(str(val), -1)
            if scale >= 0:
                _reg_write("HKCU",
                           r"Control Panel\Desktop",
                           "LogPixels",
                           [96, 120, 144, 168, 192][scale],
                           winreg.REG_DWORD)
                return f"🖥 Escalado DPI ajustado a {val}%. Reiniciá sesión para aplicar."
        cur = _reg_read("HKCU", r"Control Panel\Desktop", "LogPixels") or 96
        pct = round(cur / 96 * 100)
        return f"🖥 Escalado actual: {pct}% ({cur} DPI)"

    if action in ("monitores", "monitors", "pantallas"):
        out = _ps("Get-WmiObject Win32_VideoController | Select-Object Name,CurrentHorizontalResolution,CurrentVerticalResolution,CurrentRefreshRate | Format-Table -AutoSize | Out-String")
        return f"🖥 Monitores:\n{out}"

    if action in ("noche", "night_light", "filtro_azul"):
        # Toggle Night Light via registry
        enabled = str(params.get("value", "toggle")).lower()
        key     = r"Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount\Current\default$windows.data.bluelightreduction.bluelightreductionstate\windows.data.bluelightreduction.bluelightreductionstate"
        if enabled in ("on", "true", "activar", "1"):
            _ps("Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\CloudStore\\Store\\DefaultAccount\\Current\\default$windows.data.bluelightreduction.settings\\windows.data.bluelightreduction.settings' -Name Data -Type Binary -Value ([byte[]](0x43,0x42,0x01,0x00,0x0A,0x02,0x01,0x00,0x2A,0x06,0xBD,0xB5,0x9B,0x85,0x08,0x12,0x00))")
            return "🌙 Filtro de luz nocturna activado."
        if enabled in ("off", "false", "desactivar", "0"):
            _ps("Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\CloudStore\\Store\\DefaultAccount\\Current\\default$windows.data.bluelightreduction.settings\\windows.data.bluelightreduction.settings' -Name Data -Type Binary -Value ([byte[]](0x43,0x42,0x01,0x00,0x0A,0x02,0x00,0x00,0x2A,0x06,0xBD,0xB5,0x9B,0x85,0x08,0x12,0x00))")
            return "☀️ Filtro de luz nocturna desactivado."
        # Open Night Light settings
        subprocess.Popen("start ms-settings:nightlight", shell=True)
        return "🌙 Configuración de luz nocturna abierta."

    if action in ("hdr",):
        subprocess.Popen("start ms-settings:display-advancedgraphics", shell=True)
        return "🖥 Configuración HDR abierta en Configuración de Windows."

    if action in ("orientacion", "rotation", "orientation"):
        val = params.get("value", "landscape")
        ori_map = {"horizontal": 0, "landscape": 0, "portrait": 1,
                   "vertical": 1, "horizontal_invertido": 2, "portrait_invertido": 3}
        code = ori_map.get(str(val).lower(), 0)
        _ps(f"""
Add-Type @'
using System;using System.Runtime.InteropServices;
public class Rotate {{
    public const int DMDO_DEFAULT=0,DMDO_90=1,DMDO_180=2,DMDO_270=3;
    [DllImport("user32.dll")] public static extern bool EnumDisplaySettings(string n,int m,ref DEVMODE3 dm);
    [DllImport("user32.dll")] public static extern int ChangeDisplaySettings(ref DEVMODE3 dm,int flags);
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Ansi)] public struct DEVMODE3 {{
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)] public string dmDeviceName;
        public short dmSpecVersion,dmDriverVersion,dmSize,dmDriverExtra;
        public int dmFields; public int dmPositionX,dmPositionY,dmDisplayOrientation,dmDisplayFixedOutput;
        public short dmColor,dmDuplex,dmYResolution,dmTTOption,dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)] public string dmFormName;
        public short dmLogPixels; public int dmBitsPerPel,dmPelsWidth,dmPelsHeight,dmDisplayFlags,dmDisplayFrequency;
    }}
}}
'@
$dm=New-Object Rotate+DEVMODE3; $dm.dmSize=[System.Runtime.InteropServices.Marshal]::SizeOf($dm);
[Rotate]::EnumDisplaySettings($null,-1,[ref]$dm); $dm.dmDisplayOrientation={code}; $dm.dmFields=0x80;
[Rotate]::ChangeDisplaySettings([ref]$dm,0)
""")
        return f"🖥 Orientación ajustada ({val})."

    return f"Acción de pantalla desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# AUDIO
# ══════════════════════════════════════════════════════════════════════════════

def _get_audio_endpoint_volume():
    """Return IAudioEndpointVolume for the default playback device using pycaw."""
    if not _HAS_PYCAW:
        return None
    try:
        speakers = AudioUtilities.GetSpeakers()
        return speakers.EndpointVolume
    except Exception:
        return None


def _volume_get() -> int | None:
    dev = _get_audio_endpoint_volume()
    if dev is None:
        return None
    try:
        return round(dev.GetMasterVolumeLevelScalar() * 100)
    except Exception:
        return None


def _volume_set(percent: int) -> bool:
    dev = _get_audio_endpoint_volume()
    if dev is None:
        return False
    try:
        dev.SetMasterVolumeLevelScalar(max(0, min(100, percent)) / 100.0, None)
        return True
    except Exception:
        return False


def _volume_mute() -> bool:
    dev = _get_audio_endpoint_volume()
    if dev is None:
        return False
    try:
        muted = dev.GetMute()
        dev.SetMute(not muted, None)
        return True
    except Exception:
        return False


def _audio(action: str, params: dict) -> str:
    if action in ("volumen", "volume"):
        val = params.get("value")
        if val is None:
            v = _volume_get()
            if v is not None:
                return f"🔊 Volumen actual: {v}%"
            # Fallback — PowerShell
            out = _ps("(Get-AudioDevice -Playback | Get-AudioDeviceVolume).Volume")
            if out and "[Error]" not in out:
                return f"🔊 Volumen actual: {out}%"
            return "🔊 Volumen actual no disponible. Usá 'ajustar volumen a 50' para cambiarlo."
        v = max(0, min(100, int(val)))
        if _volume_set(v):
            return f"🔊 Volumen ajustado a {v}%."
        # Fallback — nircmd / PowerShell SendKeys
        nircmd = _cmd("where nircmd 2>nul")
        if nircmd and "nircmd" in nircmd.lower():
            _cmd(f"nircmd setsysvolume {int(v * 655.35)}")
        else:
            _ps(f"""
$vol = {v} / 100.0
$wscript = New-Object -ComObject WScript.Shell
$steps = [Math]::Round(($vol - 0) / (1/50))
for ($i=0; $i -lt 50; $i++) {{ $wscript.SendKeys([char]174) }}
for ($i=0; $i -lt $steps; $i++) {{ $wscript.SendKeys([char]175) }}
""")
        return f"🔊 Volumen ajustado a {v}%."

    if action in ("mute", "silenciar", "mutear"):
        if _volume_mute():
            return "🔇 Audio silenciado/des-silenciado."
        _ps("""
$wscript = New-Object -ComObject WScript.Shell
$wscript.SendKeys([char]173)
""")
        return "🔇 Audio silenciado/des-silenciado."

    if action in ("dispositivos_audio", "audio_devices", "dispositivos"):
        out = _ps("Get-WmiObject Win32_SoundDevice | Select-Object Name,Status | Format-Table -AutoSize | Out-String")
        return f"🔊 Dispositivos de audio:\n{out}"

    if action in ("dispositivo_predeterminado", "set_default_audio"):
        device = params.get("device", "")
        if device:
            _ps(f"Set-AudioDevice -Name '{device}'")
            return f"🔊 Dispositivo predeterminado cambiado a '{device}'."
        subprocess.Popen("start ms-settings:sound", shell=True)
        return "🔊 Configuración de sonido abierta."

    if action in ("volumen_mic", "mic_volume", "microfono_volumen"):
        val = params.get("value")
        if val:
            _ps(f"""
$mic = Get-WmiObject Win32_SoundDevice | Where-Object {{$_.Name -like '*Microphone*' -or $_.Name -like '*Mic*'}}
""")
            # Open sound control panel for mic
            subprocess.Popen("control mmsys.cpl sounds", shell=True)
            return "🎙 Configuración de micrófono abierta. Ajustá el nivel manualmente por ahora."
        return "🎙 Para ajustar el micrófono, usá las configuraciones de sonido."

    if action in ("sonido_configuracion", "sound_settings"):
        subprocess.Popen("start ms-settings:sound", shell=True)
        return "🔊 Configuración de sonido abierta."

    if action in ("ecualizador", "spatial_audio"):
        subprocess.Popen("start ms-settings:sound-devices", shell=True)
        return "🔊 Configuración de audio espacial abierta."

    return f"Acción de audio desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# RED / NETWORK
# ══════════════════════════════════════════════════════════════════════════════

def _network(action: str, params: dict) -> str:
    if action in ("wifi_list", "redes_wifi", "redes"):
        out = _cmd("netsh wlan show networks mode=Bssid")
        if not out:
            return "No se encontraron redes WiFi. ¿Está el WiFi activado?"
        lines = [l for l in out.splitlines() if "SSID" in l or "Signal" in l or "Authentication" in l]
        return "📶 Redes WiFi disponibles:\n" + "\n".join(lines[:30])

    if action in ("wifi_connect", "conectar_wifi", "conectar"):
        ssid = params.get("ssid", params.get("network", ""))
        pwd  = params.get("password", params.get("contraseña", ""))
        if not ssid:
            return "❌ Especificá el nombre de la red (ssid)."
        if pwd:
            # Create profile XML and connect
            profile_xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
<name>{ssid}</name><SSIDConfig><SSID><name>{ssid}</name></SSID></SSIDConfig>
<connectionType>ESS</connectionType><connectionMode>auto</connectionMode>
<MSM><security><authEncryption><authentication>WPA2PSK</authentication>
<encryption>AES</encryption></authEncryption>
<sharedKey><keyType>passPhrase</keyType><protected>false</protected>
<keyMaterial>{pwd}</keyMaterial></sharedKey></security></MSM></WLANProfile>"""
            tmp = Path(os.environ.get("TEMP", "C:\\Temp")) / "nexo_wifi.xml"
            tmp.write_text(profile_xml, "utf-8")
            _cmd(f'netsh wlan add profile filename="{tmp}" user=all')
            _cmd(f'netsh wlan connect name="{ssid}"')
            tmp.unlink(missing_ok=True)
            return f"📶 Conectando a '{ssid}'..."
        else:
            _cmd(f'netsh wlan connect name="{ssid}"')
            return f"📶 Conectando a '{ssid}' (perfil existente)..."

    if action in ("wifi_disconnect", "desconectar_wifi", "desconectar_red"):
        _cmd("netsh wlan disconnect")
        return "📶 WiFi desconectado."

    if action in ("wifi_off", "wifi_apagar", "apagar_wifi"):
        _cmd("netsh interface set interface Wi-Fi admin=disable")
        return "📶 WiFi desactivado."

    if action in ("wifi_on", "wifi_encender", "encender_wifi"):
        _cmd("netsh interface set interface Wi-Fi admin=enable")
        return "📶 WiFi activado."

    if action in ("wifi_info", "info_red", "red_actual"):
        out = _cmd("netsh wlan show interfaces")
        lines = [l for l in out.splitlines() if any(k in l for k in ("SSID","Signal","Receive","Transmit","State","Authentication"))]
        return "📶 Red WiFi actual:\n" + "\n".join(lines)

    if action in ("ip", "ip_info", "direccion_ip"):
        out = _ps("Get-NetIPAddress | Where-Object {$_.AddressFamily -eq 'IPv4' -and $_.IPAddress -notlike '127.*'} | Select-Object InterfaceAlias,IPAddress,PrefixLength | Format-Table -AutoSize | Out-String")
        pub  = _cmd("curl -s --max-time 3 ifconfig.me") or "no disponible"
        return f"🌐 IPs locales:\n{out}\n🌍 IP pública: {pub}"

    if action in ("dns", "cambiar_dns"):
        dns1 = params.get("dns1", params.get("primary", "8.8.8.8"))
        dns2 = params.get("dns2", params.get("secondary", "8.8.4.4"))
        iface = params.get("interface", "Wi-Fi")
        _ps(f'Set-DnsClientServerAddress -InterfaceAlias "{iface}" -ServerAddresses ("{dns1}","{dns2}")')
        return f"🌐 DNS cambiado a {dns1} / {dns2} en '{iface}'."

    if action in ("dns_reset", "dns_automatico", "dns_auto"):
        iface = params.get("interface", "Wi-Fi")
        _ps(f'Set-DnsClientServerAddress -InterfaceAlias "{iface}" -ResetServerAddresses')
        return f"🌐 DNS de '{iface}' restablecido a automático."

    if action in ("flush_dns", "limpiar_dns", "dns_flush"):
        _cmd("ipconfig /flushdns")
        return "🌐 Caché DNS limpiado."

    if action in ("modo_avion", "airplane_mode"):
        val = str(params.get("value", "toggle")).lower()
        if val in ("on", "activar", "true", "1"):
            _ps("(Get-NetAdapter | Where-Object {$_.Status -ne 'Disabled'}) | Disable-NetAdapter -Confirm:$false")
            return "✈️ Modo avión activado (todos los adaptadores desactivados)."
        if val in ("off", "desactivar", "false", "0"):
            _ps("Get-NetAdapter | Enable-NetAdapter -Confirm:$false")
            return "✈️ Modo avión desactivado."
        subprocess.Popen("start ms-settings:network-airplanemode", shell=True)
        return "✈️ Configuración de modo avión abierta."

    if action in ("bluetooth_on", "bluetooth_activar", "bt_on"):
        _ps("(Get-PnpDevice -Class Bluetooth | Where-Object {$_.Status -ne 'OK'}) | Enable-PnpDevice -Confirm:$false -ErrorAction SilentlyContinue")
        return "🔵 Bluetooth activado."

    if action in ("bluetooth_off", "bluetooth_desactivar", "bt_off"):
        _ps("Get-PnpDevice -Class Bluetooth | Disable-PnpDevice -Confirm:$false -ErrorAction SilentlyContinue")
        return "🔵 Bluetooth desactivado."

    if action in ("bluetooth_devices", "dispositivos_bluetooth", "bt_devices"):
        out = _ps("Get-PnpDevice -Class Bluetooth | Select-Object FriendlyName,Status | Format-Table -AutoSize | Out-String")
        return f"🔵 Dispositivos Bluetooth:\n{out}"

    if action in ("proxy_off", "desactivar_proxy", "sin_proxy"):
        _reg_write("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Internet Settings", "ProxyEnable", 0, winreg.REG_DWORD)
        return "🌐 Proxy desactivado."

    if action in ("proxy_on", "activar_proxy"):
        host = params.get("host", "127.0.0.1")
        port = params.get("port", "8080")
        _reg_write("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Internet Settings", "ProxyEnable", 1, winreg.REG_DWORD)
        _reg_write("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Internet Settings", "ProxyServer", f"{host}:{port}")
        return f"🌐 Proxy activado: {host}:{port}."

    if action in ("velocidad_red", "network_speed", "ping"):
        host = params.get("host", "8.8.8.8")
        out  = _cmd(f"ping -n 4 {host}")
        lines = [l for l in out.splitlines() if "ms" in l.lower() or "perdidos" in l.lower() or "Average" in l.lower() or "Promedio" in l.lower()]
        return f"🌐 Ping a {host}:\n" + "\n".join(lines)

    if action in ("compartir_red", "network_sharing"):
        subprocess.Popen("start ms-settings:network-mobilehotspot", shell=True)
        return "🌐 Configuración de punto de acceso abierta."

    return f"Acción de red desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# ENERGÍA / POWER
# ══════════════════════════════════════════════════════════════════════════════

def _power(action: str, params: dict) -> str:
    if action in ("plan_energia", "power_plan", "plan"):
        val = params.get("value", "").lower()
        plans = {
            "equilibrado": "381b4222-f694-41f0-9685-ff5bb260df2e",
            "balanced":    "381b4222-f694-41f0-9685-ff5bb260df2e",
            "ahorro":      "a1841308-3541-4fab-bc81-f71556f20b4a",
            "powersaver":  "a1841308-3541-4fab-bc81-f71556f20b4a",
            "alto rendimiento": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
            "high performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
            "maximo rendimiento": "e9a42b02-d5df-448d-aa00-03f14749eb61",
            "ultimate":    "e9a42b02-d5df-448d-aa00-03f14749eb61",
        }
        if val and val in plans:
            _cmd_elevated(f"powercfg /setactive {plans[val]}")
            return f"⚡ Plan de energía cambiado a '{val}'."
        # List plans
        out = _cmd("powercfg /list")
        return f"⚡ Planes de energía disponibles:\n{out}"

    if action in ("suspender", "sleep", "suspend"):
        mins = params.get("minutes", params.get("value"))
        if mins:
            _cmd_elevated(f"shutdown /h /t {int(mins)*60}")
            return f"💤 PC se suspenderá en {mins} minutos."
        _cmd_elevated("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        return "💤 Suspendiendo la PC..."

    if action in ("hibernar", "hibernate"):
        _cmd_elevated("shutdown /h")
        return "💤 Hibernando la PC..."

    if action in ("suspender_pantalla", "apagar_pantalla", "screen_off"):
        try:
            import ctypes
            HWND_BROADCAST = 0xFFFF
            WM_SYSCOMMAND = 0x0112
            SC_MONITORPOWER = 0xF170
            ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)
        except Exception:
            _ps("[Power]::SendMessage(0xFFFF,0x0112,0xF170,2)")
        return "🖥 Pantalla apagada."

    if action in ("tiempo_suspension", "sleep_timeout", "sleep_time"):
        val = params.get("value", params.get("minutes", "0"))
        mins = int(val)
        _cmd_elevated(f"powercfg /change standby-timeout-ac {mins}")
        _cmd_elevated(f"powercfg /change standby-timeout-dc {mins}")
        return f"⚡ Tiempo de suspensión ajustado a {mins} minutos (0 = nunca)."

    if action in ("tiempo_pantalla", "screen_timeout", "display_timeout"):
        val = params.get("value", params.get("minutes", "10"))
        mins = int(val)
        _cmd_elevated(f"powercfg /change monitor-timeout-ac {mins}")
        _cmd_elevated(f"powercfg /change monitor-timeout-dc {mins}")
        return f"🖥 Apagado de pantalla en {mins} minutos."

    if action in ("hibernacion_on", "enable_hibernate"):
        _cmd_elevated("powercfg /hibernate on")
        return "💤 Hibernación habilitada."

    if action in ("hibernacion_off", "disable_hibernate"):
        _cmd_elevated("powercfg /hibernate off")
        return "💤 Hibernación deshabilitada."

    if action in ("inicio_rapido", "fast_startup"):
        val = str(params.get("value", "on")).lower()
        v   = 1 if val in ("on", "true", "activar") else 0
        _reg_write("HKLM", r"SYSTEM\CurrentControlSet\Control\Session Manager\Power", "HiberbootEnabled", v, winreg.REG_DWORD)
        return f"⚡ Inicio rápido {'activado' if v else 'desactivado'}. Reiniciá para aplicar."

    if action in ("bateria", "battery", "bateria_info"):
        if _HAS_PSUTIL:
            try:
                batt = psutil.sensors_battery()
                if batt:
                    pct = batt.percent
                    plug = "Conectado" if batt.power_plugged else "Desconectado"
                    remaining = ""
                    if batt.secsleft > 0 and batt.secsleft < psutil.POWER_TIME_UNLIMITED:
                        h, m = divmod(batt.secsleft // 60, 60)
                        remaining = f", restan {h}h {m}m"
                    return f"🔋 Carga: {pct}% ({plug}{remaining})"
                return "🔋 No hay batería (PC de escritorio)."
            except Exception:
                pass
        out = _ps("""
$b = Get-WmiObject Win32_Battery
if ($b) {
    "Carga: $($b.EstimatedChargeRemaining)%`nEstado: $($b.BatteryStatus)`nTiempo restante: $(if($b.EstimatedRunTime -lt 71582788){\"$([Math]::Round($b.EstimatedRunTime/60))h\"}else{'Conectado'})"
} else { 'No hay batería (PC de escritorio).' }
""")
        return f"🔋 {out}"

    if action in ("ahorro_bateria", "battery_saver"):
        val = str(params.get("value", "toggle")).lower()
        if val in ("on", "activar", "true"):
            _cmd_elevated("powercfg /setacvalueindex scheme_current sub_energysaver ESLP 1")
            return "🔋 Ahorro de batería activado."
        if val in ("off", "desactivar", "false"):
            _cmd_elevated("powercfg /setacvalueindex scheme_current sub_energysaver ESLP 0")
            return "🔋 Ahorro de batería desactivado."
        subprocess.Popen("start ms-settings:batterysaver", shell=True)
        return "🔋 Configuración de ahorro de batería abierta."

    if action in ("info_energia", "power_report"):
        out_path = str(Path(os.environ.get("TEMP", "C:\\Temp")) / "power_report.html")
        _cmd(f'powercfg /energy /output "{out_path}" /duration 5')
        subprocess.Popen(f'start "" "{out_path}"', shell=True)
        return "⚡ Informe de energía generado y abierto."

    return f"Acción de energía desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# SISTEMA / SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

def _system(action: str, params: dict) -> str:
    if action in ("info", "sistema_info", "pc_info"):
        if _HAS_PSUTIL:
            try:
                import time as _time_mod
                boot = psutil.boot_time()
                uptime_sec = int(_time_mod.time() - boot)
                h, m = divmod(uptime_sec // 60, 60)
                mem = psutil.virtual_memory()
                return (
                    f"💻 Información del sistema:\n"
                    f"PC: {os.environ.get('COMPUTERNAME', '???')}\n"
                    f"OS: {os.environ.get('OS', 'Windows')} "
                    f"{os.environ.get('PROCESSOR_ARCHITECTURE', '')}\n"
                    f"RAM: {mem.total / (1024**3):.1f} GB\n"
                    f"Uptime: {h}h {m}m\n"
                    f"Usuario: {os.environ.get('USERNAME', '???')}"
                )
            except Exception:
                pass
        out = _ps("""
$cs = Get-WmiObject Win32_ComputerSystem
$os = Get-WmiObject Win32_OperatingSystem
$cpu = Get-WmiObject Win32_Processor
$ram = [Math]::Round($cs.TotalPhysicalMemory/1GB,1)
$uptime = (Get-Date) - $os.ConvertToDateTime($os.LastBootUpTime)
"PC: $($cs.Name)`nOS: $($os.Caption) $($os.OSArchitecture)`nCPU: $($cpu.Name)`nRAM: ${ram}GB`nUptime: $([int]$uptime.TotalHours)h $($uptime.Minutes)m`nUsuario: $($cs.UserName)`nDominio: $($cs.Domain)"
""")
        return f"💻 Información del sistema:\n{out}"

    if action in ("nombre_pc", "computer_name", "hostname"):
        new_name = params.get("value", params.get("name", ""))
        if new_name:
            _ps(f"Rename-Computer -NewName '{new_name}' -Force")
            return f"💻 Nombre del PC cambiado a '{new_name}'. Reiniciá para aplicar."
        return f"💻 Nombre actual: {_cmd('hostname')}"

    if action in ("fecha_hora", "datetime", "fecha", "hora"):
        val = params.get("value", "")
        if val:
            _ps(f"Set-Date -Date '{val}'")
            return f"🕐 Fecha/hora ajustada a '{val}'."
        return f"🕐 Fecha y hora actual: {_ps('Get-Date | Out-String').strip()}"

    if action in ("zona_horaria", "timezone"):
        val = params.get("value", params.get("timezone", ""))
        if val:
            _ps(f"Set-TimeZone -Id '{val}'")
            return f"🕐 Zona horaria cambiada a '{val}'."
        out = _ps("Get-TimeZone | Select-Object Id,DisplayName | Format-List | Out-String")
        all_tz = _ps("Get-TimeZone -ListAvailable | Where-Object {$_.Id -like '*Argentina*' -or $_.Id -like '*Buenos*'} | Select-Object Id | Out-String")
        return f"🕐 Zona horaria actual:\n{out}\nZonas Argentina:\n{all_tz}"

    if action in ("idioma", "language", "region"):
        val = params.get("value", "")
        if val:
            subprocess.Popen("start ms-settings:regionlanguage", shell=True)
            return "🌐 Configuración de idioma abierta. Cambiá el idioma manualmente."
        out = _ps("Get-Culture | Select-Object Name,DisplayName | Format-List | Out-String")
        return f"🌐 Configuración regional:\n{out}"

    if action in ("reiniciar", "restart", "reboot"):
        delay = int(params.get("delay", params.get("segundos", 5)))
        if delay > 0:
            _cmd(f"shutdown /r /t {delay} /c 'Reinicio solicitado por NEXO'")
        else:
            _cmd("shutdown /r /t 0")
        return f"🔄 PC reiniciando en {delay} segundos..."

    if action in ("apagar", "shutdown", "turn_off"):
        delay = int(params.get("delay", params.get("segundos", 5)))
        _cmd(f"shutdown /s /t {delay} /c 'Apagado solicitado por NEXO'")
        return f"🔴 PC apagándose en {delay} segundos..."

    if action in ("cancelar_apagado", "cancel_shutdown"):
        _cmd("shutdown /a")
        return "✅ Apagado/reinicio cancelado."

    if action in ("bloquear", "lock", "lock_screen"):
        _ps("(Add-Type -AssemblyName PresentationFramework); [System.Windows.Application]::Current")
        subprocess.Popen("rundll32.exe user32.dll,LockWorkStation", shell=True)
        return "🔒 Pantalla bloqueada."

    if action in ("cerrar_sesion", "logoff", "sign_out"):
        _cmd("shutdown /l")
        return "🚪 Cerrando sesión..."

    if action in ("rendimiento", "performance_info", "task_manager"):
        if _HAS_PSUTIL:
            try:
                cpu = psutil.cpu_percent(interval=0.3)
                mem = psutil.virtual_memory()
                disk = psutil.disk_usage("C:\\")
                return (
                    f"📊 Rendimiento:\n"
                    f"CPU: {cpu}%\n"
                    f"RAM: {mem.used / (1024**3):.1f}GB / {mem.total / (1024**3):.1f}GB\n"
                    f"Disco C: {disk.used / (1024**3):.1f}GB usados / "
                    f"{disk.free / (1024**3):.1f}GB libres"
                )
            except Exception:
                pass
        out = _ps("""
$cpu = (Get-WmiObject Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
$mem = Get-WmiObject Win32_OperatingSystem
$memUsed = [Math]::Round(($mem.TotalVisibleMemorySize - $mem.FreePhysicalMemory)/1MB,1)
$memTotal = [Math]::Round($mem.TotalVisibleMemorySize/1MB,1)
$disk = Get-PSDrive C | Select-Object Used,Free
$diskUsed = [Math]::Round($disk.Used/1GB,1)
$diskFree = [Math]::Round($disk.Free/1GB,1)
"CPU: ${cpu}%`nRAM: ${memUsed}GB / ${memTotal}GB`nDisco C: ${diskUsed}GB usados / ${diskFree}GB libres"
""")
        return f"📊 Rendimiento:\n{out}"

    if action in ("variables_entorno", "env_vars", "env"):
        name = params.get("name", params.get("variable", ""))
        if name:
            val = os.environ.get(name, _ps(f'[System.Environment]::GetEnvironmentVariable("{name}","Machine")'))
            return f"🔧 {name} = {val or '(no definida)'}"
        out = _ps("[System.Environment]::GetEnvironmentVariables('User').GetEnumerator() | Sort-Object Key | ForEach-Object { \"$($_.Key) = $($_.Value)\" } | Out-String")
        return f"🔧 Variables de entorno del usuario:\n{out[:2000]}"

    if action in ("set_env", "set_variable", "crear_variable"):
        name  = params.get("name", "")
        value = params.get("value", "")
        scope = params.get("scope", "User")
        if not name:
            return "❌ Especificá name y value."
        _ps(f'[System.Environment]::SetEnvironmentVariable("{name}","{value}","{scope}")')
        return f"🔧 Variable {name} = {value} ({scope}) guardada."

    if action in ("delete_env", "eliminar_variable"):
        name  = params.get("name", "")
        scope = params.get("scope", "User")
        _ps(f'[System.Environment]::SetEnvironmentVariable("{name}",$null,"{scope}")')
        return f"🔧 Variable {name} eliminada."

    if action in ("drivers", "controladores"):
        out = _ps("Get-WmiObject Win32_PnPSignedDriver | Where-Object {$_.DeviceName -ne $null} | Select-Object DeviceName,DriverVersion,Manufacturer | Sort-Object DeviceName | Format-Table -AutoSize | Out-String")
        return f"🔧 Controladores instalados:\n{out[:3000]}"

    if action in ("actualizaciones", "windows_update", "updates"):
        subprocess.Popen("start ms-settings:windowsupdate", shell=True)
        return "🔄 Configuración de Windows Update abierta."

    if action in ("activacion", "activation"):
        out = _ps("(Get-WmiObject -Query 'select * from SoftwareLicensingProduct where PartialProductKey is not null').LicenseStatus")
        status = {"1": "✅ Activado", "0": "❌ No activado", "5": "⚠️ Notificación"}.get(str(out), f"Estado: {out}")
        return f"🔑 Windows: {status}"

    return f"Acción de sistema desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# PERSONALIZACIÓN
# ══════════════════════════════════════════════════════════════════════════════

def _theme_broadcast():
    """Broadcast theme change to all windows so it applies immediately."""
    try:
        import ctypes
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "ImmersiveColorSet",
            0x0002, 5000, None
        )
    except Exception:
        pass


def _personalization(action: str, params: dict) -> str:
    if action in ("fondo", "wallpaper", "fondo_pantalla"):
        path = params.get("path", params.get("value", ""))
        if path:
            path = str(Path(path).resolve())
            if not Path(path).exists():
                return f"❌ No existe el archivo: {path}"
            _ps(f"""
Add-Type -TypeDefinition @'
using System;using System.Runtime.InteropServices;
public class Wallpaper {{
    [DllImport("user32.dll",CharSet=CharSet.Auto)] public static extern int SystemParametersInfo(int uAction,int uParam,string lpvParam,int fuWinIni);
}}
'@
[Wallpaper]::SystemParametersInfo(20,0,'{path}',3)
""")
            return f"🖼 Fondo de pantalla cambiado a '{Path(path).name}'."
        return "❌ Especificá path de la imagen."

    if action in ("tema", "theme"):
        val = str(params.get("value", "")).lower()
        if val in ("oscuro", "dark"):
            _reg_write("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "AppsUseLightTheme", 0, winreg.REG_DWORD)
            _reg_write("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "SystemUsesLightTheme", 0, winreg.REG_DWORD)
            _theme_broadcast()
            return "🎨 Tema oscuro activado."
        if val in ("claro", "light"):
            _reg_write("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "AppsUseLightTheme", 1, winreg.REG_DWORD)
            _reg_write("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "SystemUsesLightTheme", 1, winreg.REG_DWORD)
            _theme_broadcast()
            return "🎨 Tema claro activado."
        subprocess.Popen("start ms-settings:themes", shell=True)
        return "🎨 Configuración de temas abierta."

    if action in ("color_acento", "accent_color"):
        subprocess.Popen("start ms-settings:colors", shell=True)
        return "🎨 Configuración de colores abierta."

    if action in ("barra_tareas", "taskbar"):
        val = str(params.get("value", "")).lower()
        if val in ("ocultar", "hide", "auto_hide"):
            _reg_write("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StuckRects3", "Settings", None)
            subprocess.Popen("start ms-settings:taskbar", shell=True)
            return "🖥 Configuración de barra de tareas abierta."
        subprocess.Popen("start ms-settings:taskbar", shell=True)
        return "🖥 Configuración de barra de tareas abierta."

    if action in ("protector_pantalla", "screensaver"):
        val = params.get("value", "")
        if val == "off" or val == "desactivar":
            _ps("Set-ItemProperty -Path 'HKCU:\\Control Panel\\Desktop' -Name SCRNSAVE.EXE -Value ''")
            return "🖥 Protector de pantalla desactivado."
        subprocess.Popen("control desk.cpl,,@screensaver", shell=True)
        return "🖥 Configuración de protector de pantalla abierta."

    if action in ("transparencia", "transparency"):
        val = str(params.get("value", "toggle")).lower()
        v   = 1 if val in ("on", "activar", "true") else 0 if val in ("off", "desactivar", "false") else None
        if v is not None:
            _reg_write("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency", v, winreg.REG_DWORD)
            return f"🎨 Transparencia {'activada' if v else 'desactivada'}."
        cur = _reg_read("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency")
        return f"🎨 Transparencia: {'activada' if cur else 'desactivada'}"

    if action in ("pantalla_bloqueo", "lock_screen"):
        subprocess.Popen("start ms-settings:lockscreen", shell=True)
        return "🔒 Configuración de pantalla de bloqueo abierta."

    if action in ("fuentes", "fonts"):
        val = params.get("value", "")
        if val == "list":
            out = _ps("[System.Drawing.FontFamily]::Families | Select-Object -First 30 -ExpandProperty Name | Out-String")
            return f"🔤 Fuentes instaladas (primeras 30):\n{out}"
        subprocess.Popen("start ms-settings:fonts", shell=True)
        return "🔤 Configuración de fuentes abierta."

    if action in ("cursor", "puntero", "mouse_pointer"):
        subprocess.Popen("control main.cpl", shell=True)
        return "🖱 Configuración del cursor abierta."

    return f"Acción de personalización desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# APPS & PROGRAMAS
# ══════════════════════════════════════════════════════════════════════════════

def _apps(action: str, params: dict) -> str:
    if action in ("lista_apps", "installed_apps", "listar_apps"):
        out = _ps("Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | Select-Object DisplayName,DisplayVersion,Publisher | Where-Object {$_.DisplayName} | Sort-Object DisplayName | Format-Table -AutoSize | Out-String")
        return f"📦 Apps instaladas:\n{out[:3000]}"

    if action in ("desinstalar", "uninstall"):
        app = params.get("app", params.get("name", ""))
        if not app:
            return "❌ Especificá el nombre de la app."
        _ps(f"Get-Package -Name '*{app}*' | Uninstall-Package -Force")
        return f"🗑 Desinstalando '{app}'..."

    if action in ("inicio_apps", "startup_apps", "apps_inicio"):
        out = _ps("Get-CimInstance Win32_StartupCommand | Select-Object Name,Command,Location | Format-Table -AutoSize | Out-String")
        return f"🚀 Apps de inicio:\n{out}"

    if action in ("deshabilitar_inicio", "disable_startup"):
        app = params.get("app", params.get("name", ""))
        if not app:
            subprocess.Popen("start ms-settings:startupapps", shell=True)
            return "🚀 Gestión de apps de inicio abierta."
        _ps(f"Get-ScheduledTask -TaskName '*{app}*' | Disable-ScheduledTask")
        return f"🚀 App de inicio '{app}' deshabilitada."

    if action in ("apps_predeterminadas", "default_apps"):
        subprocess.Popen("start ms-settings:defaultapps", shell=True)
        return "📦 Configuración de apps predeterminadas abierta."

    if action in ("microsoft_store", "store"):
        subprocess.Popen("start ms-windows-store:", shell=True)
        return "📦 Microsoft Store abierta."

    if action in ("actualizar_apps", "update_apps"):
        _ps("Get-AppxPackage | ForEach-Object { Add-AppxPackage -DisableDevelopmentMode -Register \"$($_.InstallLocation)\\AppXManifest.xml\" -ErrorAction SilentlyContinue }")
        return "📦 Actualización de apps iniciada."

    return f"Acción de apps desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# SEGURIDAD / SECURITY
# ══════════════════════════════════════════════════════════════════════════════

def _security(action: str, params: dict) -> str:
    if action in ("defender_scan", "antivirus_scan", "escanear"):
        tipo = params.get("type", "quick").lower()
        scan_type = {"quick": "1", "full": "2", "custom": "3"}.get(tipo, "1")
        _ps(f"Start-MpScan -ScanType {scan_type}")
        return f"🛡 Escaneo antivirus {'rápido' if scan_type=='1' else 'completo'} iniciado."

    if action in ("defender_estado", "antivirus_status", "defender_status"):
        out = _ps("Get-MpComputerStatus | Select-Object AMRunningMode,AntivirusEnabled,RealTimeProtectionEnabled,AntispywareEnabled,NISEnabled | Format-List | Out-String")
        return f"🛡 Estado de Windows Defender:\n{out}"

    if action in ("defender_update", "actualizar_antivirus"):
        _ps("Update-MpSignature")
        return "🛡 Definiciones del antivirus actualizadas."

    if action in ("firewall_status", "firewall_estado"):
        out = _ps("Get-NetFirewallProfile | Select-Object Name,Enabled | Format-Table | Out-String")
        return f"🔥 Estado del firewall:\n{out}"

    if action in ("firewall_on", "activar_firewall"):
        _ps("Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True")
        return "🔥 Firewall activado en todos los perfiles."

    if action in ("firewall_off", "desactivar_firewall"):
        _ps("Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False")
        return "🔥 Firewall desactivado. ⚠️ Esto reduce la seguridad."

    if action in ("uac", "control_cuentas"):
        val = str(params.get("value", "")).lower()
        if val in ("off", "desactivar", "0"):
            _reg_write("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "EnableLUA", 0, winreg.REG_DWORD)
            return "🔑 UAC desactivado. Reiniciá para aplicar. ⚠️ Reduce la seguridad."
        if val in ("on", "activar", "1"):
            _reg_write("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "EnableLUA", 1, winreg.REG_DWORD)
            return "🔑 UAC activado. Reiniciá para aplicar."
        cur = _reg_read("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "EnableLUA")
        return f"🔑 UAC: {'Activado' if cur else 'Desactivado'}"

    if action in ("bitlocker_status",):
        out = _ps("manage-bde -status C: 2>&1 | Out-String")
        return f"🔒 BitLocker:\n{out[:500]}"

    if action in ("politicas", "group_policy"):
        subprocess.Popen("gpedit.msc", shell=True)
        return "🔑 Editor de políticas de grupo abierto."

    if action in ("usuarios", "user_accounts", "cuentas"):
        out = _ps("Get-LocalUser | Select-Object Name,Enabled,LastLogon | Format-Table -AutoSize | Out-String")
        return f"👤 Cuentas de usuario:\n{out}"

    if action in ("password_politica", "password_policy"):
        out = _cmd("net accounts")
        return f"🔑 Política de contraseñas:\n{out}"

    return f"Acción de seguridad desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# MOUSE & TECLADO
# ══════════════════════════════════════════════════════════════════════════════

def _input_devices(action: str, params: dict) -> str:
    if action in ("velocidad_mouse", "mouse_speed", "sensibilidad_mouse"):
        val = params.get("value")
        if val:
            v = max(1, min(20, int(val)))
            _reg_write("HKCU", r"Control Panel\Mouse", "MouseSensitivity", str(v))
            _ps("$code='using System.Runtime.InteropServices;public class NativeMethods{[DllImport(\"user32.dll\")]public static extern bool SystemParametersInfo(uint u,uint p,ref int r,uint f);}';Add-Type -TypeDefinition $code -Language CSharp;$v={v};[NativeMethods]::SystemParametersInfo(0x0071,0,[ref]$v,0x03)")
            return f"🖱 Velocidad del mouse ajustada a {v}/20."
        cur = _reg_read("HKCU", r"Control Panel\Mouse", "MouseSensitivity")
        return f"🖱 Velocidad del mouse: {cur}/20"

    if action in ("doble_click", "double_click_speed"):
        val = params.get("value")
        if val:
            v = max(100, min(900, int(val)))
            _reg_write("HKCU", r"Control Panel\Mouse", "DoubleClickSpeed", str(v))
            return f"🖱 Velocidad de doble click: {v}ms."
        return f"🖱 Velocidad de doble click: {_reg_read('HKCU', r'Control Panel\\Mouse', 'DoubleClickSpeed')}ms"

    if action in ("scroll_mouse", "rueda_mouse", "scroll_speed"):
        val = params.get("value", "3")
        _reg_write("HKCU", r"Control Panel\Desktop", "WheelScrollLines", str(val))
        return f"🖱 Velocidad de scroll: {val} líneas por paso."

    if action in ("boton_mouse", "swap_buttons", "mouse_zurdo"):
        val = str(params.get("value", "toggle")).lower()
        if val in ("on", "zurdo", "left", "swap"):
            _ps("[System.Windows.Forms.SystemInformation]::MouseButtonsSwapped")
            _cmd("rundll32 user32.dll,SwapMouseButton 1")
            return "🖱 Botones del mouse intercambiados (para zurdos)."
        _cmd("rundll32 user32.dll,SwapMouseButton 0")
        return "🖱 Botones del mouse normales (para diestros)."

    if action in ("puntero_precisión", "enhance_pointer", "pointer_precision"):
        val = str(params.get("value", "toggle")).lower()
        v   = "1" if val in ("on", "activar") else "0" if val in ("off", "desactivar") else None
        if v:
            _reg_write("HKCU", r"Control Panel\Mouse", "MouseSpeed", v)
            return f"🖱 Precisión del puntero {'activada' if v=='1' else 'desactivada'}."
        subprocess.Popen("control main.cpl", shell=True)
        return "🖱 Configuración del mouse abierta."

    if action in ("velocidad_teclado", "keyboard_speed", "repeticion_teclado"):
        val = params.get("value", "31")
        _reg_write("HKCU", r"Control Panel\Keyboard", "KeyboardSpeed", str(val))
        return f"⌨️ Velocidad de repetición del teclado: {val}."

    if action in ("retardo_teclado", "keyboard_delay"):
        val = params.get("value", "1")
        _reg_write("HKCU", r"Control Panel\Keyboard", "KeyboardDelay", str(val))
        return f"⌨️ Retardo del teclado: {val} (0=corto, 3=largo)."

    if action in ("idioma_teclado", "keyboard_language", "layout_teclado"):
        out = _ps("Get-WinUserLanguageList | Select-Object LanguageTag,LocalName | Format-Table | Out-String")
        return f"⌨️ Idiomas del teclado:\n{out}"

    if action in ("teclado_tactil", "touch_keyboard", "osk"):
        subprocess.Popen("osk.exe", shell=True)
        return "⌨️ Teclado en pantalla abierto."

    return f"Acción de input desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# ALMACENAMIENTO / STORAGE
# ══════════════════════════════════════════════════════════════════════════════

def _storage(action: str, params: dict) -> str:
    if action in ("discos", "drives", "discos_info", "espacio"):
        if _HAS_PSUTIL:
            try:
                parts = psutil.disk_partitions()
                lines = ["💾 Almacenamiento:"]
                for p in parts:
                    if p.fstype and 'CDROM' not in p.opts:
                        try:
                            usage = psutil.disk_usage(p.mountpoint)
                            total = usage.total / (1024**3)
                            used = usage.used / (1024**3)
                            free = usage.free / (1024**3)
                            lines.append(
                                f"  {p.device} ({p.mountpoint})  "
                                f"{used:.1f}GB / {total:.1f}GB  ({usage.percent}%)"
                            )
                        except Exception:
                            lines.append(f"  {p.device} ({p.mountpoint})  sin datos")
                return "\n".join(lines)
            except Exception:
                pass
        out = _ps("Get-PSDrive -PSProvider FileSystem | Select-Object Name,@{N='Used(GB)';E={[Math]::Round($_.Used/1GB,1)}},@{N='Free(GB)';E={[Math]::Round($_.Free/1GB,1)}},@{N='Total(GB)';E={[Math]::Round(($_.Used+$_.Free)/1GB,1)}} | Format-Table -AutoSize | Out-String")
        return f"💾 Almacenamiento:\n{out}"

    if action in ("limpieza_disco", "disk_cleanup", "limpiar_disco"):
        drive = params.get("drive", "C")
        _cmd(f"cleanmgr /d {drive}: /sagerun:1")
        return f"🧹 Limpieza de disco iniciada en {drive}:."

    if action in ("papelera", "recycle_bin", "vaciar_papelera", "empty_trash", "empty_recycle_bin"):
        try:
            import ctypes
            # SHEmptyRecycleBinW: 1=sin confirmación, 2=sin progreso, 4=sin sonido
            ret = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
            # 0=OK, 0x80070002 / -2147024894 = ya estaba vacía
            if ret in (0, -2147024894, 0x80070002):
                return "🗑 Papelera de reciclaje vaciada correctamente."
            # Fallback PowerShell si ctypes retornó código inesperado
            _ps("Clear-RecycleBin -Force -ErrorAction SilentlyContinue")
            return "🗑 Papelera de reciclaje vaciada."
        except Exception:
            try:
                _ps("Clear-RecycleBin -Force -ErrorAction SilentlyContinue")
                return "🗑 Papelera de reciclaje vaciada."
            except Exception as e2:
                return f"❌ No se pudo vaciar la papelera: {e2}"

    if action in ("temp_files", "archivos_temp", "limpiar_temp"):
        tmp = os.environ.get("TEMP", "C:\\Windows\\Temp")
        deleted = 0
        for f in Path(tmp).glob("*"):
            try:
                if f.is_file():
                    f.unlink()
                    deleted += 1
                elif f.is_dir():
                    import shutil
                    shutil.rmtree(f, ignore_errors=True)
                    deleted += 1
            except Exception:
                pass
        return f"🧹 Archivos temporales eliminados: {deleted} entradas en {tmp}."

    if action in ("desfragmentar", "defrag", "optimizar_disco"):
        drive = params.get("drive", "C")
        _ps(f"Optimize-Volume -DriveLetter {drive} -Defrag -Verbose")
        return f"💾 Optimización/desfragmentación iniciada en {drive}:."

    if action in ("error_disco", "chkdsk", "check_disk"):
        drive = params.get("drive", "C")
        out   = _cmd(f"chkdsk {drive}: /scan")
        return f"💾 Verificación de disco {drive}:\n{out[:1000]}"

    if action in ("arbol_directorios", "disk_usage_dir", "uso_carpeta"):
        path = params.get("path", "C:\\")
        out  = _ps(f"Get-ChildItem -Path '{path}' -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum | Select-Object Count,Sum | ForEach-Object {{\"Archivos: $($_.Count)`nTamaño: $([Math]::Round($_.Sum/1GB,2))GB\"}}")
        return f"💾 {path}:\n{out}"

    if action in ("smb", "compartir_carpeta", "share_folder"):
        path = params.get("path", "")
        name = params.get("name", "NEXOShare")
        if path:
            _ps(f"New-SmbShare -Name '{name}' -Path '{path}' -FullAccess 'Everyone' -ErrorAction SilentlyContinue")
            return f"🌐 Carpeta compartida: '{path}' como '{name}'."
        subprocess.Popen("fsmgmt.msc", shell=True)
        return "🌐 Administrador de recursos compartidos abierto."

    return f"Acción de almacenamiento desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# SERVICIOS & PROCESOS
# ══════════════════════════════════════════════════════════════════════════════

def _services(action: str, params: dict) -> str:
    if action in ("listar_servicios", "list_services", "servicios"):
        filtro = params.get("filter", params.get("estado", ""))
        if filtro:
            out = _ps(f"Get-Service | Where-Object {{$_.Status -eq '{filtro}'}} | Select-Object Name,DisplayName,Status | Format-Table -AutoSize | Out-String")
        else:
            out = _ps("Get-Service | Select-Object Name,DisplayName,Status | Sort-Object Status,Name | Format-Table -AutoSize | Out-String")
        return f"⚙️ Servicios:\n{out[:3000]}"

    if action in ("iniciar_servicio", "start_service"):
        name = params.get("name", params.get("service", ""))
        if not name:
            return "❌ Especificá el nombre del servicio."
        _ps(f"Start-Service -Name '{name}' -ErrorAction Stop")
        return f"▶️ Servicio '{name}' iniciado."

    if action in ("detener_servicio", "stop_service"):
        name = params.get("name", params.get("service", ""))
        if not name:
            return "❌ Especificá el nombre del servicio."
        _ps(f"Stop-Service -Name '{name}' -Force -ErrorAction Stop")
        return f"⏹ Servicio '{name}' detenido."

    if action in ("reiniciar_servicio", "restart_service"):
        name = params.get("name", params.get("service", ""))
        if not name:
            return "❌ Especificá el nombre del servicio."
        _ps(f"Restart-Service -Name '{name}' -Force")
        return f"🔄 Servicio '{name}' reiniciado."

    if action in ("info_servicio", "service_info"):
        name = params.get("name", params.get("service", ""))
        if not name:
            return "❌ Especificá el nombre del servicio."
        out = _ps(f"Get-Service -Name '{name}' | Format-List *")
        return f"⚙️ {out}"

    if action in ("listar_procesos", "list_processes", "procesos"):
        out = _ps("Get-Process | Sort-Object CPU -Descending | Select-Object -First 20 Name,Id,CPU,@{N='Mem(MB)';E={[Math]::Round($_.WorkingSet/1MB,1)}} | Format-Table -AutoSize | Out-String")
        return f"⚙️ Procesos (Top 20 por CPU):\n{out}"

    if action in ("terminar_proceso", "kill_process", "kill"):
        name = params.get("name", params.get("process", ""))
        pid  = params.get("pid")
        if pid:
            _ps(f"Stop-Process -Id {pid} -Force")
            return f"⏹ Proceso PID {pid} terminado."
        if name:
            _ps(f"Stop-Process -Name '{name}' -Force -ErrorAction SilentlyContinue")
            return f"⏹ Proceso '{name}' terminado."
        return "❌ Especificá name o pid del proceso."

    if action in ("prioridad_proceso", "process_priority"):
        name  = params.get("name", "")
        nivel = params.get("priority", "Normal")
        if name:
            _ps(f"(Get-Process -Name '{name}').PriorityClass = '{nivel}'")
            return f"⚙️ Prioridad de '{name}' cambiada a {nivel}."
        return "❌ Especificá name del proceso."

    return f"Acción de servicios desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# PRIVACIDAD & NOTIFICACIONES
# ══════════════════════════════════════════════════════════════════════════════

def _privacy(action: str, params: dict) -> str:
    if action in ("camara_privacidad", "camera_privacy"):
        val = str(params.get("value", "")).lower()
        v   = 1 if val in ("off", "desactivar", "block") else 0
        _reg_write("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\AppPrivacy", "LetAppsAccessCamera", v, winreg.REG_DWORD)
        return f"📷 Acceso a cámara {'bloqueado' if v else 'permitido'} para apps. Reiniciá para aplicar."

    if action in ("microfono_privacidad", "mic_privacy", "microphone_privacy"):
        val = str(params.get("value", "")).lower()
        v   = 1 if val in ("off", "desactivar", "block") else 0
        _reg_write("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\AppPrivacy", "LetAppsAccessMicrophone", v, winreg.REG_DWORD)
        return f"🎙 Acceso a micrófono {'bloqueado' if v else 'permitido'}. Reiniciá para aplicar."

    if action in ("ubicacion", "location", "gps"):
        val = str(params.get("value", "")).lower()
        v   = 0 if val in ("off", "desactivar") else 1
        _reg_write("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\LocationAndSensors", "DisableLocation", 1 - v, winreg.REG_DWORD)
        return f"📍 Servicios de ubicación {'desactivados' if not v else 'activados'}."

    if action in ("telemetria", "telemetry", "diagnosticos"):
        val = str(params.get("value", "")).lower()
        v   = 0 if val in ("off", "0", "desactivar", "minimo") else 1
        _reg_write("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", v, winreg.REG_DWORD)
        return f"🔒 Telemetría ajustada a {'mínimo' if v==0 else 'normal'}. Reiniciá para aplicar."

    if action in ("no_molestar", "focus_assist", "dnd", "do_not_disturb"):
        val = str(params.get("value", "toggle")).lower()
        if val in ("on", "activar", "true"):
            _reg_write("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings", "NOC_GLOBAL_SETTING_TOASTS_ENABLED", 0, winreg.REG_DWORD)
            return "🔕 No molestar activado (notificaciones silenciadas)."
        if val in ("off", "desactivar", "false"):
            _reg_write("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings", "NOC_GLOBAL_SETTING_TOASTS_ENABLED", 1, winreg.REG_DWORD)
            return "🔔 Notificaciones reactivadas."
        subprocess.Popen("start ms-settings:quiethours", shell=True)
        return "🔕 Configuración de No molestar abierta."

    if action in ("notificaciones", "notifications"):
        subprocess.Popen("start ms-settings:notifications", shell=True)
        return "🔔 Configuración de notificaciones abierta."

    if action in ("privacidad", "privacy_settings"):
        subprocess.Popen("start ms-settings:privacy", shell=True)
        return "🔒 Configuración de privacidad abierta."

    if action in ("publicidad", "advertising_id"):
        _reg_write("HKCU", r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 0, winreg.REG_DWORD)
        return "🔒 ID de publicidad desactivado."

    if action in ("portapapeles", "clipboard"):
        val = str(params.get("value", "clear")).lower()
        if val in ("clear", "limpiar", "vaciar"):
            _ps("Set-Clipboard -Value $null")
            return "📋 Portapapeles limpiado."
        if val in ("history_on", "historial_on"):
            _reg_write("HKCU", r"Software\Microsoft\Clipboard", "EnableClipboardHistory", 1, winreg.REG_DWORD)
            return "📋 Historial del portapapeles activado."
        if val in ("history_off", "historial_off"):
            _reg_write("HKCU", r"Software\Microsoft\Clipboard", "EnableClipboardHistory", 0, winreg.REG_DWORD)
            return "📋 Historial del portapapeles desactivado."
        out = _ps("Get-Clipboard")
        return f"📋 Portapapeles actual: {out[:200]}"

    return f"Acción de privacidad desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# TEMPERATURA DE CPU
# ══════════════════════════════════════════════════════════════════════════════

def _cpu_temperature(action: str, params: dict) -> str:
    """Monitor CPU temperature via WMI/OpenHardwareMonitor or PowerShell."""
    if action in ("temperatura_cpu", "cpu_temp", "temperatura"):
        # Try WMI MSAcpi_ThermalZoneTemperature
        out = _ps("""
try {
    $temps = Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace "root/wmi" -ErrorAction Stop
    $temps | ForEach-Object {
        $celsius = ($_.CurrentTemperature - 2732) / 10.0
        "Zona: $($_.InstanceName)  →  $([Math]::Round($celsius, 1))°C"
    }
} catch {
    # Fallback: Open Hardware Monitor WMI (if installed)
    try {
        $hw = Get-WmiObject -Namespace "root/OpenHardwareMonitor" -Class Sensor -ErrorAction Stop |
              Where-Object { $_.SensorType -eq "Temperature" -and $_.Name -like "*CPU*" }
        if ($hw) {
            $hw | ForEach-Object { "$($_.Name): $([Math]::Round($_.Value,1))°C" }
        } else { "OHM instalado pero sin sensores CPU." }
    } catch {
        "No se pudo leer temperatura. Instala Open Hardware Monitor o CoreTemp para habilitar WMI."
    }
}
""")
        return f"🌡 Temperatura CPU:\n{out}"

    if action in ("temperatura_info", "temp_info"):
        out = _ps("""
$cpu = Get-WmiObject Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors
$cpu | ForEach-Object { "CPU: $($_.Name) | Cores: $($_.NumberOfCores) | Threads: $($_.NumberOfLogicalProcessors)" }
""")
        return f"💻 Info CPU:\n{out}"

    return f"Acción de temperatura desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# ESCRITORIOS VIRTUALES
# ══════════════════════════════════════════════════════════════════════════════

def _virtual_desktops(action: str, params: dict) -> str:
    """Control Virtual Desktops via keyboard shortcuts and IVirtualDesktopManager."""

    if action in ("nuevo_escritorio", "new_desktop", "crear_escritorio"):
        # Win+Ctrl+D — create new virtual desktop
        _ps("""
$wsh = New-Object -ComObject WScript.Shell
$wsh.SendKeys("^%({d})")
""")
        # More reliable via .NET
        _ps("""
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait("^%({d})")
""")
        # Use keybd_event via pinvoke as most reliable
        _ps("""
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class VD {
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);
    public const int KEYEVENTF_KEYUP = 0x0002;
    public static void Press(byte key) {
        keybd_event(0xA2, 0, 0, 0); // Ctrl
        keybd_event(0x5B, 0, 0, 0); // Win
        keybd_event(key,  0, 0, 0);
        keybd_event(key,  0, KEYEVENTF_KEYUP, 0);
        keybd_event(0x5B, 0, KEYEVENTF_KEYUP, 0);
        keybd_event(0xA2, 0, KEYEVENTF_KEYUP, 0);
    }
}
'@
[VD]::Press(0x44)
""")
        return "🖥 Nuevo escritorio virtual creado (Win+Ctrl+D)."

    if action in ("cerrar_escritorio", "close_desktop"):
        _ps("""
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class VD2 {
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);
    public const int KEYEVENTF_KEYUP = 0x0002;
    public static void Press(byte key) {
        keybd_event(0xA2, 0, 0, 0);
        keybd_event(0x5B, 0, 0, 0);
        keybd_event(key,  0, 0, 0);
        keybd_event(key,  0, KEYEVENTF_KEYUP, 0);
        keybd_event(0x5B, 0, KEYEVENTF_KEYUP, 0);
        keybd_event(0xA2, 0, KEYEVENTF_KEYUP, 0);
    }
}
'@
[VD2]::Press(0x46)
""")
        return "🖥 Escritorio virtual actual cerrado (Win+Ctrl+F4)."

    if action in ("siguiente_escritorio", "next_desktop"):
        _ps("""
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class VD3 {
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);
    public const int KEYEVENTF_KEYUP = 0x0002;
    public static void Combo() {
        keybd_event(0xA2, 0, 0, 0); keybd_event(0x5B, 0, 0, 0);
        keybd_event(0x27, 0, 0, 0); keybd_event(0x27, 0, KEYEVENTF_KEYUP, 0);
        keybd_event(0x5B, 0, KEYEVENTF_KEYUP, 0); keybd_event(0xA2, 0, KEYEVENTF_KEYUP, 0);
    }
}
'@
[VD3]::Combo()
""")
        return "🖥 Cambiado al siguiente escritorio virtual (Win+Ctrl+→)."

    if action in ("anterior_escritorio", "prev_desktop"):
        _ps("""
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class VD4 {
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);
    public const int KEYEVENTF_KEYUP = 0x0002;
    public static void Combo() {
        keybd_event(0xA2, 0, 0, 0); keybd_event(0x5B, 0, 0, 0);
        keybd_event(0x25, 0, 0, 0); keybd_event(0x25, 0, KEYEVENTF_KEYUP, 0);
        keybd_event(0x5B, 0, KEYEVENTF_KEYUP, 0); keybd_event(0xA2, 0, KEYEVENTF_KEYUP, 0);
    }
}
'@
[VD4]::Combo()
""")
        return "🖥 Cambiado al escritorio virtual anterior (Win+Ctrl+←)."

    if action in ("vista_tareas", "task_view"):
        _ps("""
Add-Type @'
using System;using System.Runtime.InteropServices;
public class TV {
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);
    public const int KEYEVENTF_KEYUP = 0x0002;
}
'@
# Win+Tab
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public class KH{[DllImport("user32.dll")]public static extern void keybd_event(byte b,byte s,uint f,int e);}' -ErrorAction SilentlyContinue
[KH]::keybd_event(0x5B,0,0,0); [KH]::keybd_event(0x09,0,0,0); [KH]::keybd_event(0x09,0,2,0); [KH]::keybd_event(0x5B,0,2,0)
""")
        return "🖥 Vista de tareas abierta (Win+Tab)."

    return f"Acción de escritorio virtual desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# IMPRESORAS
# ══════════════════════════════════════════════════════════════════════════════

def _printers(action: str, params: dict) -> str:
    if action in ("listar_impresoras", "list_printers", "impresoras"):
        out = _ps("Get-Printer | Select-Object Name,DriverName,PortName,Default,PrinterStatus | Format-Table -AutoSize | Out-String")
        return f"🖨 Impresoras instaladas:\n{out}"

    if action in ("impresora_predeterminada", "set_default_printer", "predeterminar_impresora"):
        name = params.get("name", params.get("printer", ""))
        if not name:
            return "❌ Especificá el nombre de la impresora (name)."
        out = _ps(f"(New-Object -ComObject WScript.Network).SetDefaultPrinter('{name}')")
        return f"🖨 Impresora predeterminada cambiada a '{name}'."

    if action in ("imprimir_prueba", "print_test"):
        name = params.get("name", params.get("printer", ""))
        if name:
            out = _ps(f"Get-Printer -Name '{name}' | Out-Printer")
            return f"🖨 Página de prueba enviada a '{name}'."
        subprocess.Popen("start ms-settings:printers", shell=True)
        return "🖨 Configuración de impresoras abierta (seleccioná una impresora para imprimir prueba)."

    if action in ("info_impresora", "printer_info"):
        name = params.get("name", params.get("printer", ""))
        if not name:
            return "❌ Especificá el nombre de la impresora."
        out = _ps(f"Get-Printer -Name '{name}' | Format-List * | Out-String")
        return f"🖨 Info de '{name}':\n{out[:1500]}"

    if action in ("cola_impresion", "print_queue"):
        name = params.get("name", params.get("printer", ""))
        if name:
            out = _ps(f"Get-PrintJob -PrinterName '{name}' | Select-Object Id,JobStatus,DocumentName,UserName | Format-Table | Out-String")
        else:
            out = _ps("Get-Printer | ForEach-Object { $jobs = Get-PrintJob -PrinterName $_.Name -ErrorAction SilentlyContinue; if ($jobs) { \"$($_.Name): $($jobs.Count) trabajos\" } }")
        return f"🖨 Cola de impresión:\n{out or 'Sin trabajos pendientes.'}"

    if action in ("cancelar_impresion", "cancel_print_job"):
        name   = params.get("name", "")
        job_id = params.get("job_id")
        if name and job_id:
            _ps(f"Remove-PrintJob -PrinterName '{name}' -Id {job_id}")
            return f"🖨 Trabajo {job_id} cancelado en '{name}'."
        return "❌ Especificá name (impresora) y job_id."

    return f"Acción de impresoras desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# FUENTES INSTALADAS (AVANZADO)
# ══════════════════════════════════════════════════════════════════════════════

def _fonts_advanced(action: str, params: dict) -> str:
    if action in ("listar_fuentes", "list_fonts"):
        search = params.get("search", params.get("filter", ""))
        if search:
            out = _ps(f"""
[System.Drawing.Text.InstalledFontCollection]::new().Families |
  Where-Object {{ $_.Name -like '*{search}*' }} |
  Select-Object -ExpandProperty Name | Out-String
""")
        else:
            out = _ps("""
[System.Drawing.Text.InstalledFontCollection]::new().Families |
  Select-Object -ExpandProperty Name | Out-String
""")
        count = _ps("""
[System.Drawing.Text.InstalledFontCollection]::new().Families.Count
""")
        return f"🔤 Fuentes instaladas ({count.strip()} total):\n{out[:3000]}"

    if action in ("instalar_fuente", "install_font"):
        path = params.get("path", params.get("file", ""))
        if not path:
            return "❌ Especificá el path del archivo de fuente (.ttf, .otf)."
        p = Path(path)
        if not p.exists():
            return f"❌ Archivo no encontrado: {path}"
        # Copy to Fonts directory
        fonts_dir = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
        dest = fonts_dir / p.name
        try:
            import shutil
            shutil.copy2(str(p), str(dest))
            # Register in registry
            _reg_write(
                "HKLM",
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
                p.stem,
                p.name,
            )
            # Broadcast font change
            _ps("Add-Type -Name Msg -Namespace Win32 -MemberDefinition '[DllImport(\"user32.dll\")] public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);' -ErrorAction SilentlyContinue; [Win32.Msg]::PostMessage([IntPtr]0xFFFF, 0x001D, [IntPtr]::Zero, [IntPtr]::Zero)")
            return f"🔤 Fuente '{p.name}' instalada correctamente."
        except PermissionError:
            return f"❌ Sin permisos de administrador para instalar fuentes."
        except Exception as e:
            return f"❌ Error instalando fuente: {e}"

    if action in ("eliminar_fuente", "uninstall_font"):
        name = params.get("name", "")
        if not name:
            return "❌ Especificá el nombre de la fuente."
        fonts_dir = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
        # Try common extensions
        deleted = False
        for ext in (".ttf", ".otf", ".ttc", ".fon"):
            f = fonts_dir / (name + ext)
            if f.exists():
                try:
                    f.unlink()
                    deleted = True
                except Exception:
                    pass
        if deleted:
            return f"🔤 Fuente '{name}' eliminada. Puede requerir reinicio."
        return f"❌ Fuente '{name}' no encontrada en {fonts_dir}."

    return f"Acción de fuentes desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# CONTROL DE VENTANAS DEL ESCRITORIO
# ══════════════════════════════════════════════════════════════════════════════

def _window_control(action: str, params: dict) -> str:
    if action in ("listar_ventanas", "list_windows"):
        out = _ps("""
Add-Type -AssemblyName System.Windows.Forms
$pids = (Get-Process | Where-Object { $_.MainWindowHandle -ne 0 })
$pids | Select-Object ProcessName, Id, MainWindowTitle | Where-Object { $_.MainWindowTitle } |
  Format-Table -AutoSize | Out-String
""")
        return f"🪟 Ventanas abiertas:\n{out[:3000]}"

    if action in ("maximizar_ventana", "maximize_window"):
        name = params.get("name", params.get("process", ""))
        if not name:
            return "❌ Especificá name (nombre del proceso o título)."
        _ps(f"""
Add-Type @'
using System;using System.Runtime.InteropServices;
public class WinCtrl {{
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    public const int SW_MAXIMIZE = 3;
}}
'@
$p = Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Where-Object {{$_.MainWindowHandle -ne 0}} | Select-Object -First 1
if ($p) {{
    [WinCtrl]::ShowWindow($p.MainWindowHandle, [WinCtrl]::SW_MAXIMIZE)
    [WinCtrl]::SetForegroundWindow($p.MainWindowHandle)
}}
""")
        return f"🪟 Ventana '{name}' maximizada."

    if action in ("minimizar_ventana", "minimize_window"):
        name = params.get("name", params.get("process", ""))
        if not name:
            return "❌ Especificá name (nombre del proceso)."
        _ps(f"""
Add-Type @'
using System;using System.Runtime.InteropServices;
public class WinMin {{
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
    public const int SW_MINIMIZE = 6;
}}
'@
$p = Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Where-Object {{$_.MainWindowHandle -ne 0}} | Select-Object -First 1
if ($p) {{ [WinMin]::ShowWindow($p.MainWindowHandle, [WinMin]::SW_MINIMIZE) }}
""")
        return f"🪟 Ventana '{name}' minimizada."

    if action in ("restaurar_ventana", "restore_window"):
        name = params.get("name", params.get("process", ""))
        if not name:
            return "❌ Especificá name (nombre del proceso)."
        _ps(f"""
Add-Type @'
using System;using System.Runtime.InteropServices;
public class WinRes {{
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    public const int SW_RESTORE = 9;
}}
'@
$p = Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Where-Object {{$_.MainWindowHandle -ne 0}} | Select-Object -First 1
if ($p) {{
    [WinRes]::ShowWindow($p.MainWindowHandle, [WinRes]::SW_RESTORE)
    [WinRes]::SetForegroundWindow($p.MainWindowHandle)
}}
""")
        return f"🪟 Ventana '{name}' restaurada y enfocada."

    if action in ("cerrar_ventana", "close_window"):
        name = params.get("name", params.get("process", ""))
        if not name:
            return "❌ Especificá name (nombre del proceso)."
        _ps(f"""
$p = Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Where-Object {{$_.MainWindowHandle -ne 0}} | Select-Object -First 1
if ($p) {{ $p.CloseMainWindow() }}
""")
        return f"🪟 Señal de cierre enviada a '{name}'."

    if action in ("mover_ventana", "move_window"):
        name = params.get("name", params.get("process", ""))
        x    = params.get("x", 0)
        y    = params.get("y", 0)
        w    = params.get("width", 800)
        h    = params.get("height", 600)
        if not name:
            return "❌ Especificá name (nombre del proceso)."
        _ps(f"""
Add-Type @'
using System;using System.Runtime.InteropServices;
public class WinMove {{
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
}}
'@
$p = Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Where-Object {{$_.MainWindowHandle -ne 0}} | Select-Object -First 1
if ($p) {{ [WinMove]::MoveWindow($p.MainWindowHandle, {x}, {y}, {w}, {h}, $true) }}
""")
        return f"🪟 Ventana '{name}' movida a ({x},{y}) tamaño {w}x{h}."

    if action in ("enfocar_ventana", "focus_window", "bring_to_front"):
        name = params.get("name", params.get("process", ""))
        if not name:
            return "❌ Especificá name (nombre del proceso o título de ventana)."
        _ps(f"""
Add-Type @'
using System;using System.Runtime.InteropServices;
public class WinFocus {{
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
    public const int SW_RESTORE = 9;
}}
'@
$p = Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Where-Object {{$_.MainWindowHandle -ne 0}} | Select-Object -First 1
if ($p) {{
    [WinFocus]::ShowWindow($p.MainWindowHandle, [WinFocus]::SW_RESTORE)
    [WinFocus]::SetForegroundWindow($p.MainWindowHandle)
}}
""")
        return f"🪟 Ventana '{name}' enfocada."

    return f"Acción de control de ventanas desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# PUNTOS DE RESTAURACIÓN DEL SISTEMA
# ══════════════════════════════════════════════════════════════════════════════

def _system_restore(action: str, params: dict) -> str:
    if action in ("crear_punto_restauracion", "create_restore_point"):
        desc = params.get("description", params.get("name", "NEXO Snapshot"))
        out = _ps(f"""
try {{
    Enable-ComputerRestore -Drive "C:\\" -ErrorAction SilentlyContinue
    Checkpoint-Computer -Description '{desc}' -RestorePointType MODIFY_SETTINGS -ErrorAction Stop
    "Punto de restauración creado: {desc}"
}} catch {{
    "Error: $_"
}}
""", timeout=60)
        return f"🔄 {out}"

    if action in ("listar_puntos_restauracion", "list_restore_points"):
        out = _ps("Get-ComputerRestorePoint | Select-Object SequenceNumber,Description,CreationTime | Format-Table -AutoSize | Out-String")
        return f"🔄 Puntos de restauración:\n{out}"

    if action in ("restaurar_sistema", "restore_system"):
        seq = params.get("sequence", params.get("id"))
        if not seq:
            return "❌ Especificá sequence (número de secuencia del punto de restauración)."
        out = _ps(f"""
try {{
    Restore-Computer -RestorePoint {seq} -Confirm:$false
    "Restaurando al punto {seq}. El sistema se reiniciará."
}} catch {{
    "Error: $_"
}}
""", timeout=30)
        return f"🔄 {out}"

    if action in ("activar_restauracion", "enable_restore"):
        drive = params.get("drive", "C:\\")
        _ps(f'Enable-ComputerRestore -Drive "{drive}"')
        return f"🔄 Restauración del sistema habilitada en {drive}."

    if action in ("desactivar_restauracion", "disable_restore"):
        drive = params.get("drive", "C:\\")
        _ps(f'Disable-ComputerRestore -Drive "{drive}"')
        return f"🔄 Restauración del sistema deshabilitada en {drive}."

    return f"Acción de restauración desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# GESTIÓN AVANZADA DEL REGISTRO
# ══════════════════════════════════════════════════════════════════════════════

def _registry_advanced(action: str, params: dict) -> str:
    hive  = params.get("hive", "HKCU").upper()
    key   = params.get("key", "")

    if action in ("backup_registro", "registry_backup", "exportar_registro"):
        out_file = params.get(
            "output",
            str(Path.home() / "Desktop" / "nexo_registry_backup.reg")
        )
        hive_key = f"{hive}\\{key}" if key else hive
        out = _cmd(f'reg export "{hive_key}" "{out_file}" /y')
        return f"📤 Backup del registro exportado a '{out_file}'."

    if action in ("buscar_registro", "search_registry", "registry_search"):
        query  = params.get("query", params.get("search", ""))
        if not query:
            return "❌ Especificá query (texto a buscar)."
        scope  = params.get("hive", "HKCU")
        out = _ps(f"""
$results = @()
try {{
    Get-ChildItem -Path '{scope}:\\' -Recurse -ErrorAction SilentlyContinue |
    ForEach-Object {{
        $path = $_.PSPath
        try {{
            $props = Get-ItemProperty -Path $path -ErrorAction SilentlyContinue
            $props.PSObject.Properties | Where-Object {{ $_.Value -like '*{query}*' -or $_.Name -like '*{query}*' }} |
            ForEach-Object {{ $results += "$path → $($_.Name) = $($_.Value)" }}
        }} catch {{}}
    }}
    if ($results.Count -gt 0) {{ ($results | Select-Object -First 20) -join "`n" }}
    else {{ "No se encontraron coincidencias para '{query}'." }}
}} catch {{
    "Error al buscar: $_"
}}
""", timeout=60)
        return f"🔍 Resultados en registro para '{query}':\n{out[:3000]}"

    if action in ("importar_registro", "registry_import"):
        path = params.get("path", params.get("file", ""))
        if not path or not Path(path).exists():
            return "❌ Especificá path de un archivo .reg válido."
        out = _cmd(f'reg import "{path}"')
        return f"📥 Registro importado desde '{path}'."

    if action in ("listar_subclaves", "list_subkeys", "registry_list"):
        if not key:
            return "❌ Especificá hive y key."
        out = _ps(f"Get-ChildItem -Path '{hive}:\\{key}' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty PSChildName | Out-String")
        return f"🔧 Subclaves de {hive}\\{key}:\n{out[:2000]}"

    return f"Acción de registro avanzado desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# GESTIÓN DE INICIO DEL SISTEMA (AVANZADO)
# ══════════════════════════════════════════════════════════════════════════════

def _startup_advanced(action: str, params: dict) -> str:
    if action in ("listar_inicio", "list_startup", "startup_list"):
        # Registry locations for startup apps
        out = _ps("""
$paths = @(
    'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run',
    'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run',
    'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce',
    'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce'
)
$results = @()
foreach ($p in $paths) {
    try {
        $hive = $p.Split(':')[0]
        Get-ItemProperty -Path $p -ErrorAction SilentlyContinue |
        Get-Member -MemberType NoteProperty |
        Where-Object { $_.Name -notin ('PSPath','PSParentPath','PSChildName','PSDrive','PSProvider') } |
        ForEach-Object { $results += "[$hive] $($_.Name)" }
    } catch {}
}
# Also check Task Scheduler
Get-ScheduledTask -ErrorAction SilentlyContinue |
  Where-Object { $_.Settings.StartWhenAvailable -or $_.Triggers.TriggerType -eq 'Boot' -or $_.Triggers.TriggerType -eq 'Logon' } |
  Select-Object -First 10 -ExpandProperty TaskName |
  ForEach-Object { $results += "[Scheduler] $_" }
$results -join "`n"
""")
        return f"🚀 Apps de inicio del sistema:\n{out[:3000]}"

    if action in ("habilitar_inicio", "enable_startup"):
        app = params.get("name", params.get("app", ""))
        if not app:
            return "❌ Especificá name de la app."
        # Try Task Scheduler first, then registry
        out = _ps(f"""
$task = Get-ScheduledTask -TaskName '*{app}*' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($task) {{
    Enable-ScheduledTask -TaskName $task.TaskName
    "Tarea '$($task.TaskName)' habilitada en Scheduler."
}} else {{
    "No se encontró tarea de inicio para '{app}'. Verificá el nombre exacto."
}}
""")
        return f"🚀 {out}"

    if action in ("deshabilitar_inicio_reg", "disable_startup_reg"):
        app = params.get("name", params.get("app", ""))
        hive_path = params.get("hive", "HKCU")
        if not app:
            return "❌ Especificá name de la app."
        # Remove from registry Run keys
        _ps(f"""
$paths = @('HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run', 'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run')
foreach ($p in $paths) {{
    Remove-ItemProperty -Path $p -Name '{app}' -ErrorAction SilentlyContinue
}}
""")
        return f"🚀 App '{app}' eliminada de inicio automático (registro)."

    if action in ("agregar_inicio", "add_startup"):
        app  = params.get("name", params.get("app", ""))
        path = params.get("path", params.get("command", ""))
        scope = params.get("scope", "user").lower()  # user | system
        if not app or not path:
            return "❌ Especificá name y path (comando a ejecutar)."
        hive_path = (
            r"Software\Microsoft\Windows\CurrentVersion\Run"
        )
        hive = "HKCU" if scope == "user" else "HKLM"
        result = _reg_write(hive, hive_path, app, path)
        if result is True:
            return f"🚀 '{app}' agregada al inicio del sistema ({hive})."
        return f"❌ Error: {result}"

    return f"Acción de inicio avanzado desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# REGISTRO DE WINDOWS
# ══════════════════════════════════════════════════════════════════════════════

def _registry(action: str, params: dict) -> str:
    hive  = params.get("hive", "HKCU").upper()
    key   = params.get("key", "")
    name  = params.get("name", params.get("value_name", ""))
    value = params.get("value", "")

    if action in ("leer", "read", "get"):
        if not key:
            return "❌ Especificá hive y key."
        if name:
            result = _reg_read(hive, key, name)
            return f"🔧 {hive}\\{key}\\{name} = {result}"
        # List all values in key
        out = _ps(f"Get-ItemProperty -Path '{hive}:\\{key}' -ErrorAction SilentlyContinue | Format-List | Out-String")
        return f"🔧 {hive}\\{key}:\n{out[:2000]}"

    if action in ("escribir", "write", "set"):
        if not key or not name:
            return "❌ Especificá hive, key, name y value."
        reg_type = params.get("type", "REG_SZ").upper()
        type_map = {
            "REG_SZ": winreg.REG_SZ,
            "REG_DWORD": winreg.REG_DWORD,
            "REG_BINARY": winreg.REG_BINARY,
            "REG_EXPAND_SZ": winreg.REG_EXPAND_SZ,
        }
        rtype = type_map.get(reg_type, winreg.REG_SZ)
        if rtype == winreg.REG_DWORD:
            value = int(value)
        result = _reg_write(hive, key, name, value, rtype)
        if result is True:
            return f"✅ Registro guardado: {hive}\\{key}\\{name} = {value}"
        return f"❌ Error: {result}"

    if action in ("eliminar", "delete", "del"):
        if not key or not name:
            out = _ps(f"Remove-Item -Path '{hive}:\\{key}' -Recurse -ErrorAction Stop")
            return f"🗑 Clave {hive}\\{key} eliminada."
        out = _ps(f"Remove-ItemProperty -Path '{hive}:\\{key}' -Name '{name}' -ErrorAction Stop")
        return f"🗑 Valor {hive}\\{key}\\{name} eliminado."

    if action in ("exportar", "export"):
        out_file = params.get("output", f"C:\\Users\\{os.getenv('USERNAME')}\\Desktop\\registry_export.reg")
        _cmd(f'reg export "{hive}\\{key}" "{out_file}" /y')
        return f"📤 Registro exportado a '{out_file}'."

    return f"Acción de registro desconocida: '{action}'. Opciones: leer, escribir, eliminar, exportar."


# ══════════════════════════════════════════════════════════════════════════════
# ACCESIBILIDAD
# ══════════════════════════════════════════════════════════════════════════════

def _accessibility(action: str, params: dict) -> str:
    if action in ("lupa", "magnifier"):
        val = str(params.get("value", "toggle")).lower()
        if val in ("on", "activar"):
            subprocess.Popen("magnify.exe", shell=True)
            return "🔍 Lupa activada."
        if val in ("off", "desactivar"):
            _ps("Stop-Process -Name magnify -ErrorAction SilentlyContinue")
            return "🔍 Lupa desactivada."
        subprocess.Popen("magnify.exe", shell=True)
        return "🔍 Lupa abierta."

    if action in ("narrador", "narrator"):
        val = str(params.get("value", "toggle")).lower()
        if val in ("on", "activar"):
            subprocess.Popen("narrator.exe", shell=True)
            return "🔊 Narrador activado."
        if val in ("off", "desactivar"):
            _ps("Stop-Process -Name narrator -ErrorAction SilentlyContinue")
            return "🔊 Narrador desactivado."
        subprocess.Popen("narrator.exe", shell=True)
        return "🔊 Narrador abierto."

    if action in ("contraste_alto", "high_contrast"):
        val = str(params.get("value", "toggle")).lower()
        if val in ("on", "activar"):
            _ps("(Add-Type -Assembly System.Windows.Forms -PassThru); [System.Windows.Forms.SystemInformation]::HighContrast")
            _reg_write("HKCU", r"Control Panel\Accessibility\HighContrast", "Flags", "127")
            return "🎨 Alto contraste activado. Cerrá y abrí sesión para aplicar."
        _reg_write("HKCU", r"Control Panel\Accessibility\HighContrast", "Flags", "126")
        return "🎨 Alto contraste desactivado."

    if action in ("teclas_adhesivas", "sticky_keys"):
        subprocess.Popen("start ms-settings:easeofaccess-keyboard", shell=True)
        return "⌨️ Configuración de accesibilidad del teclado abierta."

    if action in ("accesibilidad", "accessibility_settings"):
        subprocess.Popen("start ms-settings:easeofaccess", shell=True)
        return "♿ Centro de accesibilidad abierto."

    if action in ("tamanio_texto", "text_size", "font_size"):
        subprocess.Popen("start ms-settings:easeofaccess-display", shell=True)
        return "🔤 Configuración de tamaño de texto abierta."

    return f"Acción de accesibilidad desconocida: '{action}'."


# ══════════════════════════════════════════════════════════════════════════════
# ABRE PANEL DE CONTROL / CONFIGURACION DIRECTA
# ══════════════════════════════════════════════════════════════════════════════

def _open_settings(action: str, params: dict) -> str:
    panels = {
        "configuracion":   "start ms-settings:",
        "panel_control":   "control",
        "actualizaciones": "start ms-settings:windowsupdate",
        "pantalla":        "start ms-settings:display",
        "sonido":          "start ms-settings:sound",
        "red":             "start ms-settings:network",
        "bluetooth":       "start ms-settings:bluetooth",
        "impresoras":      "start ms-settings:printers",
        "usuarios":        "start ms-settings:accounts",
        "aplicaciones":    "start ms-settings:appsfeatures",
        "fecha_hora":      "start ms-settings:dateandtime",
        "idioma":          "start ms-settings:regionlanguage",
        "energia":         "start ms-settings:powersleep",
        "almacenamiento":  "start ms-settings:storagesense",
        "privacidad":      "start ms-settings:privacy",
        "accesibilidad":   "start ms-settings:easeofaccess",
        "personalizacion": "start ms-settings:personalization",
        "dispositivos":    "start ms-settings:devices",
        "sistema":         "start ms-settings:about",
        "gaming":          "start ms-settings:gaming",
        "busqueda":        "start ms-settings:cortana",
        "inicio":          "start ms-settings:startupapps",
        "defrag":          "dfrgui",
        "administrador":   "compmgmt.msc",
        "servicios_panel": "services.msc",
        "regedit":         "regedit",
        "task_scheduler":  "taskschd.msc",
        "event_viewer":    "eventvwr.msc",
        "firewall_panel":  "WF.msc",
        "msconfig":        "msconfig",
        "dxdiag":          "dxdiag",
    }
    cmd_str = panels.get(action, "")
    if cmd_str:
        subprocess.Popen(cmd_str, shell=True)
        return f"⚙️ Panel abierto: {action}"
    return f"Panel desconocido: '{action}'"


# ══════════════════════════════════════════════════════════════════════════════
# ROUTER PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

_CATEGORY_MAP = {
    # Pantalla
    "brillo": ("display", "brillo"), "brightness": ("display", "brillo"),
    "resolucion": ("display", "resolucion"), "resolution": ("display", "resolucion"),
    "frecuencia": ("display", "frecuencia"), "hz": ("display", "frecuencia"), "refresh_rate": ("display", "frecuencia"),
    "escalado": ("display", "escalado"), "dpi": ("display", "escalado"), "scaling": ("display", "escalado"),
    "monitores": ("display", "monitores"), "monitors": ("display", "monitores"),
    "noche": ("display", "noche"), "night_light": ("display", "noche"),
    "orientacion": ("display", "orientacion"), "rotation": ("display", "orientacion"),
    "hdr": ("display", "hdr"),
    # Audio
    "volumen": ("audio", "volumen"), "volume": ("audio", "volumen"),
    "mute": ("audio", "mute"), "silenciar": ("audio", "silenciar"),
    "dispositivos_audio": ("audio", "dispositivos_audio"), "audio_devices": ("audio", "dispositivos_audio"),
    "volumen_mic": ("audio", "volumen_mic"), "mic_volume": ("audio", "volumen_mic"),
    "sonido_configuracion": ("audio", "sonido_configuracion"),
    # Red
    "wifi_list": ("network", "wifi_list"), "redes_wifi": ("network", "wifi_list"), "redes": ("network", "wifi_list"),
    "wifi_connect": ("network", "wifi_connect"), "conectar_wifi": ("network", "wifi_connect"),
    "wifi_disconnect": ("network", "wifi_disconnect"), "desconectar_wifi": ("network", "wifi_disconnect"),
    "wifi_off": ("network", "wifi_off"), "wifi_on": ("network", "wifi_on"),
    "wifi_info": ("network", "wifi_info"), "info_red": ("network", "wifi_info"),
    "ip": ("network", "ip"), "ip_info": ("network", "ip"),
    "dns": ("network", "dns"), "dns_reset": ("network", "dns_reset"),
    "flush_dns": ("network", "flush_dns"), "limpiar_dns": ("network", "flush_dns"),
    "modo_avion": ("network", "modo_avion"), "airplane_mode": ("network", "modo_avion"),
    "bluetooth_on": ("network", "bluetooth_on"), "bluetooth_off": ("network", "bluetooth_off"),
    "bluetooth_devices": ("network", "bluetooth_devices"),
    "proxy_on": ("network", "proxy_on"), "proxy_off": ("network", "proxy_off"),
    "velocidad_red": ("network", "velocidad_red"), "ping": ("network", "velocidad_red"),
    # Energía
    "plan_energia": ("power", "plan_energia"), "power_plan": ("power", "plan_energia"),
    "suspender": ("power", "suspender"), "sleep": ("power", "suspender"),
    "hibernar": ("power", "hibernar"), "hibernate": ("power", "hibernar"),
    "apagar_pantalla": ("power", "suspender_pantalla"), "screen_off": ("power", "suspender_pantalla"),
    "tiempo_suspension": ("power", "tiempo_suspension"), "sleep_timeout": ("power", "tiempo_suspension"),
    "tiempo_pantalla": ("power", "tiempo_pantalla"), "display_timeout": ("power", "tiempo_pantalla"),
    "bateria": ("power", "bateria"), "battery": ("power", "bateria"),
    "ahorro_bateria": ("power", "ahorro_bateria"), "battery_saver": ("power", "ahorro_bateria"),
    "inicio_rapido": ("power", "inicio_rapido"), "fast_startup": ("power", "inicio_rapido"),
    # Sistema
    "info": ("system", "info"), "sistema_info": ("system", "info"),
    "nombre_pc": ("system", "nombre_pc"), "computer_name": ("system", "nombre_pc"), "hostname": ("system", "nombre_pc"),
    "fecha_hora": ("system", "fecha_hora"), "datetime": ("system", "fecha_hora"),
    "zona_horaria": ("system", "zona_horaria"), "timezone": ("system", "zona_horaria"),
    "idioma": ("system", "idioma"), "language": ("system", "idioma"),
    "reiniciar": ("system", "reiniciar"), "restart": ("system", "reiniciar"),
    "apagar": ("system", "apagar"), "shutdown": ("system", "apagar"),
    "cancelar_apagado": ("system", "cancelar_apagado"),
    "bloquear": ("system", "bloquear"), "lock": ("system", "bloquear"),
    "cerrar_sesion": ("system", "cerrar_sesion"), "logoff": ("system", "cerrar_sesion"),
    "rendimiento": ("system", "rendimiento"), "performance_info": ("system", "rendimiento"),
    "variables_entorno": ("system", "variables_entorno"), "env_vars": ("system", "variables_entorno"),
    "set_env": ("system", "set_env"), "crear_variable": ("system", "set_env"),
    "delete_env": ("system", "delete_env"), "eliminar_variable": ("system", "delete_env"),
    "actualizaciones": ("system", "actualizaciones"), "windows_update": ("system", "actualizaciones"),
    "activacion": ("system", "activacion"),
    # Personalización
    "fondo": ("personalization", "fondo"), "wallpaper": ("personalization", "fondo"),
    "tema": ("personalization", "tema"), "theme": ("personalization", "tema"),
    "color_acento": ("personalization", "color_acento"),
    "barra_tareas": ("personalization", "barra_tareas"), "taskbar": ("personalization", "barra_tareas"),
    "protector_pantalla": ("personalization", "protector_pantalla"), "screensaver": ("personalization", "protector_pantalla"),
    "transparencia": ("personalization", "transparencia"), "transparency": ("personalization", "transparencia"),
    "pantalla_bloqueo": ("personalization", "pantalla_bloqueo"),
    "fuentes": ("personalization", "fuentes"), "fonts": ("personalization", "fuentes"),
    "cursor": ("personalization", "cursor"),
    # Apps
    "lista_apps": ("apps", "lista_apps"), "installed_apps": ("apps", "lista_apps"),
    "desinstalar": ("apps", "desinstalar"), "uninstall": ("apps", "desinstalar"),
    "inicio_apps": ("apps", "inicio_apps"), "startup_apps": ("apps", "inicio_apps"),
    "apps_predeterminadas": ("apps", "apps_predeterminadas"),
    # Seguridad
    "defender_scan": ("security", "defender_scan"), "antivirus_scan": ("security", "defender_scan"),
    "defender_estado": ("security", "defender_estado"),
    "firewall_status": ("security", "firewall_status"),
    "firewall_on": ("security", "firewall_on"), "firewall_off": ("security", "firewall_off"),
    "uac": ("security", "uac"),
    "bitlocker_status": ("security", "bitlocker_status"),
    "usuarios": ("security", "usuarios"),
    # Input
    "velocidad_mouse": ("input", "velocidad_mouse"), "mouse_speed": ("input", "velocidad_mouse"),
    "doble_click": ("input", "doble_click"), "scroll_mouse": ("input", "scroll_mouse"),
    "boton_mouse": ("input", "boton_mouse"), "swap_buttons": ("input", "boton_mouse"),
    "velocidad_teclado": ("input", "velocidad_teclado"), "keyboard_speed": ("input", "velocidad_teclado"),
    "retardo_teclado": ("input", "retardo_teclado"), "idioma_teclado": ("input", "idioma_teclado"),
    "teclado_tactil": ("input", "teclado_tactil"), "osk": ("input", "teclado_tactil"),
    # Storage
    "discos": ("storage", "discos"), "espacio": ("storage", "discos"),
    "limpieza_disco": ("storage", "limpieza_disco"), "disk_cleanup": ("storage", "limpieza_disco"),
    "papelera": ("storage", "papelera"), "vaciar_papelera": ("storage", "papelera"),
    "empty_trash": ("storage", "papelera"), "empty_recycle_bin": ("storage", "papelera"),
    "recycle_bin": ("storage", "papelera"),
    "temp_files": ("storage", "temp_files"), "limpiar_temp": ("storage", "temp_files"),
    "desfragmentar": ("storage", "desfragmentar"), "defrag": ("storage", "desfragmentar"),
    "error_disco": ("storage", "error_disco"), "chkdsk": ("storage", "error_disco"),
    # Servicios
    "listar_servicios": ("services", "listar_servicios"), "servicios": ("services", "listar_servicios"),
    "iniciar_servicio": ("services", "iniciar_servicio"), "start_service": ("services", "iniciar_servicio"),
    "detener_servicio": ("services", "detener_servicio"), "stop_service": ("services", "detener_servicio"),
    "reiniciar_servicio": ("services", "reiniciar_servicio"), "restart_service": ("services", "reiniciar_servicio"),
    "listar_procesos": ("services", "listar_procesos"), "procesos": ("services", "listar_procesos"),
    "terminar_proceso": ("services", "terminar_proceso"), "kill": ("services", "terminar_proceso"),
    # Privacidad
    "camara_privacidad": ("privacy", "camara_privacidad"),
    "microfono_privacidad": ("privacy", "microfono_privacidad"),
    "ubicacion": ("privacy", "ubicacion"), "telemetria": ("privacy", "telemetria"),
    "no_molestar": ("privacy", "no_molestar"), "focus_assist": ("privacy", "no_molestar"), "dnd": ("privacy", "no_molestar"),
    "notificaciones": ("privacy", "notificaciones"),
    "portapapeles": ("privacy", "portapapeles"), "clipboard": ("privacy", "portapapeles"),
    "publicidad": ("privacy", "publicidad"),
    # Registro
    "registro_leer": ("registry", "leer"), "registry_read": ("registry", "leer"),
    "registro_escribir": ("registry", "escribir"), "registry_write": ("registry", "escribir"),
    "registro_eliminar": ("registry", "eliminar"), "registry_delete": ("registry", "eliminar"),
    # Accesibilidad
    "lupa": ("accessibility", "lupa"), "magnifier": ("accessibility", "lupa"),
    "narrador": ("accessibility", "narrador"), "narrator": ("accessibility", "narrador"),
    "contraste_alto": ("accessibility", "contraste_alto"), "high_contrast": ("accessibility", "contraste_alto"),
    "accesibilidad": ("accessibility", "accesibilidad"),
    # Temperatura CPU
    "temperatura_cpu": ("cpu_temp", "temperatura_cpu"), "cpu_temp": ("cpu_temp", "temperatura_cpu"),
    "temperatura": ("cpu_temp", "temperatura_cpu"),
    # Escritorios virtuales
    "nuevo_escritorio": ("virtual_desktops", "nuevo_escritorio"), "new_desktop": ("virtual_desktops", "nuevo_escritorio"),
    "cerrar_escritorio": ("virtual_desktops", "cerrar_escritorio"), "close_desktop": ("virtual_desktops", "cerrar_escritorio"),
    "siguiente_escritorio": ("virtual_desktops", "siguiente_escritorio"), "next_desktop": ("virtual_desktops", "siguiente_escritorio"),
    "anterior_escritorio": ("virtual_desktops", "anterior_escritorio"), "prev_desktop": ("virtual_desktops", "anterior_escritorio"),
    "vista_tareas": ("virtual_desktops", "vista_tareas"), "task_view": ("virtual_desktops", "vista_tareas"),
    # Impresoras
    "listar_impresoras": ("printers", "listar_impresoras"), "list_printers": ("printers", "listar_impresoras"), "impresoras": ("printers", "listar_impresoras"),
    "impresora_predeterminada": ("printers", "impresora_predeterminada"), "set_default_printer": ("printers", "impresora_predeterminada"),
    "imprimir_prueba": ("printers", "imprimir_prueba"), "print_test": ("printers", "imprimir_prueba"),
    "cola_impresion": ("printers", "cola_impresion"), "print_queue": ("printers", "cola_impresion"),
    # Fuentes avanzado
    "listar_fuentes": ("fonts_adv", "listar_fuentes"), "list_fonts": ("fonts_adv", "listar_fuentes"),
    "instalar_fuente": ("fonts_adv", "instalar_fuente"), "install_font": ("fonts_adv", "instalar_fuente"),
    "eliminar_fuente": ("fonts_adv", "eliminar_fuente"), "uninstall_font": ("fonts_adv", "eliminar_fuente"),
    # Control de ventanas
    "listar_ventanas": ("windows", "listar_ventanas"), "list_windows": ("windows", "listar_ventanas"),
    "maximizar_ventana": ("windows", "maximizar_ventana"), "maximize_window": ("windows", "maximizar_ventana"),
    "minimizar_ventana": ("windows", "minimizar_ventana"), "minimize_window": ("windows", "minimizar_ventana"),
    "restaurar_ventana": ("windows", "restaurar_ventana"), "restore_window": ("windows", "restaurar_ventana"),
    "cerrar_ventana": ("windows", "cerrar_ventana"), "close_window": ("windows", "cerrar_ventana"),
    "mover_ventana": ("windows", "mover_ventana"), "move_window": ("windows", "mover_ventana"),
    "enfocar_ventana": ("windows", "enfocar_ventana"), "focus_window": ("windows", "enfocar_ventana"),
    # Puntos de restauración
    "crear_punto_restauracion": ("restore", "crear_punto_restauracion"), "create_restore_point": ("restore", "crear_punto_restauracion"),
    "listar_puntos_restauracion": ("restore", "listar_puntos_restauracion"), "list_restore_points": ("restore", "listar_puntos_restauracion"),
    "restaurar_sistema": ("restore", "restaurar_sistema"), "restore_system": ("restore", "restaurar_sistema"),
    # Registro avanzado
    "backup_registro": ("registry_adv", "backup_registro"), "registry_backup": ("registry_adv", "backup_registro"),
    "buscar_registro": ("registry_adv", "buscar_registro"), "search_registry": ("registry_adv", "buscar_registro"),
    "importar_registro": ("registry_adv", "importar_registro"), "registry_import": ("registry_adv", "importar_registro"),
    "listar_subclaves": ("registry_adv", "listar_subclaves"), "list_subkeys": ("registry_adv", "listar_subclaves"),
    # Inicio avanzado
    "listar_inicio": ("startup_adv", "listar_inicio"), "list_startup": ("startup_adv", "listar_inicio"),
    "habilitar_inicio": ("startup_adv", "habilitar_inicio"), "enable_startup": ("startup_adv", "habilitar_inicio"),
    "deshabilitar_inicio_reg": ("startup_adv", "deshabilitar_inicio_reg"), "disable_startup_reg": ("startup_adv", "deshabilitar_inicio_reg"),
    "agregar_inicio": ("startup_adv", "agregar_inicio"), "add_startup": ("startup_adv", "agregar_inicio"),
}

_HANDLERS = {
    "display":          _display,
    "audio":            _audio,
    "network":          _network,
    "power":            _power,
    "system":           _system,
    "personalization":  _personalization,
    "apps":             _apps,
    "security":         _security,
    "input":            _input_devices,
    "storage":          _storage,
    "services":         _services,
    "privacy":          _privacy,
    "registry":         _registry,
    "accessibility":    _accessibility,
    # New handlers
    "cpu_temp":         _cpu_temperature,
    "virtual_desktops": _virtual_desktops,
    "printers":         _printers,
    "fonts_adv":        _fonts_advanced,
    "windows":          _window_control,
    "restore":          _system_restore,
    "registry_adv":     _registry_advanced,
    "startup_adv":      _startup_advanced,
}


def _is_admin() -> bool:
    """Check if running as administrator."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _auto_elevate(script_block: str) -> str:
    """Run a PowerShell command with auto-elevation if needed.
    Uses Start-Process -Verb RunAs for admin commands."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-Command",
             f"""
             $psi = New-Object System.Diagnostics.ProcessStartInfo;
             $psi.FileName = 'powershell.exe';
             $psi.Arguments = '-NoProfile -NonInteractive -Command & {{{script_block}}}';
             $psi.Verb = 'RunAs';
             $psi.UseShellExecute = $true;
             $psi.WindowStyle = 'Hidden';
             $p = [System.Diagnostics.Process]::Start($psi);
             if ($p) {{ $p.WaitForExit(); 'OK' }} else {{ 'FAILED' }}
             """],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        return (r.stdout or "").strip() or (r.stderr or "").strip()
    except Exception as e:
        return f"[Error] {e}"


def _cmd_elevated(cmd: str, timeout: int = 30) -> str:
    """Run a cmd.exe command elevated (if not already admin)."""
    if _is_admin():
        return _cmd(cmd, timeout)
    # Wrap in PowerShell RunAs
    escaped = cmd.replace("'", "''")
    return _auto_elevate(f"cmd.exe /c '{escaped}'")


def windows_settings(parameters: dict, response=None, player=None, session_memory=None) -> str:
    params   = parameters or {}
    action   = params.get("action", "").lower().strip().replace(" ", "_")
    category = params.get("category", "").lower().strip()

    _log(player, f"action={action} category={category}")

    # Admin-required actions
    admin_actions = {
        "defender_scan", "firewall_on", "firewall_off", "uac", "bitlocker",
        "set_timezone", "set_datetime", "set_hostname", "restart", "shutdown",
        "install_app", "uninstall", "set_dns", "flush_dns", "wifi_on",
        "wifi_off", "airplane_on", "airplane_off", "bluetooth_on", "bluetooth_off",
        "set_brightness", "set_resolution", "set_scaling", "hdr_off", "hdr_on",
    }
    needs_admin = action in admin_actions or any(a in action for a in admin_actions)

    # Direct category dispatch
    if category and category in _HANDLERS:
        return _HANDLERS[category](action, params)

    # Auto-detect category from action
    if action in _CATEGORY_MAP:
        cat, mapped_action = _CATEGORY_MAP[action]
        return _HANDLERS[cat](mapped_action, params)

    # Open settings panels directly
    if action in ("abrir", "open", "panel", "abrir_panel"):
        target = params.get("target", params.get("panel", action))
        return _open_settings(target, params)

    # Try open_settings with action name itself
    result = _open_settings(action, params)
    if "desconocido" not in result:
        return result

    return (
        f"🔧 Acción '{action}' no reconocida.\n\n"
        "Categorías disponibles:\n"
        "  pantalla: brillo, resolucion, frecuencia, escalado, noche, orientacion, hdr\n"
        "  audio: volumen, mute, dispositivos_audio\n"
        "  red: wifi_list, wifi_connect, wifi_info, ip, dns, bluetooth_on/off, modo_avion\n"
        "  energia: plan_energia, suspender, hibernar, bateria, tiempo_pantalla\n"
        "  sistema: info, nombre_pc, fecha_hora, zona_horaria, reiniciar, apagar, rendimiento\n"
        "  personalizacion: fondo, tema, barra_tareas, transparencia, protector_pantalla\n"
        "  apps: lista_apps, desinstalar, inicio_apps\n"
        "  seguridad: defender_scan, firewall_on/off, uac, usuarios\n"
        "  input: velocidad_mouse, doble_click, scroll_mouse, velocidad_teclado\n"
        "  almacenamiento: discos, papelera, limpiar_temp, desfragmentar\n"
        "  servicios: listar_servicios, iniciar/detener/reiniciar_servicio, procesos, kill\n"
        "  privacidad: no_molestar, camara_privacidad, telemetria, portapapeles\n"
        "  registro: registro_leer, registro_escribir, registro_eliminar\n"
        "  accesibilidad: lupa, narrador, contraste_alto\n"
        "  temperatura: temperatura_cpu\n"
        "  escritorios_virtuales: nuevo_escritorio, cerrar_escritorio, siguiente_escritorio, anterior_escritorio\n"
        "  impresoras: listar_impresoras, impresora_predeterminada, imprimir_prueba, cola_impresion\n"
        "  fuentes: listar_fuentes, instalar_fuente, eliminar_fuente\n"
        "  ventanas: listar_ventanas, maximizar_ventana, minimizar_ventana, mover_ventana, enfocar_ventana\n"
        "  restauracion: crear_punto_restauracion, listar_puntos_restauracion, restaurar_sistema\n"
        "  registro_avanzado: backup_registro, buscar_registro, importar_registro\n"
        "  inicio_avanzado: listar_inicio, habilitar_inicio, agregar_inicio, deshabilitar_inicio_reg"
    )
