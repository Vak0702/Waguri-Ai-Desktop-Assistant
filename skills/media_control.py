"""
media_control.py — Volume and media playback control via OS-level calls.

Windows: uses pycaw for precise volume control + keyboard media keys for
playback. macOS/Linux: uses osascript / amixer + playerctl as available.
"""

from __future__ import annotations

import platform
import re
import subprocess


def handle(raw_text: str) -> str:
    t = raw_text.lower()
    plat = platform.system().lower()

    if "mute" in t and "unmute" not in t:
        return _mute(plat)
    if "unmute" in t:
        return _unmute(plat)

    m = re.search(r"volume\s+(?:to\s+)?(\d{1,3})", t)
    if m:
        return _set_volume(plat, int(m.group(1)))

    if "volume up" in t or "louder" in t:
        return _nudge_volume(plat, +10)
    if "volume down" in t or "quieter" in t:
        return _nudge_volume(plat, -10)

    if "play" in t or "resume" in t:
        return _media_key(plat, "play_pause")
    if "pause" in t:
        return _media_key(plat, "play_pause")
    if "next" in t or "skip" in t:
        return _media_key(plat, "next")
    if "previous" in t:
        return _media_key(plat, "previous")

    return "I didn't catch a specific media action there."


# ---------- Windows (pycaw) ----------

def _get_windows_volume_interface():
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def _set_volume(plat: str, level: int) -> str:
    level = max(0, min(100, level))
    try:
        if plat == "windows":
            vol = _get_windows_volume_interface()
            vol.SetMasterVolumeLevelScalar(level / 100, None)
        elif plat == "darwin":
            subprocess.run(["osascript", "-e", f"set volume output volume {level}"])
        else:
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{level}%"])
        return f"Volume set to {level} percent."
    except Exception as e:
        return f"Couldn't set volume — {e}"


def _nudge_volume(plat: str, delta: int) -> str:
    try:
        if plat == "windows":
            vol = _get_windows_volume_interface()
            current = vol.GetMasterVolumeLevelScalar() * 100
            return _set_volume(plat, int(current + delta))
        elif plat == "darwin":
            direction = "increase" if delta > 0 else "decrease"
            subprocess.run(["osascript", "-e", f"set volume output volume (output volume of (get volume settings) + {delta})"])
            return "Adjusted volume."
        else:
            sign = "+" if delta > 0 else "-"
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{abs(delta)}%{sign}"])
            return "Adjusted volume."
    except Exception as e:
        return f"Couldn't adjust volume — {e}"


def _mute(plat: str) -> str:
    try:
        if plat == "windows":
            vol = _get_windows_volume_interface()
            vol.SetMute(1, None)
        elif plat == "darwin":
            subprocess.run(["osascript", "-e", "set volume with output muted"])
        else:
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "mute"])
        return "Muted."
    except Exception as e:
        return f"Couldn't mute — {e}"


def _unmute(plat: str) -> str:
    try:
        if plat == "windows":
            vol = _get_windows_volume_interface()
            vol.SetMute(0, None)
        elif plat == "darwin":
            subprocess.run(["osascript", "-e", "set volume without output muted"])
        else:
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "unmute"])
        return "Unmuted."
    except Exception as e:
        return f"Couldn't unmute — {e}"


def _media_key(plat: str, action: str) -> str:
    """Sends OS media key events. Requires `keyboard` lib on Windows/Linux."""
    try:
        if plat == "windows" or plat == "linux":
            import keyboard
            key_map = {"play_pause": "play/pause media", "next": "next track", "previous": "previous track"}
            keyboard.send(key_map[action])
        elif plat == "darwin":
            key_map = {"play_pause": "16", "next": "17", "previous": "18"}  # media key codes
            subprocess.run(["osascript", "-e",
                             f'tell application "System Events" to key code {key_map[action]}'])
        return "Done."
    except Exception as e:
        return f"Couldn't send media command — {e}"
