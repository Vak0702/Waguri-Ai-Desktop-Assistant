# Waguri — Personal AI Voice Assistant

A desktop voice assistant with a glowing animated orb GUI, wake-word
activation, multi-turn conversation, screen analysis, system vitals, app
control, and full voice control over its own window — all running on free
API tiers by default.

## Features

- 🎙️ Wake word activation ("Waguri") with **multi-turn conversation mode** —
  say the wake word once, then keep talking without repeating it
- 🔮 Glowing orb GUI with idle / listening / thinking / speaking / error states
- 🕶️ **Minimal mode** — hide all buttons/log, leaving only the floating orb;
  toggle by voice, double-click, or the tray menu
- 🖥️ Screen analysis — "what's on my screen", "summarize this document"
- 📊 System vitals — CPU, RAM, disk, battery, network
- 🚀 App control — open/close applications by voice, with fuzzy name
  correction ("sportify" → "spotify") and real install-path detection
- 🔊 Media control — volume, play/pause/skip
- 📁 File search across common folders
- ⏰ Local reminders and notes with OS notifications
- 🪟 Voice-controlled window — "go full screen", "minimize", "mute yourself",
  "hide the controls"
- 💬 General conversation, powered by **independently configurable LLM
  providers** for chat vs. vision (mix free services, no single point of failure)
- 🔇 Noise-reduced, vocabulary-biased speech recognition for better accuracy

- Screenshot , waguri can take screenshots (just say "take screenshots")

- can open new windows/ desktop.
- can minimize/maximize/close/open the windows on your command

## Setup

### 1. Install Python dependencies

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

**Windows-specific:** `pycaw` and `comtypes` (for volume control) install
automatically via the platform marker in requirements.txt.

**macOS-specific:** PyAudio/sounddevice may need `portaudio`:
```bash
brew install portaudio
```

**Linux-specific:** you'll likely need:
```bash
sudo apt install portaudio19-dev python3-pyaudio libxcb-cursor0
```

**A note if you're on Windows and your project lives under OneDrive:**
OneDrive's file sync can corrupt or silently break a Python virtual
environment (thousands of small files syncing at once). If you hit
inexplicable "nothing happens" behavior, move the project to a plain local
folder like `C:\Waguri` and recreate the venv there.

### 2. Configure API keys

```bash
cp .env.example .env
```

Waguri uses **two independent provider settings** — one for general
conversation, one for screen analysis — so you can mix free services rather
than depending on a single one:

```
CHAT_PROVIDER=groq
VISION_PROVIDER=openrouter
```

Supported values: `gemini`, `groq`, `anthropic`, `openrouter`. Only `groq`
lacks vision support, so don't assign it to `VISION_PROVIDER`.

Then fill in the API key(s) for whichever provider(s) you actually assigned:

| Provider | Free? | Get a key at | Notes |
|---|---|---|---|
| **Groq** | Yes, no card | console.groq.com/keys | Fast, chat only, no vision |
| **OpenRouter** | Yes, no card | openrouter.ai/keys | Free vision-capable model (`meta-llama/llama-4-maverick:free`), rate-limited |
| **Gemini** | Yes, no card | aistudio.google.com/apikey | Vision-capable, but some accounts currently hit a `403 PERMISSION_DENIED` bug on Google's side — see note below |
| **Anthropic** | Paid | console.anthropic.com | Vision-capable, most reliable if you're willing to pay |

You only need to set the key(s) for the provider(s) you actually chose above
— unused providers are never initialized, so it's fine to leave the rest
blank.

**Known Gemini issue:** as of mid-2026, many Google accounts (including
brand-new projects with no usage history) hit a `"Your project has been
denied access"` error — a widely-reported false positive in Google's abuse
detection, not something wrong with your setup. If you hit this, use
`openrouter` or `anthropic` for `VISION_PROVIDER` instead.

### 3. First run

```bash
python main.py
```

The orb window should appear. Grant microphone permission if your OS prompts
for it. Say **"Waguri"** followed by a command, e.g.:

- "Waguri, how's my battery?"
- "Waguri, open Chrome"
- "Waguri, what's on my screen?"
- "Waguri, remind me to take a break in 20 minutes"
- "Waguri, shut down" *(will ask for confirmation)*

If something goes wrong on startup, check `waguri_debug.log` (created next
to `main.py`) — every startup step and any crash traceback is logged there,
even if the console window closes too fast to read.

## Conversation mode

You only need to say "Waguri" once. After that, it stays listening and keeps
responding turn after turn — no need to repeat the wake word for follow-up
questions. The conversation ends when either:

- You say something like **"stop listening"**, **"that's all"**,
  **"goodbye"**, or **"never mind"**, or
- You go quiet for about 8 seconds (configurable via `IDLE_TIMEOUT_SECONDS`
  in `config.py`)

Either way, it returns to wake-word standby and you'll need to say "Waguri"
again to start a new conversation.

## Voice-controlled window

Say these at any point during a conversation:

| Say this | What happens |
|---|---|
| "Just show the orb" / "hide the controls" | Buttons and log disappear — only the orb floats on screen |
| "Show the controls" | Restores the full UI |
| "Go full screen" | Orb window fills the entire screen |
| "Exit full screen" | Returns to normal size/position |
| "Minimize" | Hides to the system tray |
| "Mute yourself" | Stops listening entirely |

