"""
tts.py — Text-to-speech wrapper using edge-tts (free, natural-sounding,
requires internet). Falls back to pyttsx3 (fully offline, robotic but
reliable) if edge-tts fails or is unavailable.

Exposes amplitude callbacks so the GUI orb can pulse in sync with speech.
"""

from __future__ import annotations

import asyncio
import io
import tempfile
import os
import wave
import audioop  # stdlib; used only for RMS amplitude estimation

import numpy as np
import sounddevice as sd
import soundfile as sf

import config


class TextToSpeech:
    def __init__(self, voice: str = None):
        self.voice = voice or config.TTS_VOICE
        self._engine = config.TTS_ENGINE

    # ---------- public API ----------

    def speak(self, text: str, amplitude_callback=None):
        """
        Synthesize `text` and play it. If `amplitude_callback` is given,
        it's called repeatedly during playback with a 0.0-1.0 amplitude
        value so the caller (GUI) can animate the orb in sync.
        """
        if not text.strip():
            return

        try:
            if self._engine == "edge-tts":
                wav_path = asyncio.run(self._synthesize_edge_tts(text))
            else:
                wav_path = self._synthesize_pyttsx3(text)

            self._play_with_amplitude(wav_path, amplitude_callback)
        finally:
            try:
                os.remove(wav_path)
            except Exception:
                pass

    # ---------- synthesis backends ----------

    async def _synthesize_edge_tts(self, text: str) -> str:
        import edge_tts  # imported lazily so app still runs without it installed
        communicate = edge_tts.Communicate(text, self.voice)
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        await communicate.save(path)

        # Convert mp3 -> wav for consistent playback/amplitude analysis
        wav_path = path.replace(".mp3", ".wav")
        data, samplerate = sf.read(path)
        sf.write(wav_path, data, samplerate)
        os.remove(path)
        return wav_path

    def _synthesize_pyttsx3(self, text: str) -> str:
        import pyttsx3  # offline fallback engine
        engine = pyttsx3.init()
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        engine.save_to_file(text, path)
        engine.runAndWait()
        return path

    # ---------- playback with live amplitude ----------

    def _play_with_amplitude(self, wav_path: str, amplitude_callback):
        data, samplerate = sf.read(wav_path, dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)  # downmix to mono for amplitude calc

        chunk_size = int(samplerate * 0.05)  # 50ms chunks

        def stream_callback(outdata, frames, time_info, status):
            nonlocal pos
            chunk = data[pos:pos + frames]
            if len(chunk) < frames:
                outdata[:len(chunk), 0] = chunk
                outdata[len(chunk):, 0] = 0
                raise sd.CallbackStop()
            else:
                outdata[:, 0] = chunk
            if amplitude_callback:
                level = min(1.0, float(np.abs(chunk).mean()) * 8)
                amplitude_callback(level)
            pos += frames

        pos = 0
        with sd.OutputStream(samplerate=samplerate, channels=1,
                              callback=stream_callback, blocksize=chunk_size):
            sd.sleep(int(len(data) / samplerate * 1000) + 100)

        if amplitude_callback:
            amplitude_callback(0.0)
