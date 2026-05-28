"""
system_monitor.py — Monitor de rendimiento del sistema para NEXO.

Muestra: CPU, RAM, GPU, disco, red, temperatura, batería,
         procesos top, y resumen general de rendimiento.

Requiere: pip install psutil  (casi siempre ya está instalado)
Opcional: pip install gputil  (para info GPU NVIDIA)
          pip install pynvml  (alternativa NVIDIA)
"""
from __future__ import annotations

import platform
import time
from datetime import timedelta


def _log(player, msg: str):
    print(f"[SysMonitor] {msg}")
    if player:
        player.write_log(f"[monitor] {msg}")


def _get_psutil():
    try:
        import psutil
        return psutil
    except ImportError:
        return None


def _bar(pct: float, width: int = 10) -> str:
    filled = int(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


# ── CPU ───────────────────────────────────────────────────────────────────────

def _cpu_info() -> str:
    ps = _get_psutil()
    if not ps:
        return "❌ psutil no instalado. Ejecutá: pip install psutil"

    pct     = ps.cpu_percent(interval=0.5)
    freq    = ps.cpu_freq()
    cores   = ps.cpu_count(logical=False)
    threads = ps.cpu_count(logical=True)
    load    = ps.getloadavg() if hasattr(ps, "getloadavg") else (0, 0, 0)

    lines = [
        f"🖥️ CPU  {_bar(pct)} {pct:.1f}%",
        f"   Núcleos: {cores} físicos / {threads} lógicos",
    ]
    if freq:
        lines.append(f"   Frecuencia: {freq.current:.0f} MHz (máx {freq.max:.0f} MHz)")
    if load[0]:
        lines.append(f"   Carga (1/5/15 min): {load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f}")

    # Top 3 procesos por CPU
    procs = sorted(ps.process_iter(["pid", "name", "cpu_percent"]),
                   key=lambda p: p.info["cpu_percent"] or 0, reverse=True)[:3]
    if procs:
        lines.append("   Top CPU:")
        for p in procs:
            lines.append(f"     • {p.info['name']} (PID {p.info['pid']}): {p.info['cpu_percent']:.1f}%")

    return "\n".join(lines)


# ── RAM ───────────────────────────────────────────────────────────────────────

def _ram_info() -> str:
    ps = _get_psutil()
    if not ps:
        return "❌ psutil no instalado."

    mem  = ps.virtual_memory()
    swap = ps.swap_memory()

    def gb(b): return b / 1024 ** 3

    lines = [
        f"💾 RAM  {_bar(mem.percent)} {mem.percent:.1f}%",
        f"   Usada: {gb(mem.used):.1f} GB / Total: {gb(mem.total):.1f} GB  "
        f"(Libre: {gb(mem.available):.1f} GB)",
    ]
    if swap.total > 0:
        lines.append(
            f"   Swap: {gb(swap.used):.1f} GB / {gb(swap.total):.1f} GB  ({swap.percent:.1f}%)"
        )

    # Top 3 procesos por RAM
    procs = sorted(
        ps.process_iter(["pid", "name", "memory_percent"]),
        key=lambda p: p.info["memory_percent"] or 0, reverse=True,
    )[:3]
    if procs:
        lines.append("   Top RAM:")
        for p in procs:
            lines.append(f"     • {p.info['name']} (PID {p.info['pid']}): {p.info['memory_percent']:.1f}%")

    return "\n".join(lines)


# ── DISCO ─────────────────────────────────────────────────────────────────────

def _disk_info() -> str:
    ps = _get_psutil()
    if not ps:
        return "❌ psutil no instalado."

    def gb(b): return b / 1024 ** 3

    lines = ["💿 Discos:"]
    for part in ps.disk_partitions():
        try:
            usage = ps.disk_usage(part.mountpoint)
            lines.append(
                f"   {part.device} ({part.fstype})  "
                f"{_bar(usage.percent)} {usage.percent:.1f}%  "
                f"{gb(usage.used):.1f}/{gb(usage.total):.1f} GB"
            )
        except PermissionError:
            lines.append(f"   {part.device}: sin acceso")

    try:
        io = ps.disk_io_counters()
        if io:
            lines.append(
                f"   I/O total: Lectura {gb(io.read_bytes):.1f} GB  "
                f"| Escritura {gb(io.write_bytes):.1f} GB"
            )
    except Exception:
        pass

    return "\n".join(lines)


# ── RED ───────────────────────────────────────────────────────────────────────

def _network_info() -> str:
    ps = _get_psutil()
    if not ps:
        return "❌ psutil no instalado."

    def mb(b): return b / 1024 ** 2

    io1 = ps.net_io_counters()
    time.sleep(1)
    io2 = ps.net_io_counters()
    sent_mb  = (io2.bytes_sent - io1.bytes_sent) / 1024
    recv_mb  = (io2.bytes_recv - io1.bytes_recv) / 1024

    lines = [
        f"🌐 Red (velocidad en tiempo real):",
        f"   ↑ Subida:  {sent_mb:.1f} KB/s",
        f"   ↓ Bajada:  {recv_mb:.1f} KB/s",
        f"   Total enviado: {mb(io2.bytes_sent):.0f} MB  "
        f"| Total recibido: {mb(io2.bytes_recv):.0f} MB",
    ]

    # Interfaces activas
    addrs = ps.net_if_addrs()
    for iface, addr_list in addrs.items():
        for addr in addr_list:
            if addr.family == 2 and not addr.address.startswith("127."):  # AF_INET IPv4
                lines.append(f"   {iface}: {addr.address}")
                break

    return "\n".join(lines)


# ── GPU ───────────────────────────────────────────────────────────────────────

def _gpu_info() -> str:
    # Intentar con GPUtil (NVIDIA)
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            lines = ["🎮 GPU (NVIDIA):"]
            for gpu in gpus:
                lines.append(
                    f"   {gpu.name}  {_bar(gpu.load * 100)} {gpu.load * 100:.1f}%"
                )
                lines.append(
                    f"   VRAM: {gpu.memoryUsed:.0f}/{gpu.memoryTotal:.0f} MB  "
                    f"({gpu.memoryUtil * 100:.1f}%)"
                )
                lines.append(f"   Temp: {gpu.temperature}°C")
            return "\n".join(lines)
    except ImportError:
        pass

    # Intentar con pynvml
    try:
        import pynvml
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        lines = ["🎮 GPU (NVIDIA via pynvml):"]
        for i in range(count):
            h   = pynvml.nvmlDeviceGetHandleByIndex(i)
            nm  = pynvml.nvmlDeviceGetName(h).decode()
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            util = pynvml.nvmlDeviceGetUtilizationRates(h)
            temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
            lines.append(
                f"   {nm}  {_bar(util.gpu)} {util.gpu}%  "
                f"VRAM {mem.used//1024**2}/{mem.total//1024**2} MB  Temp {temp}°C"
            )
        pynvml.nvmlShutdown()
        return "\n".join(lines)
    except Exception:
        pass

    # Fallback: información básica del sistema
    return "🎮 GPU: Instalá 'pip install gputil' para info detallada de GPU NVIDIA."


# ── TEMPERATURA ───────────────────────────────────────────────────────────────

def _temp_info() -> str:
    ps = _get_psutil()
    if not ps:
        return "❌ psutil no instalado."

    if not hasattr(ps, "sensors_temperatures"):
        return "🌡 Temperatura: No disponible en Windows (requiere HWiNFO/OpenHardwareMonitor)."

    try:
        temps = ps.sensors_temperatures()
        if not temps:
            return "🌡 Temperatura: No se detectaron sensores."
        lines = ["🌡 Temperaturas:"]
        for name, entries in temps.items():
            for e in entries:
                bar = "🔴" if e.current > 85 else "🟡" if e.current > 70 else "🟢"
                lines.append(f"   {bar} {name} / {e.label or 'core'}: {e.current:.1f}°C")
        return "\n".join(lines)
    except Exception as e:
        return f"🌡 Temperatura: No disponible ({e})."


# ── BATERÍA ───────────────────────────────────────────────────────────────────

def _battery_info() -> str:
    ps = _get_psutil()
    if not ps:
        return "❌ psutil no instalado."

    bat = ps.sensors_battery()
    if not bat:
        return "🔋 Batería: No se detectó batería (puede ser PC de escritorio)."

    plug   = "🔌 Cargando" if bat.power_plugged else "🔋 Batería"
    secs   = bat.secsleft
    remain = str(timedelta(seconds=secs)) if secs and secs > 0 else "—"
    return (
        f"{plug}  {_bar(bat.percent)} {bat.percent:.0f}%\n"
        f"   Tiempo restante: {remain}"
    )


# ── PROCESOS ─────────────────────────────────────────────────────────────────

def _top_processes(n: int = 10, sort_by: str = "cpu") -> str:
    ps = _get_psutil()
    if not ps:
        return "❌ psutil no instalado."

    key   = "cpu_percent" if sort_by == "cpu" else "memory_percent"
    emoji = "🖥️" if sort_by == "cpu" else "💾"

    procs = sorted(
        ps.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]),
        key=lambda p: p.info.get(key) or 0, reverse=True,
    )[:n]

    lines = [f"{emoji} Top {n} procesos por {sort_by.upper()}:"]
    for p in procs:
        cpu = p.info.get("cpu_percent") or 0
        mem = p.info.get("memory_percent") or 0
        lines.append(
            f"  {p.info['name'][:30]:<30} PID {p.info['pid']:>6}  "
            f"CPU {cpu:>5.1f}%  RAM {mem:>4.1f}%"
        )
    return "\n".join(lines)


