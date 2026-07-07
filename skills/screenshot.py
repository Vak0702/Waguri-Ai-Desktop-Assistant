"""
screenshot.py — Saves a screenshot to disk. Distinct from screen_analysis.py,
which sends a screenshot to a vision LLM to describe/answer questions about
it. This skill just captures and saves the file — no LLM call, no cost,
works even with no API keys configured at all.
"""

from __future__ import annotations

import platform
import subprocess
from datetime import datetime
from pathlib import Path

import mss
import mss.tools

SCREENSHOT_DIR = Path.home() / "Pictures" / "Waguri Screenshots"


def take_screenshot() -> str:
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filepath = SCREENSHOT_DIR / f"waguri_{timestamp}.png"

        with mss.mss() as sct:
            monitor = sct.monitors[1]  # primary monitor
            raw = sct.grab(monitor)
            mss.tools.to_png(raw.rgb, raw.size, output=str(filepath))

        _reveal(filepath)
        return f"Screenshot saved as {filepath.name} in your Pictures folder."
    except Exception as e:
        return f"I couldn't take the screenshot — {e}"


def _reveal(filepath: Path):
    """Opens the containing folder and highlights the file, OS-appropriate.
    Best-effort — if this fails, the screenshot is still saved successfully."""
    system = platform.system().lower()
    try:
        if system == "windows":
            subprocess.run(["explorer", "/select,", str(filepath)])
        elif system == "darwin":
            subprocess.run(["open", "-R", str(filepath)])
        else:
            subprocess.run(["xdg-open", str(filepath.parent)])
    except Exception:
        pass