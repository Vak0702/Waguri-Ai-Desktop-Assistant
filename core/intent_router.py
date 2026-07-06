"""
intent_router.py — Lightweight first-pass intent classification.

Cheap keyword/regex matching handles obvious commands instantly (no LLM
round-trip needed for "what's my battery" or "open chrome"). Anything
ambiguous falls through to the LLM brain for general conversation or
more nuanced intent detection.
"""

from __future__ import annotations

import re
import difflib
from dataclasses import dataclass
from enum import Enum, auto

from skills.app_control import known_app_names


class Intent(Enum):
    SYSTEM_VITALS = auto()
    APP_CONTROL_OPEN = auto()
    APP_CONTROL_CLOSE = auto()
    SCREEN_ANALYSIS = auto()
    MEDIA_CONTROL = auto()
    FILE_SEARCH = auto()
    REMINDER = auto()
    SYSTEM_POWER = auto()      # shutdown / restart / sleep / lock — destructive, needs confirm
    END_CONVERSATION = auto()  # user signals they're done talking to Waguri (not a PC power action)
    GUI_CONTROL = auto()       # window UI actions: fullscreen, minimize, minimal mode, mute mic
    CHAT = auto()              # fallback: general LLM conversation


@dataclass
class RoutedIntent:
    intent: Intent
    payload: dict


_VITALS_PATTERNS = re.compile(
    r"\b(cpu|ram|memory|battery|disk|storage|network|system (vitals|stats|status))\b", re.I
)
_OPEN_PATTERN = re.compile(r"\bopen\s+(.+)", re.I)
_CLOSE_PATTERN = re.compile(r"\b(close|quit|kill)\s+(.+)", re.I)
_SCREEN_PATTERN = re.compile(
    r"\b(what'?s on my screen|screen|read this|analyze this|summarize this|what am i looking at)\b",
    re.I
)
_MEDIA_PATTERN = re.compile(
    r"\b(volume|mute|unmute|play|pause|next track|previous track|skip)\b", re.I
)
_FILE_SEARCH_PATTERN = re.compile(r"\b(find|search for|locate)\s+(.+?\s+)?file", re.I)
_REMINDER_PATTERN = re.compile(r"\b(remind me|set a reminder|note that|take a note)\b", re.I)
_POWER_PATTERN = re.compile(r"\b(shut ?down|restart|reboot|put (my )?(computer|pc) to sleep|lock (my )?(screen|computer|pc))\b", re.I)

# Phrases that end the current conversation session (return to wake-word
# standby) without being confused with "put my computer to sleep".
_END_CONVERSATION_PATTERN = re.compile(
    r"\b(stop listening|that'?s all|that'?ll be all|never\s?mind|"
    r"goodbye( waguri)?|bye waguri|thanks?,?\s*that'?s it|"
    r"you can stop( now)?|stand down|go back to sleep)\b",
    re.I
)

# Window/UI control phrases. Note: "mute your(self)?/mic" is deliberately
# distinct wording from the system-volume "mute" handled by MEDIA_CONTROL,
# and this whole block is checked *before* MEDIA_PATTERN in route() so
# "mute yourself" doesn't get caught by MEDIA_CONTROL's bare \bmute\b first.
_GUI_FULLSCREEN_ON_PATTERN = re.compile(r"\b(go |make (this|it) )?full ?screen\b", re.I)
_GUI_FULLSCREEN_OFF_PATTERN = re.compile(r"\b(exit|leave) full ?screen\b", re.I)
_GUI_MINIMIZE_PATTERN = re.compile(r"\bminimize( yourself| to tray)?\b", re.I)
_GUI_HIDE_CONTROLS_PATTERN = re.compile(
    r"\b(hide (the )?(controls|buttons)|minimal mode|clean view|"
    r"just show (the )?orb|orb only|hide (the )?ui)\b", re.I
)
_GUI_SHOW_CONTROLS_PATTERN = re.compile(
    r"\b(show (the )?(controls|buttons)|bring back (the )?controls|"
    r"exit minimal mode|show (the )?ui)\b", re.I
)
_GUI_MUTE_MIC_PATTERN = re.compile(r"\bmute (yourself|your ?self|your mic|the mic)\b", re.I)


