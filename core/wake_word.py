"""
wake_word.py — Always-listening, low-CPU wake word detector.

Default: openWakeWord (free, no API key, runs a small ONNX model locally).
openWakeWord ships generic wake words out of the box; for a *custom*
"Waguri" model you'd train one via their training notebook and drop the
resulting .onnx/.tflite file in assets/. Until you do that, this module
falls back to a simple keyword-spotting mode: it continuously transcribes
short audio windows with a tiny STT pass and checks for "waguri" in the
text. This fallback is heavier on CPU than a true wake-word model but
requires zero extra setup and works immediately.

Set WAKE_WORD_MODE in this file to switch strategies once you've trained
a custom openWakeWord model.
"""

from __future__ import annotations

import time
import numpy as np
import sounddevice as sd

import config

WAKE_WORD_MODE = "fallback_stt"  # "openwakeword" | "fallback_stt"


class WakeWordDetector:
    def __init__(self, on_wake):
        """
        on_wake: callback invoked (no args) when the wake word is detected.
        """
        self.on_wake = on_wake
        self._running = False
        self.sample_rate = 16000

        if WAKE_WORD_MODE == "openwakeword":
            self._init_openwakeword()

    def _init_openwakeword(self):
        from openwakeword.model import Model
        # Replace with your custom-trained "waguri" model path once available:
        # self.oww_model = Model(wakeword_models=["assets/waguri.onnx"])
        self.oww_model = Model()  # uses bundled generic models as placeholder

    # ---------- main loop ----------

    def start(self):
        self._running = True
        if WAKE_WORD_MODE == "openwakeword":
            self._run_openwakeword_loop()
        else:
            self._run_fallback_loop()

    def stop(self):
        self._running = False

    def _run_openwakeword_loop(self):
        chunk_samples = 1280  # openWakeWord expects 80ms @ 16kHz chunks

        def callback(indata, frames, time_info, status):
            if not self._running:
                raise sd.CallbackStop()
            audio_int16 = (indata[:, 0] * 32767).astype(np.int16)
            predictions = self.oww_model.predict(audio_int16)
            for _name, score in predictions.items():
                if score > 0.5:
                    self.on_wake()

        with sd.InputStream(samplerate=self.sample_rate, channels=1,
                             dtype="float32", blocksize=chunk_samples,
                             callback=callback):
            while self._running:
                sd.sleep(100)

    def _run_fallback_loop(self):
        """
        Lightweight fallback: uses a tiny whisper model to periodically
        check short audio snippets for the wake word. Not as efficient as
        a dedicated wake-word model, but works out of the box.
        """
        from faster_whisper import WhisperModel
        tiny_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")

        window_seconds = 2.0
        block_samples = int(self.sample_rate * window_seconds)

        while self._running:
            audio = sd.rec(block_samples, samplerate=self.sample_rate,
                            channels=1, dtype="float32")
            sd.wait()
            flat = audio.flatten()

            # Skip near-silent windows to save compute
            if float(np.abs(flat).mean()) < 0.005:
                continue

            segments, _ = tiny_model.transcribe(flat, language="en", beam_size=1)
            text = " ".join(seg.text.lower() for seg in segments)
            if config.WAKE_WORD in text:
                self.on_wake()
                time.sleep(1.0)  # brief cooldown to avoid immediate re-trigger
