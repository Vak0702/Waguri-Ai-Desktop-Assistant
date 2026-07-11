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
    TAKE_SCREENSHOT = auto()   # save a screenshot to disk (distinct from analyzing screen content)
    WEATHER = auto()
    MEDIA_CONTROL = auto()
    FILE_SEARCH = auto()
    REMINDER = auto()
    SYSTEM_POWER = auto()      # shutdown / restart / sleep / lock — destructive, needs confirm
    END_CONVERSATION = auto()  # user signals they're done talking to Waguri (not a PC power action)
    GUI_CONTROL = auto()       # Waguri's own window UI: fullscreen, minimize, minimal mode, mute
    WINDOW_CONTROL = auto()    # OTHER apps' windows: snap left/right, maximize/minimize, list
    REFRESH_APPS = auto()      # rescan Start Menu for newly-installed apps mid-session
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
_REFRESH_APPS_PATTERN = re.compile(
    r"\b(refresh|rescan|update) (my |the )?(app|application)s?( list)?\b", re.I
)
# Checked before _SCREEN_PATTERN since "screenshot" would otherwise also
# get caught as a screen-analysis request. Whisper frequently transcribes
# "screenshot" as two separate words ("screen shot"), so this matches both
# spellings, standalone or in a fuller phrase like "take a screenshot".
_SCREENSHOT_PATTERN = re.compile(r"\bscreen\s?shot\b|\bcapture (the |my )?screen\b", re.I)
_SCREEN_PATTERN = re.compile(
    r"\b(what'?s on my screen|screen|read this|analyze this|summarize this|what am i looking at)\b",
    re.I
)
_WEATHER_PATTERN = re.compile(r"\b(weather|forecast)\b", re.I)
_WEATHER_CITY_PATTERN = re.compile(r"\b(?:weather|forecast)(?: report)?\s+(?:in|for|at)\s+(.+)", re.I)
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

# Controls for OTHER applications' windows (not Waguri's own orb window).
# The literal word "window" is the required disambiguator — "minimize" alone
# means Waguri's own window (GUI_CONTROL above); "minimize this window"
# means whatever app is currently focused. These checks run *before*
# GUI_CONTROL's bare minimize/fullscreen patterns for that reason.
_WINDOW_SNAP_LEFT_PATTERN = re.compile(r"\b(snap|move) (this |the |my )?window (to the )?left\b", re.I)
_WINDOW_SNAP_RIGHT_PATTERN = re.compile(r"\b(snap|move) (this |the |my )?window (to the )?right\b", re.I)
_WINDOW_MAXIMIZE_PATTERN = re.compile(r"\bmaximize (this |the |my )?(current )?window\b", re.I)
_WINDOW_MINIMIZE_PATTERN = re.compile(r"\bminimize (this |the |my )?(current )?window\b", re.I)
_WINDOW_SHOW_ALL_PATTERN = re.compile(
    r"\b(show( me)? (all )?(my )?open windows|show task view|task view)\b", re.I
)
_WINDOW_LIST_PATTERN = re.compile(
    r"\b(list( my)? open windows|what windows are open|what('s| is) open)\b", re.I
)

_ORDINAL_WORDS = {
    "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4, "fifth": 5, "5th": 5, "sixth": 6, "6th": 6,
    "seventh": 7, "7th": 7, "eighth": 8, "8th": 8, "ninth": 9, "9th": 9,
    "tenth": 10, "10th": 10,
}
# Ordinal-based window switching ("switch to the second window", "go to
# window 3") — checked *before* the generic name-based _WINDOW_SWITCH_PATTERN
# below, since that broader pattern would otherwise treat "second" itself
# as a literal window name to search for and fail to find it.
_WINDOW_ORDINAL_WORD_PATTERN = re.compile(
    r"\b(?:go to|switch to|navigate to|focus(?: on)?)\s+(?:the\s+)?"
    r"(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th)\s+window\b",
    re.I
)
_WINDOW_ORDINAL_NUM_PATTERN = re.compile(
    r"\b(?:go to|switch to|navigate to|focus(?: on)?)\s+(?:the\s+)?window\s+(?:number\s+)?(\d+)\b",
    re.I
)
# "switch to X" / "navigate to X" / "go to X window" — brings a specific
# window to the foreground by (fuzzy) title match.
_WINDOW_SWITCH_PATTERN = re.compile(
    r"\b(switch to|navigate to|go to|bring up|focus)\s+(?:the\s+)?(.+?)(?:\s+window)?$", re.I
)
# Checked before the generic app-closing _CLOSE_PATTERN so "close this
# window" doesn't get treated as "close an app named 'this window'".
_WINDOW_CLOSE_CURRENT_PATTERN = re.compile(r"\bclose (this|the current) window\b", re.I)

