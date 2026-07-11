"""
window_control.py — Basic window management for OTHER applications (not
Waguri's own orb window, which is handled separately by gui/main_window.py
and main.py's GUI_CONTROL dispatch).

Uses Windows' own native snap shortcuts (Win+Left/Right/Up/Down) via the
`keyboard` package rather than reimplementing window geometry manually —
this respects whatever snap-assist/snap-layout behavior is already
configured on the user's system, instead of fighting it.

Also supports ordinal window switching ("switch to the second window",
"go to window 3") — a numbered list is cached after any listing action
(_list_open_windows / _show_all_windows) so the numbers stay consistent
between when you hear/see the list and when you refer back to it by
position, rather than needing to know each window's exact title.

Windows-only for now. macOS/Linux window management varies too much by
window manager to have one universal shortcut, so those platforms get a
clear "not supported yet" message rather than a broken attempt.
"""

from __future__ import annotations

import platform
import time

# Cached (hwnd, title) list from the last time windows were enumerated —
# powers ordinal references like "switch to the second window" so the
# numbering stays stable rather than re-querying Z-order fresh each time
# (which can reorder if focus changed in between).
_LAST_WINDOW_LIST: list[tuple[int, str]] = []

_IGNORED_TITLES = {"Program Manager", "Windows Input Experience"}


def _platform_key() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "darwin"
    return "linux"


def handle(payload: dict) -> str:
    action = payload.get("action")
    if action == "snap_left":
        return _snap("left")
    elif action == "snap_right":
        return _snap("right")
    elif action == "maximize":
        return _snap("maximize")
    elif action == "minimize":
        return _snap("minimize")
    elif action == "show_all":
        return _show_all_windows()
    elif action == "list_windows":
        return _list_open_windows()
    elif action == "switch_to":
        return _switch_to_window(payload.get("target", ""))
    elif action == "switch_to_ordinal":
        return _switch_to_ordinal(payload.get("ordinal"))
    elif action == "close_window":
        return _close_current_window()
    elif action == "new_desktop":
        return _new_virtual_desktop()
    elif action == "next_desktop":
        return _switch_desktop("next")
    elif action == "prev_desktop":
        return _switch_desktop("previous")
    elif action == "close_desktop":
        return _close_virtual_desktop()
    return "I didn't understand that window command."


def _snap(direction: str) -> str:
    if _platform_key() != "windows":
        return "Window snapping is currently only supported on Windows."

    try:
        import keyboard
    except ImportError:
        return "Window snapping needs the 'keyboard' package — pip install keyboard."

    key_map = {
        "left": "windows+left",
        "right": "windows+right",
        "maximize": "windows+up",
        "minimize": "windows+down",
    }
    combo = key_map.get(direction)

    try:
        keyboard.send(combo)
        if direction in ("left", "right"):
            return f"Snapped the window {direction}."
        return f"Window {direction}d."
    except Exception as e:
        return f"I couldn't do that — {e}"


def _enumerate_windows() -> list[tuple[int, str]]:
    """Returns (hwnd, title) for every visible top-level window with a
    non-empty title, minus a small filter list of background/system
    entries with no meaningful title of their own."""
    import win32gui

    candidates = []

    def _enum(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title.strip() and title not in _IGNORED_TITLES:
                candidates.append((hwnd, title))

    win32gui.EnumWindows(_enum, None)
    return candidates


def _show_all_windows() -> str:
    """Opens Windows' Task View — visually shows all open windows/apps.
    Also caches the current window order so a follow-up like 'switch to
    the second window' can reference what's shown."""
    global _LAST_WINDOW_LIST
    if _platform_key() != "windows":
        return "Showing all windows is currently only supported on Windows."
    try:
        import keyboard
        try:
            _LAST_WINDOW_LIST = _enumerate_windows()
        except Exception:
            pass  # Task View itself still works even if caching fails
        keyboard.send("windows+tab")
        return "Here's Task View. You can also say 'switch to the second window' and so on."
    except Exception as e:
        return f"I couldn't open Task View — {e}"


def _list_open_windows() -> str:
    """Enumerates visible top-level windows and speaks back a numbered
    list — distinct from _show_all_windows, which is the visual Task View
    switcher rather than a spoken list. Caches the order for ordinal
    follow-ups like 'switch to the third window'."""
    global _LAST_WINDOW_LIST
    if _platform_key() != "windows":
        return "Listing open windows is currently only supported on Windows."

    try:
        import win32gui  # noqa: F401 — import check before calling _enumerate_windows
    except ImportError:
        return "Listing windows needs pywin32 — pip install pywin32."

    try:
        candidates = _enumerate_windows()
    except Exception as e:
        return f"I couldn't list open windows — {e}"

    _LAST_WINDOW_LIST = candidates

    if not candidates:
        return "I couldn't find any open windows."

    max_list = 8
    shown = candidates[:max_list]
    more = f", and {len(candidates) - max_list} more" if len(candidates) > max_list else ""
    numbered = "; ".join(f"{i + 1}. {title}" for i, (_, title) in enumerate(shown))
    return f"Your open windows: {numbered}{more}. You can say 'switch to the second window' and so on."


def _find_window_by_name(target: str):
    """Returns (hwnd, title) for the best visible-window match for `target`
    — tries a direct substring match first, then falls back to fuzzy
    matching against all window titles. None if nothing matches at all."""
    candidates = _enumerate_windows()

    target_lower = target.lower()
    for hwnd, title in candidates:
        if target_lower in title.lower():
            return hwnd, title

    import difflib
    titles = [t for _, t in candidates]
    matches = difflib.get_close_matches(target, titles, n=1, cutoff=0.5)
    if matches:
        for hwnd, title in candidates:
            if title == matches[0]:
                return hwnd, title
    return None


def _force_foreground(hwnd) -> bool:
    """Tries several increasingly-aggressive techniques to bring `hwnd` to
    the foreground, since Windows' foreground-lock restriction can block a
    plain SetForegroundWindow call from a background process. Returns True
    if any technique reports success."""
    import win32gui
    import win32con
    import win32process
    import win32api

    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    # Technique 1: plain call — works when there's no foreground lock in effect.
    try:
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:
        pass

    # Technique 2: simulate a real ALT key press first. Windows relaxes the
    # foreground-lock restriction shortly after genuine input events, so a
    # synthetic Alt press/release bracketing the call is the standard,
    # most broadly effective workaround for this exact restriction.
    try:
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32gui.SetForegroundWindow(hwnd)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        return True
    except Exception:
        pass

    # Technique 3: briefly attach our input thread to the target window's
    # thread, which also grants permission for the focus change.
    try:
        current_thread = win32api.GetCurrentThreadId()
        target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)
        win32process.AttachThreadInput(current_thread, target_thread, True)
        try:
            win32gui.SetForegroundWindow(hwnd)
            return True
        finally:
            win32process.AttachThreadInput(current_thread, target_thread, False)
    except Exception:
        pass

    return False


