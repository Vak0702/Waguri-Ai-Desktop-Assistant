"""
system_toggles.py — Wi-Fi, Bluetooth, and Do Not Disturb control.

Wi-Fi/Bluetooth use Windows' own Radios API (via winsdk) — the same
permission model as the Settings app's toggle switches, so no
administrator privileges are needed (unlike `netsh`, which requires admin
rights to change network interface state). The first use may prompt via
Windows Settings > Privacy & security > Radios if "let apps control
wireless devices" is disabled there.

Do Not Disturb / Focus Assist has no reliable, documented API for
third-party toggling — Microsoft has never exposed one, and the internal
state is stored as an undocumented binary blob that can vary across
Windows builds. Rather than risk corrupting your actual notification
settings with a registry hack, Waguri mutes its own spoken
reminders/notifications when you ask for DND, and opens the real Focus
Assist settings page so flipping the actual Windows toggle is one click
away instead of zero — an honest middle ground rather than a fragile
workaround presented as more reliable than it is.
"""

from __future__ import annotations

import asyncio
import platform
import subprocess


def _platform_key() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "darwin"
    return "linux"


async def _set_radio(kind_name: str, turn_on: bool) -> tuple[bool, str]:
    """Returns (success, message)."""
    import winsdk.windows.devices.radios as radios

    kind_map = {
        "wifi": radios.RadioKind.WI_FI,
        "bluetooth": radios.RadioKind.BLUETOOTH,
    }
    kind = kind_map.get(kind_name)
    if kind is None:
        return False, f"Unknown radio type: {kind_name}"

    all_radios = await radios.Radio.get_radios_async()
    target_radio = None
    for r in all_radios:
        if r.kind == kind:
            target_radio = r
            break

    if target_radio is None:
        return False, f"I couldn't find a {kind_name} radio on this device."

    state = radios.RadioState.ON if turn_on else radios.RadioState.OFF
    result = await target_radio.set_state_async(state)

    if result == radios.RadioAccessStatus.ALLOWED:
        return True, ""
    elif result == radios.RadioAccessStatus.DENIED_BY_USER:
        return False, ("Windows is blocking apps from controlling wireless devices — "
                        "check Settings, Privacy and security, Radios.")
    elif result == radios.RadioAccessStatus.DENIED_BY_SYSTEM:
        return False, "A system policy is blocking this — likely managed by an admin or organization."
    else:
        return False, "Something prevented that change."


def set_wifi(turn_on: bool) -> str:
    if _platform_key() != "windows":
        return "Wi-Fi control is currently only supported on Windows."
    try:
        success, msg = asyncio.run(_set_radio("wifi", turn_on))
    except ImportError:
        return "Wi-Fi control needs the 'winsdk' package — pip install winsdk."
    except Exception as e:
        return f"I couldn't change Wi-Fi — {e}"

    if success:
        return f"Wi-Fi turned {'on' if turn_on else 'off'}."

    # Fallback for turning off specifically: some Wi-Fi adapter drivers
    # don't implement the "Radio Management" interface the Radios API
    # needs (a known real-world gap — Bluetooth almost always supports it,
    # Wi-Fi doesn't always). Disconnecting isn't the same as disabling the
    # radio, but it stops connectivity without needing admin rights.
    if not turn_on:
        if _try_netsh_wifi_disconnect():
            return "I couldn't fully disable the Wi-Fi radio, but I disconnected you from your network."

    return msg or "I couldn't change Wi-Fi."


def _try_netsh_wifi_disconnect() -> bool:
    try:
        result = subprocess.run(
            ["netsh", "wlan", "disconnect"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def set_bluetooth(turn_on: bool) -> str:
    if _platform_key() != "windows":
        return "Bluetooth control is currently only supported on Windows."
    try:
        success, msg = asyncio.run(_set_radio("bluetooth", turn_on))
    except ImportError:
        return "Bluetooth control needs the 'winsdk' package — pip install winsdk."
    except Exception as e:
        return f"I couldn't change Bluetooth — {e}"

    if success:
        return f"Bluetooth turned {'on' if turn_on else 'off'}."
    return msg or "I couldn't change Bluetooth."


# ---------- Do Not Disturb ----------
# Windows doesn't expose a documented API for the full Focus Assist tri-state
# (Off / Priority only / Alarms only), but there IS a legitimate, low-risk,
# well-documented HKCU registry value that reliably suppresses Windows'
# toast notifications system-wide — no admin rights needed, and it's a
# simple DWORD flip rather than the fragile, undocumented binary blob Focus
# Assist's own internal state uses. This achieves genuine "notifications
# don't interrupt me" behavior, even if it's blunter than Focus Assist's
# priority-list nuance.

_dnd_enabled = False


def is_dnd_enabled() -> bool:
    """Checked by main.py before speaking reminders/notifications aloud."""
    return _dnd_enabled


def _set_toast_notifications(enabled: bool) -> bool:
    """Returns True if the registry value was successfully set."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, "NOC_GLOBAL_SETTING_TOASTS_ENABLED", 0,
                           winreg.REG_DWORD, 1 if enabled else 0)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def set_do_not_disturb(turn_on: bool) -> str:
    global _dnd_enabled
    _dnd_enabled = turn_on

    registry_ok = False
    if _platform_key() == "windows":
        registry_ok = _set_toast_notifications(enabled=not turn_on)
        try:
            # Secondary nicety — opens the Focus Assist settings page too,
            # in case you want the fuller Priority/Alarms-only control.
            # os.startfile is the standard, reliable way to launch a
            # ms-settings: URI on Windows (same ShellExecute mechanism as
            # double-clicking or Win+R) — subprocess.Popen(["explorer.exe",
            # ...]) can be inconsistent with URI-scheme arguments.
            import os
            os.startfile("ms-settings:quiethours")
        except Exception:
            pass

    if turn_on:
        if registry_ok:
            return "Do not disturb is on — Windows notifications are silenced."
        return ("I'll hold off on my own spoken reminders for now, but I couldn't "
                "silence Windows' own notifications directly — you can do that "
                "manually in Settings, System, Notifications.")
    else:
        if registry_ok:
            return "Do not disturb is off — notifications are back on."
        return "Reminders are back on, though I couldn't confirm Windows' notification setting changed."