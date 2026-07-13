"""
brain.py — Orchestration core. Takes transcribed user text, routes it via
intent_router, dispatches to the matching skill, or falls back to the LLM
for general conversation. Maintains short-term conversation memory.
"""

from __future__ import annotations

import re
from collections import deque

import config
from core.intent_router import route, Intent
from core.llm_client import LLMClient
from skills import system_vitals, app_control, screen_analysis, media_control, file_ops, reminders_notes, screenshot, weather, window_control, app_discovery, system_toggles, quick_math


SYSTEM_PROMPT = """You are Waguri, a personal desktop AI voice assistant.
Speak concisely — your replies are spoken aloud via text-to-speech, so avoid
markdown, bullet points, or long paragraphs. Keep answers to 1-3 sentences
unless the user clearly wants detail. Be warm but efficient, a little witty,
never robotic. You have no visibility into the user's screen or system
unless a tool result is provided to you in context."""


class Brain:
    def __init__(self):
        self.llm = LLMClient()
        self.history: deque = deque(maxlen=config.CONVERSATION_MEMORY_TURNS * 2)
        self._pending_confirmation = None  # holds a callable awaiting yes/no

    def handle(self, user_text: str) -> str:
        """Main entry point: takes user utterance, returns Waguri's spoken reply."""
        if not user_text.strip():
            return ""

        # If we're waiting on a yes/no confirmation for a destructive action:
        if self._pending_confirmation is not None:
            return self._resolve_confirmation(user_text)

        routed = route(user_text)

        try:
            if routed.intent == Intent.SYSTEM_VITALS:
                reply = system_vitals.handle(routed.payload)
            elif routed.intent == Intent.APP_CONTROL_OPEN:
                reply = app_control.open_app(routed.payload["target"])
            elif routed.intent == Intent.APP_CONTROL_CLOSE:
                reply = app_control.close_app(routed.payload["target"])
            elif routed.intent == Intent.SCREEN_ANALYSIS:
                reply = screen_analysis.analyze(routed.payload["question"], self.llm)
            elif routed.intent == Intent.TAKE_SCREENSHOT:
                reply = screenshot.take_screenshot()
            elif routed.intent == Intent.WEATHER:
                reply = self._handle_weather(routed.payload)
            elif routed.intent == Intent.WINDOW_CONTROL:
                reply = window_control.handle(routed.payload)
            elif routed.intent == Intent.REFRESH_APPS:
                count = app_discovery.refresh()
                reply = f"Done — I found {count} installed apps."
            elif routed.intent == Intent.SYSTEM_TOGGLE:
                reply = self._handle_system_toggle(routed.payload["action"])
            elif routed.intent == Intent.QUICK_MATH:
                reply = quick_math.handle(routed.payload)
            elif routed.intent == Intent.MEDIA_CONTROL:
                reply = media_control.handle(routed.payload["raw"])
            elif routed.intent == Intent.FILE_SEARCH:
                reply = file_ops.search(routed.payload["query"])
            elif routed.intent == Intent.REMINDER:
                reply = reminders_notes.handle(routed.payload["raw"])
            elif routed.intent == Intent.SYSTEM_POWER:
                reply = self._request_power_confirmation(routed.payload["raw"])
            else:
                reply = self._chat(user_text)
        except Exception as e:
            import traceback
            print("[Waguri] ERROR in brain.handle():")
            traceback.print_exc()
            reply = f"Something went wrong there — {e}"

        self._remember(user_text, reply)
        return reply

    # ---------- general conversation ----------

    def _chat(self, user_text: str) -> str:
        return self.llm.chat(SYSTEM_PROMPT, list(self.history), user_text)

    def _remember(self, user_text: str, reply: str):
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": reply})

    # ---------- weather (location-consent gated) ----------

    def _handle_weather(self, payload: dict) -> str:
        city = payload.get("city")
        if city:
            # Explicit place named — no location access needed at all.
            return weather.get_weather_for_city(city)

        consent = weather.get_location_consent()
        if consent is None:
            # Never asked before — ask now, reusing the same yes/no
            # confirmation mechanism used for destructive system actions.
            self._pending_confirmation = self._resolve_weather_consent
            return ("I don't have permission to check your location yet. I'd use your "
                    "device's location services if available, or your approximate "
                    "IP-based location otherwise. Say yes to allow it, or just tell me "
                    "a specific city instead.")
        elif consent is False:
            return ("I don't have permission to check your location. Say 'yes' to enable "
                    "it, or ask for the weather in a specific city.")
        else:
            return weather.get_weather_for_current_location()

    def _resolve_weather_consent(self, confirmed: bool) -> str:
        weather.set_location_consent(confirmed)
        if confirmed:
            return weather.get_weather_for_current_location()
        return "Okay, I won't check your location. You can always ask for weather in a specific city."

    # ---------- system toggles: Wi-Fi, Bluetooth, Do Not Disturb ----------

    def _handle_system_toggle(self, action: str) -> str:
        if action == "wifi_on":
            return system_toggles.set_wifi(True)
        elif action == "wifi_off":
            return system_toggles.set_wifi(False)
        elif action == "bluetooth_on":
            return system_toggles.set_bluetooth(True)
        elif action == "bluetooth_off":
            return system_toggles.set_bluetooth(False)
        elif action == "dnd_on":
            return system_toggles.set_do_not_disturb(True)
        elif action == "dnd_off":
            return system_toggles.set_do_not_disturb(False)
        return "I didn't understand that."

    # ---------- destructive action confirmation flow ----------

    def _request_power_confirmation(self, raw_text: str) -> str:
        from skills import system_power

        action = system_power.parse_action(raw_text)
        if action is None:
            return "I couldn't tell which power action you meant."

        if config.CONFIRM_DESTRUCTIVE_ACTIONS:
            self._pending_confirmation = lambda confirmed: (
                system_power.execute(action) if confirmed else "Cancelled."
            )
            return f"Are you sure you want to {action.replace('_', ' ')}? Say yes to confirm."
        else:
            return system_power.execute(action)

    def _resolve_confirmation(self, user_text: str) -> str:
        confirmed = bool(re.search(r"\b(yes|yeah|yep|confirm|do it|sure)\b", user_text, re.I))
        callback = self._pending_confirmation
        self._pending_confirmation = None
        reply = callback(confirmed)
        self._remember(user_text, reply)
        return reply