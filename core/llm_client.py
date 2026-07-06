"""
llm_client.py — Unified interface over multiple LLM providers, with
*independent* provider selection for chat vs. vision. This lets you use
different API keys for different jobs at the same time — e.g. Groq
(fast, free, chat-only) for conversation, and Gemini (free, vision-capable)
for screen analysis — without manually flipping a single setting back and
forth in .env.

Configure via .env:
    CHAT_PROVIDER=groq      # "gemini" | "groq" | "anthropic"
    VISION_PROVIDER=gemini  # "gemini" | "anthropic"  (groq has no vision support)

Only the API key(s) for whichever provider(s) you actually assign to
CHAT_PROVIDER / VISION_PROVIDER need to be set — unused providers are never
initialized, so there's no penalty to leaving other keys blank.
"""

from __future__ import annotations

import base64

import config


class LLMClient:
    """Factory + unified interface. Instantiate once in brain.py."""

    def __init__(self):
        self.chat_provider = config.CHAT_PROVIDER
        self.vision_provider = config.VISION_PROVIDER

        # Lazily-initialized per-provider client handles. If the same
        # provider is used for both chat and vision, it's only set up once.
        self._gemini_client = None
        self._anthropic_client = None
        self._groq_client = None

        self.chat_available = self._ensure_provider(self.chat_provider)
        self.vision_available = (
            self._ensure_provider(self.vision_provider)
            if self.vision_provider != "groq"  # groq has no vision support at all
            else False
        )

    # ---------- lazy provider setup ----------

    def _ensure_provider(self, provider: str) -> bool:
        """Initializes the client for `provider` if not already done.
        Returns True if that provider is ready to use (has a valid key)."""
        if provider == "gemini":
            if self._gemini_client is not None:
                return True
            if not config.GEMINI_API_KEY:
                return False
            from google import genai
            self._gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
            return True

        elif provider == "groq":
            if self._groq_client is not None:
                return True
            if not config.GROQ_API_KEY:
                return False
            from groq import Groq
            self._groq_client = Groq(api_key=config.GROQ_API_KEY)
            return True

        elif provider == "anthropic":
            if self._anthropic_client is not None:
                return True
            if not config.ANTHROPIC_API_KEY:
                return False
            import anthropic
            self._anthropic_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            return True

        return False

    # ---------- chat ----------

    def chat(self, system_prompt: str, history: list[dict], user_text: str) -> str:
        if not self.chat_available:
            return self._missing_key_message(self.chat_provider, "chat")

        if self.chat_provider == "gemini":
            return self._gemini_chat(system_prompt, history, user_text)
        elif self.chat_provider == "groq":
            return self._groq_chat(system_prompt, history, user_text)
        else:
            return self._anthropic_chat(system_prompt, history, user_text)

    def _gemini_chat(self, system_prompt: str, history: list[dict], user_text: str) -> str:
        from google.genai import types

        gemini_history = [
            types.Content(
                role="model" if h["role"] == "assistant" else "user",
                parts=[types.Part.from_text(text=h["content"])],
            )
            for h in history
        ]

        chat = self._gemini_client.chats.create(
            model=config.GEMINI_MODEL,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
            history=gemini_history,
        )
        response = chat.send_message(user_text)
        return response.text.strip()

    def _anthropic_chat(self, system_prompt: str, history: list[dict], user_text: str) -> str:
        messages = list(history) + [{"role": "user", "content": user_text}]
        response = self._anthropic_client.messages.create(
            model=config.LLM_MODEL,
            max_tokens=400,
            system=system_prompt,
            messages=messages,
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def _groq_chat(self, system_prompt: str, history: list[dict], user_text: str) -> str:
        messages = [{"role": "system", "content": system_prompt}] + list(history) + \
                   [{"role": "user", "content": user_text}]
        response = self._groq_client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=messages,
            max_tokens=400,
        )
        return response.choices[0].message.content.strip()

    # ---------- vision ----------

    def vision(self, prompt: str, image_png_bytes: bytes) -> str:
        if self.vision_provider == "groq":
            return ("Screen analysis needs a vision-capable provider — Groq doesn't support "
                    "images. Set VISION_PROVIDER=gemini (or anthropic) in .env.")
        if not self.vision_available:
            return self._missing_key_message(self.vision_provider, "screen analysis")

        if self.vision_provider == "gemini":
            return self._gemini_vision(prompt, image_png_bytes)
        else:
            return self._anthropic_vision(prompt, image_png_bytes)

    def _gemini_vision(self, prompt: str, image_png_bytes: bytes) -> str:
        from google.genai import types
        response = self._gemini_client.models.generate_content(
            model=config.GEMINI_VISION_MODEL,
            contents=[
                types.Part.from_bytes(data=image_png_bytes, mime_type="image/png"),
                prompt,
            ],
        )
        return response.text.strip()

    def _anthropic_vision(self, prompt: str, image_png_bytes: bytes) -> str:
        b64_image = base64.standard_b64encode(image_png_bytes).decode("utf-8")
        response = self._anthropic_client.messages.create(
            model=config.VISION_MODEL,
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64_image}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()

    # ---------- helpers ----------

    def _missing_key_message(self, provider: str, purpose: str) -> str:
        key_hints = {
            "gemini": "GEMINI_API_KEY (free at aistudio.google.com/apikey)",
            "groq": "GROQ_API_KEY (free at console.groq.com/keys)",
            "anthropic": "ANTHROPIC_API_KEY",
        }
        hint = key_hints.get(provider, f"{provider.upper()}_API_KEY")
        return f"I don't have a {provider} API key configured for {purpose} — add {hint} to .env."