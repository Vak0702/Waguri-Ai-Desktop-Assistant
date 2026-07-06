"""
config.py — Central configuration. Loads secrets from a local .env file
(never commit that file). Adjust defaults here.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- LLM backend ---
# Pick a provider independently for chat vs. screen analysis — you can use
# different API keys/services for each. "gemini" | "groq" | "anthropic".
# Only groq lacks vision support (so don't set VISION_PROVIDER=groq).
CHAT_PROVIDER = os.getenv("CHAT_PROVIDER", "groq")
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "gemini")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
VISION_MODEL = os.getenv("VISION_MODEL", "claude-sonnet-4-6")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")  # chat only, no vision

# --- Wake word ---
WAKE_WORD = "hello"
# If using Porcupine, put your access key + a trained .ppn model path here:
PORCUPINE_ACCESS_KEY = os.getenv("PORCUPINE_ACCESS_KEY", "")
PORCUPINE_KEYWORD_PATH = os.getenv("PORCUPINE_KEYWORD_PATH", "")  # custom "Waguri" model
# Fallback: openWakeWord doesn't need a key but needs its model files downloaded once.

# --- STT ---
STT_ENGINE = os.getenv("STT_ENGINE", "faster-whisper")  # "faster-whisper" | "vosk"
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small.en")  # tiny/base/small/medium — bigger = more accurate, slower
ENABLE_NOISE_REDUCTION = os.getenv("ENABLE_NOISE_REDUCTION", "true").lower() == "true"
ENABLE_VOCAB_BIASING = os.getenv("ENABLE_VOCAB_BIASING", "true").lower() == "true"

# --- TTS ---
TTS_ENGINE = os.getenv("TTS_ENGINE", "edge-tts")  # "edge-tts" | "pyttsx3"
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-AriaNeural")  # edge-tts voice name

# --- Behavior ---
CONFIRM_DESTRUCTIVE_ACTIONS = True  # shutdown, delete files, etc. require confirmation
CONVERSATION_MEMORY_TURNS = 8       # how many past exchanges to keep as LLM context
IDLE_TIMEOUT_SECONDS = 8            # seconds of silence before returning to idle listening

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_DB_PATH = os.path.join(BASE_DIR, "memory", "waguri_memory.db")
NOTES_PATH = os.path.join(BASE_DIR, "memory", "notes.json")