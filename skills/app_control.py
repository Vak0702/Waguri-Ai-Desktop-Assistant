"""
app_control.py — Open and close desktop applications.

Windows-first implementation. For common consumer apps (Chrome, Spotify,
VS Code) we check their actual default install locations directly, since
relying on `start <name>` alone is unreliable — many apps aren't
registered on PATH or in the Windows "App Paths" registry the way system
tools like notepad/calc are. Falls back to `start` for anything else, and
includes macOS/Linux branches too.
"""

from __future__ import annotations

import os
import platform
import subprocess

# Map common spoken app names -> platform-specific launch commands.
# Extend this as you find gaps for your own installed apps.
APP_ALIASES = {
    "windows": {
        "chrome": "chrome",
        "google chrome": "chrome",
        "firefox": "firefox",
        "notepad": "notepad",
        "calculator": "calc",
        "explorer": "explorer",
        "file explorer": "explorer",
        "vscode": "code",
        "vs code": "code",
        "visual studio code": "code",
        "spotify": "spotify",
        "word": "winword",
        "excel": "excel",
        "powerpoint": "powerpnt",
        "settings": "start ms-settings:",
    },
    "darwin": {  # macOS
        "chrome": "Google Chrome",
        "google chrome": "Google Chrome",
        "safari": "Safari",
        "notes": "Notes",
        "calculator": "Calculator",
        "finder": "Finder",
        "vscode": "Visual Studio Code",
        "vs code": "Visual Studio Code",
        "spotify": "Spotify",
    },
    "linux": {
        "chrome": "google-chrome",
        "firefox": "firefox",
        "files": "nautilus",
        "file manager": "nautilus",
        "vscode": "code",
        "vs code": "code",
        "terminal": "gnome-terminal",
        "spotify": "spotify",
    },
}

# Known default install locations for common consumer apps on Windows,
# checked in order. Environment variables are expanded at lookup time.
# Add more entries here if an app you use isn't opening reliably.
WINDOWS_KNOWN_PATHS = {
    "chrome": [
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    ],
    "spotify": [
        r"%AppData%\Spotify\Spotify.exe",
        r"%ProgramFiles%\Spotify\Spotify.exe",
        r"%ProgramFiles(x86)%\Spotify\Spotify.exe",
    ],
    "code": [
        r"%LocalAppData%\Programs\Microsoft VS Code\Code.exe",
        r"%ProgramFiles%\Microsoft VS Code\Code.exe",
    ],
    "firefox": [
        r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
        r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
    ],
}


def _platform_key() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "darwin"
    return "linux"


def _resolve(target: str) -> str:
    plat = _platform_key()
    aliases = APP_ALIASES.get(plat, {})
    key = target.strip().lower()
    return aliases.get(key, target.strip())


def known_app_names() -> list[str]:
    """All recognized app name aliases for the current platform. Used
    elsewhere (STT vocabulary biasing, fuzzy correction of near-miss
    transcriptions like 'sportify' -> 'spotify') so the app-name list only
    has to be maintained in one place."""
    plat = _platform_key()
    names = set(APP_ALIASES.get(plat, {}).keys())
    if plat == "windows":
        names.update(WINDOWS_KNOWN_PATHS.keys())
        names.update(WINDOWS_PROCESS_NAMES.keys())
    return sorted(names)


def _try_known_windows_path(resolved: str) -> str | None:
    """Returns the first existing known install path for this app, if any."""
    candidates = WINDOWS_KNOWN_PATHS.get(resolved.lower(), [])
    for template in candidates:
        path = os.path.expandvars(template)
        if os.path.exists(path):
            return path
    return None


def open_app(target: str) -> str:
    plat = _platform_key()
    resolved = _resolve(target)

    try:
        if plat == "windows":
            # 1. Prefer a known, verified install path if we have one —
            #    far more reliable than hoping `start` can find the app.
            known_path = _try_known_windows_path(resolved)
            if known_path:
                subprocess.Popen([known_path])
                return f"Opening {target}."

            # 2. Fall back to letting Windows resolve it via PATH / the
            #    App Paths registry. Quoting matters here: `start` treats
            #    the first quoted argument as a window title, so we pass
            #    an empty title explicitly, then the actual target quoted.
            subprocess.Popen(f'start "" "{resolved}"', shell=True)
            return f"Opening {target}."

        elif plat == "darwin":
            subprocess.Popen(["open", "-a", resolved])
        else:
            subprocess.Popen([resolved], shell=False)
        return f"Opening {target}."
    except Exception as e:
        return f"I couldn't open {target} — {e}"


# Actual Windows process image names for common apps — "close spotify"
# needs to taskkill "Spotify.exe" specifically, not a guessed "spotify.exe".
# Extend this if closing an app you use doesn't work.
WINDOWS_PROCESS_NAMES = {
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "notepad": "notepad.exe",
    "spotify": "Spotify.exe",
    "code": "Code.exe",
    "vscode": "Code.exe",
    "vs code": "Code.exe",
    "visual studio code": "Code.exe",
    "word": "WINWORD.EXE",
    "excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE",
    "calculator": "CalculatorApp.exe",  # Windows 11; older Windows uses "Calculator.exe"
}


def close_app(target: str) -> str:
    plat = _platform_key()
    resolved = _resolve(target)

    try:
        if plat == "windows":
            # Prefer a known exact process image name; fall back to a guess
            image = WINDOWS_PROCESS_NAMES.get(resolved.lower()) \
                or (resolved if resolved.lower().endswith(".exe") else f"{resolved}.exe")

            result = subprocess.run(["taskkill", "/IM", image, "/F"],
                                     capture_output=True, text=True)
            if result.returncode != 0:
                # taskkill returns non-zero if the process wasn't found/running
                return f"{target} doesn't seem to be running."
            return f"Closing {target}."

        elif plat == "darwin":
            subprocess.run(["pkill", "-f", resolved])
        else:
            subprocess.run(["pkill", "-f", resolved])
        return f"Closing {target}."
    except Exception as e:
        return f"I couldn't close {target} — {e}"