# ── UPTIME ────────────────────────────────────────────────────────────────────

def _uptime_info() -> str:
    ps = _get_psutil()
    if not ps:
        return "❌ psutil no instalado."
    boot  = ps.boot_time()
    delta = timedelta(seconds=time.time() - boot)
    days  = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    mins  = rem // 60
    return f"⏱ Uptime: {days}d {hours}h {mins}m"


# ── REPORTE COMPLETO ──────────────────────────────────────────────────────────

def _full_report() -> str:
    sections = [
        _uptime_info(),
        _cpu_info(),
        _ram_info(),
        _disk_info(),
        _gpu_info(),
        _battery_info(),
    ]
    return "\n\n".join(sections)


# ── KILL PROCESS ──────────────────────────────────────────────────────────────

def _kill_process(name_or_pid: str) -> str:
    ps = _get_psutil()
    if not ps:
        return "❌ psutil no instalado."

    killed = []
    errors = []
    for proc in ps.process_iter(["pid", "name"]):
        try:
            if (str(proc.info["pid"]) == name_or_pid
                    or name_or_pid.lower() in proc.info["name"].lower()):
                proc.kill()
                killed.append(f"{proc.info['name']} (PID {proc.info['pid']})")
        except (ps.NoSuchProcess, ps.AccessDenied) as e:
            errors.append(str(e))

    if killed:
        return f"✅ Proceso(s) terminado(s): {', '.join(killed)}."
    if errors:
        return f"❌ No se pudo terminar: {'; '.join(errors)}"
    return f"❌ No se encontró ningún proceso con '{name_or_pid}'."


