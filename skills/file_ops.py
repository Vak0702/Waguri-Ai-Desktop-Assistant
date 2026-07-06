"""
file_ops.py — Basic file search and folder opening.

Searches from the user's home directory by default (customize SEARCH_ROOTS
below for your own common locations, e.g. Documents, Desktop, Downloads).
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
from pathlib import Path

HOME = Path.home()
SEARCH_ROOTS = [HOME / "Desktop", HOME / "Documents", HOME / "Downloads"]
MAX_RESULTS = 5


def search(query: str) -> str:
    # Extract the likely filename fragment from natural language
    m = re.search(r"(?:find|search for|locate)\s+(?:the\s+)?(?:file\s+)?(?:called\s+|named\s+)?(.+?)(?:\s+file)?$",
                   query, re.I)
    term = (m.group(1) if m else query).strip().lower()
    if not term:
        return "What file should I look for?"

    matches = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for fname in filenames:
                if term in fname.lower():
                    matches.append(Path(dirpath) / fname)
            if len(matches) >= MAX_RESULTS:
                break
        if len(matches) >= MAX_RESULTS:
            break

    if not matches:
        return f"I couldn't find anything matching '{term}' in your Desktop, Documents, or Downloads."

    if len(matches) == 1:
        _reveal(matches[0])
        return f"Found it — {matches[0].name}, opening its folder now."

    names = ", ".join(p.name for p in matches[:MAX_RESULTS])
    return f"Found {len(matches)} matches: {names}."


def _reveal(path: Path):
    """Opens the containing folder and highlights the file, OS-appropriate."""
    system = platform.system().lower()
    try:
        if system == "windows":
            subprocess.run(["explorer", "/select,", str(path)])
        elif system == "darwin":
            subprocess.run(["open", "-R", str(path)])
        else:
            subprocess.run(["xdg-open", str(path.parent)])
    except Exception:
        pass