_DESKTOP_NEW_PATTERN = re.compile(r"\b(open|create) (a )?new desktop\b", re.I)
_DESKTOP_NEXT_PATTERN = re.compile(r"\b(switch to|go to) (the )?next desktop\b", re.I)
_DESKTOP_PREV_PATTERN = re.compile(r"\b(switch to|go to) (the )?(previous|last) desktop\b", re.I)
_DESKTOP_CLOSE_PATTERN = re.compile(r"\bclose (this|the current) desktop\b", re.I)


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
    # Window-management for OTHER apps, checked before GUI_CONTROL's own
    # minimize pattern — "minimize this window" (some other app) needs to
    # win over the more general "minimize" (Waguri's own window) below.
    if _WINDOW_SNAP_LEFT_PATTERN.search(t):
        return RoutedIntent(Intent.WINDOW_CONTROL, {"raw": t, "action": "snap_left"})
    if _WINDOW_SNAP_RIGHT_PATTERN.search(t):
        return RoutedIntent(Intent.WINDOW_CONTROL, {"raw": t, "action": "snap_right"})
    if _WINDOW_MAXIMIZE_PATTERN.search(t):
        return RoutedIntent(Intent.WINDOW_CONTROL, {"raw": t, "action": "maximize"})
    if _WINDOW_MINIMIZE_PATTERN.search(t):
        return RoutedIntent(Intent.WINDOW_CONTROL, {"raw": t, "action": "minimize"})
    if _WINDOW_SHOW_ALL_PATTERN.search(t):
        return RoutedIntent(Intent.WINDOW_CONTROL, {"raw": t, "action": "show_all"})
    if _WINDOW_LIST_PATTERN.search(t):
        return RoutedIntent(Intent.WINDOW_CONTROL, {"raw": t, "action": "list_windows"})
    if _WINDOW_CLOSE_CURRENT_PATTERN.search(t):
        return RoutedIntent(Intent.WINDOW_CONTROL, {"raw": t, "action": "close_window"})

    # Desktop-specific checks must come before the generic window-switch
    # pattern below, since "switch to the next desktop" would otherwise be
    # swallowed by "switch to X" and treated as a window name to find.
    if _DESKTOP_NEW_PATTERN.search(t):
        return RoutedIntent(Intent.WINDOW_CONTROL, {"raw": t, "action": "new_desktop"})
    if _DESKTOP_NEXT_PATTERN.search(t):
        return RoutedIntent(Intent.WINDOW_CONTROL, {"raw": t, "action": "next_desktop"})
    if _DESKTOP_PREV_PATTERN.search(t):
        return RoutedIntent(Intent.WINDOW_CONTROL, {"raw": t, "action": "prev_desktop"})
    if _DESKTOP_CLOSE_PATTERN.search(t):
        return RoutedIntent(Intent.WINDOW_CONTROL, {"raw": t, "action": "close_desktop"})

    ordinal_word_match = _WINDOW_ORDINAL_WORD_PATTERN.search(t)
    if ordinal_word_match:
        ordinal = _ORDINAL_WORDS.get(ordinal_word_match.group(1).lower())
        if ordinal:
            return RoutedIntent(Intent.WINDOW_CONTROL,
                                 {"raw": t, "action": "switch_to_ordinal", "ordinal": ordinal})

    ordinal_num_match = _WINDOW_ORDINAL_NUM_PATTERN.search(t)
    if ordinal_num_match:
        return RoutedIntent(Intent.WINDOW_CONTROL,
                             {"raw": t, "action": "switch_to_ordinal", "ordinal": int(ordinal_num_match.group(1))})

    switch_match = _WINDOW_SWITCH_PATTERN.search(t)
    if switch_match:
        target = switch_match.group(2).strip()
        if target:
            return RoutedIntent(Intent.WINDOW_CONTROL, {"raw": t, "action": "switch_to", "target": target})

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

    # Checked before SCREEN_PATTERN so "take a screenshot" doesn't get
    # routed to screen analysis instead.
    if _SCREENSHOT_PATTERN.search(t):
        return RoutedIntent(Intent.TAKE_SCREENSHOT, {"raw": t})

    if _SCREEN_PATTERN.search(t):
        return RoutedIntent(Intent.SCREEN_ANALYSIS, {"raw": t, "question": t})

    if _WEATHER_PATTERN.search(t):
        city_match = _WEATHER_CITY_PATTERN.search(t)
        city = city_match.group(1).strip() if city_match else None
        return RoutedIntent(Intent.WEATHER, {"raw": t, "city": city})

    if _MEDIA_PATTERN.search(t):
        return RoutedIntent(Intent.MEDIA_CONTROL, {"raw": t})

    if _REMINDER_PATTERN.search(t):
        return RoutedIntent(Intent.REMINDER, {"raw": t})

    m = _FILE_SEARCH_PATTERN.search(t)
    if m:
        return RoutedIntent(Intent.FILE_SEARCH, {"raw": t, "query": t})

    if _REFRESH_APPS_PATTERN.search(t):
        return RoutedIntent(Intent.REFRESH_APPS, {"raw": t})

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