**You're never locked out**, even in minimal/orb-only mode: double-click the
orb to instantly restore controls, or right-click the tray icon → "Show
Controls." Muting is deliberately one-way by voice — once muted, you need to
click the 🎤 button or use the tray menu to unmute (so a misheard word can't
accidentally silence it permanently).

## How wake word detection works (important caveat)

By default, `core/wake_word.py` runs in **fallback mode**: it periodically
records short audio windows and runs a tiny local Whisper model to check for
the word "waguri" in the transcript. This works out of the box with zero
extra setup, but uses more CPU than a dedicated wake-word model and has a
short detection delay.

For a snappier, lower-CPU experience, train a **custom "Waguri" wake word
model** using [openWakeWord's training
notebook](https://github.com/dscripka/openWakeWord), drop the resulting
`.onnx` file into `assets/waguri.onnx`, then in `core/wake_word.py`:

1. Set `WAKE_WORD_MODE = "openwakeword"`
2. Uncomment and point `Model(wakeword_models=["assets/waguri.onnx"])` to your file
3. `pip install openwakeword`

## Speech recognition accuracy

A few layers work together to reduce mis-transcriptions (e.g. "spotify"
heard as "sportify"):

- **Noise reduction** — spectral-gating noise suppression runs on the raw
  recording before transcription (toggle with `ENABLE_NOISE_REDUCTION` in
  `config.py` if it ever hurts more than helps on your mic)
- **Vocabulary biasing** — Whisper gets a hint listing your known app names
  and common commands before transcribing (toggle with `ENABLE_VOCAB_BIASING`)
- **Fuzzy correction** — a safety net that snaps near-miss app names (like
  "crome" or "spootify") back to the correct known name, without touching
  words that aren't in your app list at all
- **VAD filtering** — skips non-speech segments, reducing Whisper's tendency
  to hallucinate repeated words/numbers on silence or background noise

If accuracy is still inconsistent, try bumping `WHISPER_MODEL_SIZE` in
`config.py` from `small.en` to `medium.en` (more accurate, more CPU/RAM).

## Project structure

```
waguri/
├── main.py                  # entry point, wires GUI + voice thread together
├── config.py                 # settings, loads .env
├── waguri_debug.log           # created on run — full startup/crash log
├── core/
│   ├── wake_word.py           # always-listening wake word detection
│   ├── stt.py                 # speech-to-text (faster-whisper + noise reduction)
│   ├── tts.py                 # text-to-speech (edge-tts / pyttsx3 fallback)
│   ├── llm_client.py           # unified interface over gemini/groq/anthropic/openrouter
│   ├── brain.py                # orchestration + skill dispatch + conversation memory
│   └── intent_router.py        # keyword-based fast intent classification + fuzzy correction
├── skills/
│   ├── system_vitals.py        # CPU/RAM/disk/battery/network
│   ├── app_control.py          # open/close apps, known install paths + process names
│   ├── screen_analysis.py       # screenshot + vision LLM
│   ├── media_control.py         # volume/playback
│   ├── file_ops.py              # file search
│   ├── reminders_notes.py        # local reminders/notes + notifications
│   └── system_power.py           # shutdown/restart/sleep/lock (confirm-gated)
├── gui/
│   ├── orb_widget.py             # the glowing orb (QPainter animation)
│   └── main_window.py             # frameless HUD window, tray icon, minimal mode
└── memory/                        # local JSON storage (gitignored)
```

## Extending Waguri

- **Add a new skill:** create `skills/your_skill.py` with a `handle()`
  function, add a matching pattern in `core/intent_router.py`, and dispatch
  to it in `core/brain.py`'s `handle()` method.
- **Change the voice:** browse available edge-tts voices with
  `edge-tts --list-voices` and set `TTS_VOICE` in `.env`.
- **Add another LLM provider:** `core/llm_client.py` is the single place
  that abstracts chat/vision — add a new `_ensure_provider()` branch plus
  `_yourprovider_chat()` / `_yourprovider_vision()` methods, following the
  existing gemini/groq/anthropic/openrouter pattern.
- **Add more known apps:** extend `APP_ALIASES`, `WINDOWS_KNOWN_PATHS`, and
  `WINDOWS_PROCESS_NAMES` in `skills/app_control.py` — these also feed the
  fuzzy-correction vocabulary automatically via `known_app_names()`.
- **Build a settings UI:** `MainWindow._open_settings()` in `gui/main_window.py`
  is a stub — wire up a QDialog for voice/sensitivity/provider configuration.

## Known limitations / things to harden before daily use

- Fallback wake word mode has noticeable CPU usage and a short detection lag
  — train a custom openWakeWord model for production use.
- `app_control.py`'s known-apps lists only cover common software — extend
  them for anything else you use regularly.
- Reminder time parsing (`reminders_notes.py`) only understands simple
  "in X minutes/hours" phrasing — extend with a proper date/time parser
  (e.g. `dateparser`) for "remind me at 5pm" style phrasing.
- Free-tier LLM providers (Groq, OpenRouter) have rate limits — fine for
  personal use, but not built for heavy/production traffic.
- No authentication/access control — anyone with mic access to your machine
  can issue commands, including (confirmed) shutdown.