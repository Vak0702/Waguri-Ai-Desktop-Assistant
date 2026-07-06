"""
reminders_notes.py — Simple local reminders and notes, stored as JSON.
Reminders fire OS-native notifications via `plyer` when their time arrives
(checked by a background scheduler started from main.py).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta

import config

_DEFAULT = {"notes": [], "reminders": []}


def _load() -> dict:
    if not os.path.exists(config.NOTES_PATH):
        return dict(_DEFAULT)
    with open(config.NOTES_PATH, "r") as f:
        return json.load(f)


def _save(data: dict):
    os.makedirs(os.path.dirname(config.NOTES_PATH), exist_ok=True)
    with open(config.NOTES_PATH, "w") as f:
        json.dump(data, f, indent=2)


def handle(raw_text: str) -> str:
    t = raw_text.lower()

    if "remind me" in t or "set a reminder" in t:
        return _add_reminder(raw_text)
    else:
        return _add_note(raw_text)


def _add_note(raw_text: str) -> str:
    m = re.search(r"(?:note that|take a note)[:,]?\s*(.+)", raw_text, re.I)
    content = m.group(1).strip() if m else raw_text
    data = _load()
    data["notes"].append({"text": content, "created": datetime.now().isoformat()})
    _save(data)
    return "Noted."


def _add_reminder(raw_text: str) -> str:
    # very simple time parsing: "in 10 minutes", "in an hour", "in 2 hours"
    m = re.search(r"in\s+(\d+|an?)\s*(minute|minutes|hour|hours)", raw_text, re.I)
    m_content = re.search(r"remind me (?:to\s+)?(.+?)(?:\s+in\s+\d+.*)?$", raw_text, re.I)
    content = m_content.group(1).strip() if m_content else "something"

    delta = timedelta(minutes=15)  # default fallback
    if m:
        amount_raw, unit = m.group(1), m.group(2)
        amount = 1 if amount_raw in ("a", "an") else int(amount_raw)
        delta = timedelta(hours=amount) if "hour" in unit else timedelta(minutes=amount)

    fire_at = datetime.now() + delta
    data = _load()
    data["reminders"].append({
        "text": content,
        "fire_at": fire_at.isoformat(),
        "fired": False,
    })
    _save(data)

    minutes = int(delta.total_seconds() // 60)
    return f"Got it — I'll remind you to {content} in {minutes} minutes."


def check_due_reminders() -> list[str]:
    """Called periodically (e.g. every 30s) by main.py's scheduler.
    Returns text of any reminders that just became due, and marks them fired."""
    data = _load()
    now = datetime.now()
    due = []
    changed = False

    for reminder in data["reminders"]:
        if reminder["fired"]:
            continue
        fire_at = datetime.fromisoformat(reminder["fire_at"])
        if now >= fire_at:
            due.append(reminder["text"])
            reminder["fired"] = True
            changed = True

    if changed:
        _save(data)

    return due
