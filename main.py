"""
main.py — Waguri entry point.

Wires together:
  - MainWindow (GUI: orb + tray + log)
  - WakeWordDetector (background thread, always listening)
  - SpeechToText / TextToSpeech
  - Brain (LLM + skill dispatch)
  - Reminder scheduler (background thread)

Threading model: PyQt6's GUI must run on the main thread. Wake word
listening, STT, TTS, and LLM calls are all blocking/CPU-bound, so they
run on a dedicated worker thread and communicate back to the GUI via Qt
signals (thread-safe by design in PyQt6).
"""

from __future__ import annotations

import sys
import time

from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import QApplication

import config
from core.wake_word import WakeWordDetector
from core.stt import SpeechToText
from core.tts import TextToSpeech
from core.brain import Brain
from core.intent_router import route, Intent
from gui.main_window import MainWindow
from gui.orb_widget import OrbState
from skills import reminders_notes


class VoiceWorker(QThread):
    """Background thread running the full listen -> transcribe -> think ->
    speak loop, plus always-on wake word detection. Emits signals so the
    GUI (main thread) can react safely."""

    orbStateChanged = pyqtSignal(object)     # OrbState
    transcript = pyqtSignal(str, str)        # speaker, text
    amplitudeUpdate = pyqtSignal(float)
    guiCommand = pyqtSignal(str)             # action name, e.g. "fullscreen_on"

    def __init__(self):
        super().__init__()
        self._muted = False
        self._running = True

        self.stt = SpeechToText()
        self.tts = TextToSpeech()
        self.brain = Brain()
        self.wake_word = WakeWordDetector(on_wake=self._on_wake_detected)

        self._wake_triggered = False

    def run(self):
        # Wake word detector blocks this thread in its own loop; when it
        # detects "Waguri", it calls _on_wake_detected() from inside that
        # loop, so we handle the full interaction there, then resume listening.
        self.wake_word.start()

    def stop(self):
        self._running = False
        self.wake_word.stop()

    def set_muted(self, muted: bool):
        self._muted = muted

    # ---------- interaction cycle, triggered by wake word ----------

    def _on_wake_detected(self):
        if self._muted or not self._running:
            return

        try:
            print("[Waguri] Wake word detected. Conversation started.")
            silence_since = None  # tracks how long we've heard nothing, for auto-sleep

            while self._running and not self._muted:
                self.orbStateChanged.emit(OrbState.LISTENING)

                stream = self.stt.get_live_amplitude_stream(
                    lambda level: self.amplitudeUpdate.emit(level)
                )
                user_text = self.stt.transcribe_once()
                stream.stop()
                stream.close()

                # --- nothing heard: track silence, auto-sleep after a timeout ---
                if not user_text.strip():
                    if silence_since is None:
                        silence_since = time.time()
                        print("[Waguri] Heard nothing, waiting for more...")
                    elif time.time() - silence_since > config.IDLE_TIMEOUT_SECONDS:
                        print("[Waguri] Idle timeout reached, going back to sleep.")
                        break
                    continue

                silence_since = None  # reset, we heard something
                print(f"[Waguri] Transcribed: '{user_text}'")
                self.transcript.emit("You", user_text)

                # --- check if this turn is the user ending the conversation ---
                routed = route(user_text)
                if routed.intent == Intent.END_CONVERSATION:
                    reply = "Okay, let me know if you need anything else."
                    print("[Waguri] End-of-conversation phrase detected.")
                    self.transcript.emit("Waguri", reply)
                    self.orbStateChanged.emit(OrbState.SPEAKING)
                    self.tts.speak(reply, amplitude_callback=lambda lvl: self.amplitudeUpdate.emit(lvl))
                    break

                # --- GUI/window control: instant, no LLM round-trip needed ---
                if routed.intent == Intent.GUI_CONTROL:
                    action = routed.payload["action"]
                    print(f"[Waguri] GUI command: {action}")

                    ack_messages = {
                        "mute_mic": "Going quiet. Click the mic button to bring me back.",
                        "hide_controls": "Hiding controls. Say 'show controls', double-click the orb, or use the tray menu to bring them back.",
                        "show_controls": "Here you go.",
                        "minimize": "Minimizing to the tray.",
                        "fullscreen_on": "Going full screen.",
                        "exit_fullscreen": "Exiting full screen.",
                    }
                    reply = ack_messages.get(action, "Done.")
                    self.transcript.emit("Waguri", reply)
                    self.orbStateChanged.emit(OrbState.SPEAKING)
                    self.tts.speak(reply, amplitude_callback=lambda lvl: self.amplitudeUpdate.emit(lvl))

                    self.guiCommand.emit(action)

                    if action == "mute_mic":
                        # Mute takes effect immediately in this thread too —
                        # further wake-word triggers are ignored until a
                        # human physically unmutes via the GUI/tray.
                        self._muted = True
                        break

                    continue  # conversation keeps going for other GUI actions

                # --- normal turn: think, then speak, then loop for the next turn ---
                self.orbStateChanged.emit(OrbState.THINKING)
                print("[Waguri] Sending to LLM/brain...")
                reply = self.brain.handle(user_text)
                print(f"[Waguri] Reply: '{reply}'")

                self.transcript.emit("Waguri", reply)
                self.orbStateChanged.emit(OrbState.SPEAKING)
                print("[Waguri] Speaking...")
                self.tts.speak(reply, amplitude_callback=lambda lvl: self.amplitudeUpdate.emit(lvl))
                print("[Waguri] Done speaking. Listening for next turn...")
                # loop continues — no wake word needed for the next turn

            print("[Waguri] Conversation ended. Back to wake-word standby.")
            self.orbStateChanged.emit(OrbState.IDLE)

        except Exception:
            import traceback
            print("[Waguri] ERROR during interaction cycle:")
            traceback.print_exc()
            self.orbStateChanged.emit(OrbState.ERROR)


class WaguriApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.window = MainWindow()
        self.worker = VoiceWorker()

        self._wire_signals()
        self._start_reminder_scheduler()

        self.window.show()
        self.worker.start()

    def _wire_signals(self):
        self.worker.orbStateChanged.connect(self.window.set_orb_state)
        self.worker.transcript.connect(self.window.append_log)
        self.worker.amplitudeUpdate.connect(self.window.orb.feed_amplitude)
        self.worker.guiCommand.connect(self._handle_gui_command)

        self.window.micToggled.connect(self.worker.set_muted)
        self.window.quitRequested.connect(self._quit)
        self.window.settingsRequested.connect(self._open_settings)

    def _handle_gui_command(self, action: str):
        """Dispatches a voice-triggered UI action (from VoiceWorker, running
        on a background thread) to the actual GUI method on the main thread.
        Qt's signal/slot mechanism makes this thread-safe automatically."""
        dispatch = {
            "mute_mic": lambda: self.window.set_muted_ui(True),
            "hide_controls": self.window.hide_controls,
            "show_controls": self.window.show_controls,
            "minimize": self.window._minimize_to_tray,
            "fullscreen_on": self.window.enter_fullscreen,
            "exit_fullscreen": self.window.exit_fullscreen,
        }
        handler = dispatch.get(action)
        if handler:
            handler()
        else:
            print(f"[Waguri] Unknown GUI command: {action}")

    def _start_reminder_scheduler(self):
        self.reminder_timer = QTimer()
        self.reminder_timer.timeout.connect(self._check_reminders)
        self.reminder_timer.start(30_000)  # every 30 seconds

    def _check_reminders(self):
        due = reminders_notes.check_due_reminders()
        for text in due:
            self.window.append_log("Waguri", f"Reminder: {text}")
            self.window.set_orb_state(OrbState.SPEAKING)
            self.worker.tts.speak(f"Reminder: {text}")
            self.window.set_orb_state(OrbState.IDLE)
            self.window.tray.showMessage("Waguri Reminder", text)

    def _open_settings(self):
        # Placeholder: wire up a real settings dialog here (voice selection,
        # wake sensitivity, API key entry, etc.) as a future enhancement.
        self.window.append_log("Waguri", "Settings panel isn't built yet — edit config.py / .env for now.")

    def _quit(self):
        self.worker.stop()
        self.worker.wait(2000)
        self.app.quit()

    def run(self):
        return self.app.exec()


if __name__ == "__main__":
    import os
    import traceback

    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "waguri_debug.log")

    def _log(msg: str):
        """Writes to both the console and a log file, and flushes immediately —
        so we capture output even if the console window/buffering swallows it."""
        print(msg, flush=True)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass

    try:
        _log("=" * 50)
        _log("[Waguri] Starting up...")
        _log(f"[Waguri] Python: {sys.version}")
        _log(f"[Waguri] Working directory: {os.getcwd()}")
        _log(f"[Waguri] Script directory: {os.path.dirname(os.path.abspath(__file__))}")

        provider_keys = {"gemini": config.GEMINI_API_KEY, "groq": config.GROQ_API_KEY, "anthropic": config.ANTHROPIC_API_KEY}
        if not provider_keys.get(config.CHAT_PROVIDER):
            _log(f"[Waguri] WARNING: No API key set for CHAT_PROVIDER '{config.CHAT_PROVIDER}' in .env.")
        if not provider_keys.get(config.VISION_PROVIDER):
            _log(f"[Waguri] WARNING: No API key set for VISION_PROVIDER '{config.VISION_PROVIDER}' in .env.")

        _log("[Waguri] Creating application...")
        app_instance = WaguriApp()
        _log("[Waguri] Application created successfully. Entering main loop...")
        exit_code = app_instance.run()
        _log(f"[Waguri] Main loop exited with code {exit_code}.")
        sys.exit(exit_code)

    except Exception:
        _log("[Waguri] FATAL ERROR during startup:")
        _log(traceback.format_exc())
        print("\n--- Waguri crashed. Full details above and in waguri_debug.log ---")
        input("Press Enter to close this window...")
        sys.exit(1)