"""
app_discovery.py — Auto-discovers installed applications so "open X" works
for anything you have installed, not just a hand-maintained alias list.

Uses PowerShell's `Get-StartApps` cmdlet, which enumerates *everything* in
your Start Menu index — both traditional desktop apps (.exe-based) and
Microsoft Store / UWP apps (like Netflix, the modern Calculator, etc.) that
don't have classic .lnk shortcut files at all. This is the same index
Windows itself uses to power the Start Menu, so it's more complete and
more reliable than manually scanning shortcut files.

Each entry gives an AppID, which is launched via the universal
`explorer.exe shell:AppsFolder\\<AppID>` mechanism — the same protocol
Windows uses internally when you click a Start Menu tile, so it works
identically for both desktop and Store apps without needing to tell them
apart.

Scanned once per process and cached. Call refresh() to force a rescan
(e.g. right after installing new software mid-session).
"""

from __future__ import annotations

import json
import platform
import subprocess

_DISCOVERED_APPS: dict[str, str] = {}  # normalized name -> AppID
_SCANNED = False


def _platform_key() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "darwin"
    return "linux"


def _scan() -> dict[str, str]:
    if _platform_key() != "windows":
        return {}

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        data = json.loads(result.stdout)
    except Exception:
        return {}

    # PowerShell's ConvertTo-Json returns a single object (not a list) when
    # there's only one result — normalize to always work with a list.
    if isinstance(data, dict):
        data = [data]

    discovered: dict[str, str] = {}
    for entry in data:
        name = str(entry.get("Name", "")).strip()
        app_id = str(entry.get("AppID", "")).strip()
        if name and app_id:
            discovered[name.lower()] = app_id
    return discovered


def get_installed_apps() -> dict[str, str]:
    """Returns the cached name -> AppID index, scanning once on first call."""
    global _DISCOVERED_APPS, _SCANNED
    if not _SCANNED:
        _DISCOVERED_APPS = _scan()
        _SCANNED = True
    return _DISCOVERED_APPS


def refresh() -> int:
    """Forces a rescan — e.g. after installing new software mid-session.
    Returns the number of apps found."""
    global _DISCOVERED_APPS, _SCANNED
    _DISCOVERED_APPS = _scan()
    _SCANNED = True
    return len(_DISCOVERED_APPS)


def find_app_id(name: str) -> str | None:
    """Looks up a discovered app's AppID by exact, substring, or fuzzy name
    match, in that order of preference."""
    apps = get_installed_apps()
    if not apps:
        return None
    name_lower = name.strip().lower()

    if name_lower in apps:
        return apps[name_lower]

    for app_name, app_id in apps.items():
        if name_lower in app_name or app_name in name_lower:
            return app_id

    import difflib
    matches = difflib.get_close_matches(name_lower, apps.keys(), n=1, cutoff=0.6)
    if matches:
        return apps[matches[0]]

    return None


def launch(app_id: str) -> None:
    """Launches an app via its AppID using the same shell:AppsFolder
    mechanism Windows itself uses for Start Menu tiles — works for both
    traditional desktop apps and Microsoft Store/UWP apps identically."""
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"])