def _focus_window(hwnd, title: str) -> str:
    """Restores (if minimized) and brings a window to the foreground.
    Shared by both name-based and ordinal-based switching."""
    import win32gui

    if not win32gui.IsWindow(hwnd):
        return f"That window ('{title}') doesn't seem to exist anymore — try listing your windows again."

    # Dismiss any active shell overlay first (Task View, Start Menu,
    # Alt-Tab view). These are special topmost surfaces that can silently
    # swallow/override a foreground-change request from another process —
    # the call can "succeed" with no error, but the overlay just stays
    # visually on top, making it look like nothing happened.
    try:
        import keyboard
        keyboard.send("esc")
        time.sleep(0.15)
    except Exception:
        pass

    success = _force_foreground(hwnd)
    if success:
        return f"Switched to {title}."
    return (f"I found {title}, but Windows wouldn't let me bring it to the front. "
            f"It might be on a different virtual desktop — try switching desktops first, "
            f"or bring it up manually.")


def _switch_to_window(target: str) -> str:
    if _platform_key() != "windows":
        return "Switching windows is currently only supported on Windows."
    if not target:
        return "Which window would you like me to switch to?"

    try:
        import win32gui  # noqa: F401 — import check
    except ImportError:
        return "Switching windows needs pywin32 — pip install pywin32."

    found = _find_window_by_name(target)
    if found is None:
        return f"I couldn't find a window matching '{target}'."
    hwnd, title = found
    return _focus_window(hwnd, title)


def _switch_to_ordinal(ordinal: int | None) -> str:
    """Switches to the Nth window from the last time windows were listed
    (via 'list open windows' or 'show me all my open windows'). If nothing
    has been listed yet this session, enumerates fresh first."""
    global _LAST_WINDOW_LIST
    if _platform_key() != "windows":
        return "Switching windows is currently only supported on Windows."
    if not ordinal:
        return "Which window number did you mean?"

    try:
        import win32gui  # noqa: F401 — import check
    except ImportError:
        return "Switching windows needs pywin32 — pip install pywin32."

    if not _LAST_WINDOW_LIST:
        try:
            _LAST_WINDOW_LIST = _enumerate_windows()
        except Exception as e:
            return f"I couldn't check open windows — {e}"

    if ordinal < 1 or ordinal > len(_LAST_WINDOW_LIST):
        return f"I only see {len(_LAST_WINDOW_LIST)} open windows — there's no window number {ordinal}."

    hwnd, title = _LAST_WINDOW_LIST[ordinal - 1]
    return _focus_window(hwnd, title)


def _close_current_window() -> str:
    """Closes whatever window currently has focus, gently (Alt+F4 — lets
    the app prompt to save unsaved work if needed). Distinct from
    app_control.close_app, which force-kills an entire named application
    via taskkill regardless of unsaved work."""
    if _platform_key() != "windows":
        return "Closing the current window is currently only supported on Windows."
    try:
        import keyboard
        keyboard.send("alt+f4")
        return "Closing the current window."
    except Exception as e:
        return f"I couldn't do that — {e}"


def _new_virtual_desktop() -> str:
    if _platform_key() != "windows":
        return "Virtual desktops are currently only supported on Windows."
    try:
        import keyboard
        keyboard.send("windows+ctrl+d")
        return "Created a new desktop."
    except Exception as e:
        return f"I couldn't create a new desktop — {e}"


def _switch_desktop(direction: str) -> str:
    if _platform_key() != "windows":
        return "Virtual desktops are currently only supported on Windows."
    try:
        import keyboard
        combo = "windows+ctrl+right" if direction == "next" else "windows+ctrl+left"
        keyboard.send(combo)
        return f"Switched to the {direction} desktop."
    except Exception as e:
        return f"I couldn't switch desktops — {e}"


def _close_virtual_desktop() -> str:
    if _platform_key() != "windows":
        return "Virtual desktops are currently only supported on Windows."
    try:
        import keyboard
        keyboard.send("windows+ctrl+f4")
        return "Closed this desktop."
    except Exception as e:
        return f"I couldn't close this desktop — {e}"