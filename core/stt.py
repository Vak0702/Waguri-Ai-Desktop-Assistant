"""
stt.py — Speech-to-text wrapper.

Uses faster-whisper (runs locally, no internet required, good accuracy).
Records a short utterance from the mic (silence-terminated) and returns
the transcribed text.

Swap-friendly: if you prefer Vosk or a cloud STT API, implement the same
`transcribe_once()` interface and swap the import in core/brain.py / main.py.
"""

from __future__ import annotations

import queue
import tempfile
import wave
import time

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

import config
from skills.app_control import known_app_names


class SpeechToText:
    def __init__(self, model_size: str = None, device: str = "cpu", compute_type: str = "int8"):
        model_size = model_size or config.WHISPER_MODEL_SIZE
        # compute_type="int8" keeps CPU usage/memory low; use "float16" if you have a GPU (device="cuda")
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self.sample_rate = 16000

    def record_until_silence(self, silence_threshold: float = 0.01,
                              silence_duration: float = 1.2,
                              max_duration: float = 15.0) -> np.ndarray:
        """Records from the default mic until the user stops talking."""
        q: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            q.put(indata.copy())

        recorded = []
        silence_start = None
        start_time = time.time()

        with sd.InputStream(samplerate=self.sample_rate, channels=1,
                             dtype="float32", callback=callback):
            while True:
                chunk = q.get()
                recorded.append(chunk)
                volume = float(np.abs(chunk).mean())

                if volume < silence_threshold:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > silence_duration and len(recorded) > 5:
                        break
                else:
                    silence_start = None

                if time.time() - start_time > max_duration:
                    break

        return np.concatenate(recorded, axis=0).flatten()

    def transcribe_once(self) -> str:
        """Record one utterance and return the transcribed text."""
        audio = self.record_until_silence()
        audio = self._reduce_noise(audio)

        # initial_prompt biases Whisper's decoding toward vocabulary it's
        # likely to hear — this measurably reduces mishearing app names
        # (e.g. "spotify" -> "sportify") since the model now has those
        # exact words as context going in.
        vocab = ", ".join(known_app_names())
        initial_prompt = (
            "Voice assistant commands: open, close, battery, CPU, RAM, disk, "
            "volume, what's on my screen, remind me, shut down, restart, "
            f"lock screen. App names: {vocab}."
        )

        segments, _info = self.model.transcribe(
            audio, language="en", beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=initial_prompt,
        )
        text = " ".join(seg.text.strip() for seg in segments)
        return text.strip()

    def _reduce_noise(self, audio: np.ndarray) -> np.ndarray:
        """Applies spectral-gating noise reduction to the raw recording
        before transcription — suppresses steady background noise (fans,
        hum, hiss) that can otherwise get transcribed as garbage or subtly
        distort nearby words. Fails safe: if noisereduce isn't installed or
        errors on this clip, the original audio is used unmodified."""
        try:
            import noisereduce as nr
            return nr.reduce_noise(y=audio, sr=self.sample_rate, stationary=False)
        except Exception:
            return audio

    def get_live_amplitude_stream(self, callback):
        """
        Optional helper: opens a mic stream and calls `callback(level: float)`
        continuously with normalized amplitude (0.0-1.0), useful for driving
        the orb's LISTENING pulse in real time. Caller is responsible for
        closing the returned stream when done.
        """
        def _cb(indata, frames, time_info, status):
            level = min(1.0, float(np.abs(indata).mean()) * 20)
            callback(level)

        stream = sd.InputStream(samplerate=self.sample_rate, channels=1,
                                 dtype="float32", callback=_cb)
        stream.start()
        return stream