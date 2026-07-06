"""
system_vitals.py — Reports CPU, RAM, disk, battery, and network status
using psutil. Fully cross-platform.
"""

from __future__ import annotations

import psutil


def handle(payload: dict) -> str:
    raw = payload.get("raw", "").lower()

    if "cpu" in raw:
        return _cpu()
    if "ram" in raw or "memory" in raw:
        return _memory()
    if "battery" in raw:
        return _battery()
    if "disk" in raw or "storage" in raw:
        return _disk()
    if "network" in raw:
        return _network()

    # generic "how's my system doing" -> give a short combined summary
    return _summary()


def _cpu() -> str:
    percent = psutil.cpu_percent(interval=0.6)
    cores = psutil.cpu_count(logical=True)
    return f"CPU is at {percent:.0f} percent across {cores} logical cores."


def _memory() -> str:
    mem = psutil.virtual_memory()
    used_gb = mem.used / (1024 ** 3)
    total_gb = mem.total / (1024 ** 3)
    return f"Using {used_gb:.1f} of {total_gb:.1f} gigabytes of RAM, that's {mem.percent:.0f} percent."


def _battery() -> str:
    battery = psutil.sensors_battery()
    if battery is None:
        return "No battery detected — looks like you're on a desktop."
    status = "charging" if battery.power_plugged else "on battery"
    return f"Battery is at {battery.percent:.0f} percent, currently {status}."


def _disk() -> str:
    usage = psutil.disk_usage("/")
    free_gb = usage.free / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)
    return f"You have {free_gb:.0f} gigabytes free out of {total_gb:.0f} total, {usage.percent:.0f} percent used."


def _network() -> str:
    io = psutil.net_io_counters()
    sent_mb = io.bytes_sent / (1024 ** 2)
    recv_mb = io.bytes_recv / (1024 ** 2)
    return f"Since startup: {sent_mb:.0f} megabytes sent, {recv_mb:.0f} megabytes received."


def _summary() -> str:
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    battery = psutil.sensors_battery()
    parts = [f"CPU at {cpu:.0f} percent", f"RAM at {mem.percent:.0f} percent"]
    if battery is not None:
        parts.append(f"battery at {battery.percent:.0f} percent")
    return "Here's the rundown: " + ", ".join(parts) + "."