def _clean_app_target(raw_target: str) -> str:
    """
    Strips trailing hallucination noise that small Whisper models commonly
    produce on silence/background noise — repeated digits, stray commas,
    trailing punctuation, with spaces between them
    (e.g. "chrome 3, 3, 3, 4, 3." -> "chrome").
    """
    cleaned = re.sub(r"[\d,\.\s]+$", "", raw_target).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _fuzzy_correct_app_name(target: str) -> str:
    """
    Safety net for near-miss transcriptions of known app names — e.g. STT
    hearing "sportify" instead of "spotify". Only corrects when there's a
    strong match (cutoff=0.72) against Waguri's known app vocabulary, so it
    won't silently mangle the name of some other app you say that isn't in
    the list — that just passes through unchanged.
    """
    candidates = known_app_names()
    matches = difflib.get_close_matches(target.lower(), candidates, n=1, cutoff=0.72)
    return matches[0] if matches else target


def route(text: str) -> RoutedIntent:
    """Classify user text into an Intent. Cheap, deterministic, instant."""
    t = text.strip()

    # GUI control checked early and before MEDIA_PATTERN specifically so
    # "mute yourself" doesn't get caught by the system-volume mute pattern.
    if _GUI_MUTE_MIC_PATTERN.search(t):
        return RoutedIntent(Intent.GUI_CONTROL, {"raw": t, "action": "mute_mic"})
    if _GUI_HIDE_CONTROLS_PATTERN.search(t):
        return RoutedIntent(Intent.GUI_CONTROL, {"raw": t, "action": "hide_controls"})
    if _GUI_SHOW_CONTROLS_PATTERN.search(t):
        return RoutedIntent(Intent.GUI_CONTROL, {"raw": t, "action": "show_controls"})
    if _GUI_MINIMIZE_PATTERN.search(t):
        return RoutedIntent(Intent.GUI_CONTROL, {"raw": t, "action": "minimize"})
    # Order matters: check "exit fullscreen" before the more general
    # "fullscreen" pattern, since the latter would otherwise also match
    # inside "exit full screen".
    if _GUI_FULLSCREEN_OFF_PATTERN.search(t):
        return RoutedIntent(Intent.GUI_CONTROL, {"raw": t, "action": "exit_fullscreen"})
    if _GUI_FULLSCREEN_ON_PATTERN.search(t):
        return RoutedIntent(Intent.GUI_CONTROL, {"raw": t, "action": "fullscreen_on"})

    if _END_CONVERSATION_PATTERN.search(t):
        return RoutedIntent(Intent.END_CONVERSATION, {"raw": t})

    if _POWER_PATTERN.search(t):
        return RoutedIntent(Intent.SYSTEM_POWER, {"raw": t})

    if _VITALS_PATTERNS.search(t):
        return RoutedIntent(Intent.SYSTEM_VITALS, {"raw": t})

    if _SCREEN_PATTERN.search(t):
        return RoutedIntent(Intent.SCREEN_ANALYSIS, {"raw": t, "question": t})

    if _MEDIA_PATTERN.search(t):
        return RoutedIntent(Intent.MEDIA_CONTROL, {"raw": t})

    if _REMINDER_PATTERN.search(t):
        return RoutedIntent(Intent.REMINDER, {"raw": t})

    m = _FILE_SEARCH_PATTERN.search(t)
    if m:
        return RoutedIntent(Intent.FILE_SEARCH, {"raw": t, "query": t})

    m = _CLOSE_PATTERN.search(t)
    if m:
        target = _clean_app_target(m.group(2).strip())
        target = _fuzzy_correct_app_name(target)
        if target:
            return RoutedIntent(Intent.APP_CONTROL_CLOSE, {"raw": t, "target": target})

    m = _OPEN_PATTERN.search(t)
    if m:
        # avoid false-positive on phrases like "open to the idea" — require a
        # short, app-name-like target (no more than ~4 words) after cleaning
        # out any trailing STT hallucination noise (digits/punctuation)
        target = _clean_app_target(m.group(1).strip())
        target = _fuzzy_correct_app_name(target)
        if target and len(target.split()) <= 4:
            return RoutedIntent(Intent.APP_CONTROL_OPEN, {"raw": t, "target": target})

    return RoutedIntent(Intent.CHAT, {"raw": t})