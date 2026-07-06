"""
screen_analysis.py — Captures the screen and sends it to a vision-capable
LLM (Gemini or Claude, whichever is configured) to answer questions like
"what's on my screen" or "summarize this document".

Uses `mss` for fast, cross-platform screenshot capture.
"""

from __future__ import annotations

import io

import mss
import mss.tools
from PIL import Image


def _capture_screenshot() -> bytes:
    """Captures the primary monitor and returns PNG bytes, downscaled to
    keep the vision API request small and fast."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # index 0 is "all monitors combined"; 1 is primary
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        max_width = 1280
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def analyze(question: str, llm) -> str:
    """`llm` is a core.llm_client.LLMClient instance."""
    png_bytes = _capture_screenshot()
    prompt_question = question if question and len(question) > 6 else "What's currently on my screen? Describe it briefly."

    prompt = (
        "You're Waguri, a voice assistant. The user asked: "
        f'"{prompt_question}". Look at this screenshot of their screen and answer '
        "concisely (1-3 sentences), as if speaking aloud."
    )
    return llm.vision(prompt, png_bytes)