# ── DISPATCHER ───────────────────────────────────────────────────────────────

def system_monitor(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params  = parameters or {}
    action  = params.get("action", "report").lower().strip()
    sort_by = params.get("sort_by", "cpu").lower().strip()
    n       = int(params.get("count", 10))

    _log(player, f"action={action}")

    if action in ("cpu",):
        return _cpu_info()

    elif action in ("ram", "memory", "memoria"):
        return _ram_info()

    elif action in ("disk", "disco", "storage", "almacenamiento"):
        return _disk_info()

    elif action in ("network", "net", "red"):
        return _network_info()

    elif action in ("gpu",):
        return _gpu_info()

    elif action in ("temperature", "temp", "temperatura"):
        return _temp_info()

    elif action in ("battery", "batería", "bateria"):
        return _battery_info()

    elif action in ("uptime", "tiempo_encendido"):
        return _uptime_info()

    elif action in ("processes", "procesos", "top", "top_processes"):
        return _top_processes(n=n, sort_by=sort_by)

    elif action in ("kill", "matar", "terminar", "kill_process"):
        target = params.get("name", params.get("process", "")).strip()
        if not target:
            return "❌ Especificá el nombre o PID del proceso a terminar."
        return _kill_process(target)

    elif action in ("report", "resumen", "full", "completo", "performance"):
        return _full_report()

    else:
        return (
            f"Acción desconocida: '{action}'. "
            "Opciones: cpu, ram, disk, network, gpu, temperature, battery, "
            "uptime, processes, kill, report."
        )
