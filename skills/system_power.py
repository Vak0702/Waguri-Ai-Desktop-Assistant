"""
system_power.py — Destructive system power actions: shutdown, restart,
sleep, lock. Always gated behind confirmation in core/brain.py before
execute() is called.
"""

from __future__ import annotations

import platform
import re
import subprocess


def parse_action(raw_text: str) -> str | None:
    t = raw_text.lower()
    if re.search(r"\bshut ?down\b", t):
        return "shutdown"
    if re.search(r"\b(restart|reboot)\b", t):
        return "restart"
    if re.search(r"\bsleep\b", t):
        return "sleep"
    if re.search(r"\block\b", t):
        return "lock"
    return None


def execute(action: str) -> str:
    system = platform.system().lower()
    try:
        if action == "shutdown":
            if system == "windows":
                subprocess.run(["shutdown", "/s", "/t", "5"])
            elif system == "darwin":
                subprocess.run(["osascript", "-e", 'tell app "System Events" to shut down'])
            else:
                subprocess.run(["shutdown", "-h", "now"])
            return "Shutting down now."

        if action == "restart":
            if system == "windows":
                subprocess.run(["shutdown", "/r", "/t", "5"])
            elif system == "darwin":
                subprocess.run(["osascript", "-e", 'tell app "System Events" to restart'])
            else:
                subprocess.run(["shutdown", "-r", "now"])
            return "Restarting now."

        if action == "sleep":
            if system == "windows":
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            elif system == "darwin":
                subprocess.run(["pmset", "sleepnow"])
            else:
                subprocess.run(["systemctl", "suspend"])
            return "Going to sleep."

        if action == "lock":
            if system == "windows":
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
            elif system == "darwin":
                subprocess.run(["pmset", "displaysleepnow"])
            else:
                subprocess.run(["loginctl", "lock-session"])
            return "Locking your screen."

    except Exception as e:
        return f"Couldn't complete that — {e}"

    return "Unknown power action."
