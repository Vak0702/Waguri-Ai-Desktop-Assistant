# Waguri — Personal AI Voice Assistant

A desktop voice assistant with a glowing animated orb GUI, wake-word
activation, multi-turn conversation, screen analysis, weather, window
management, system vitals, app control (including auto-discovery of
anything installed), and full voice control over its own window — all
running on free API tiers by default.

## Features

- 🎙️ Wake word activation ("Waguri") with **multi-turn conversation mode**
  — say the wake word once, then keep talking without repeating it
- 👋 **Wake greeting + proactive health check** — a short spoken greeting
  each time it wakes, plus a silent system/connection check that only
  speaks up if something's actually wrong (low battery, high CPU/RAM,
  a broken LLM connection)
- 🔮 Glowing orb GUI with idle / listening / thinking / speaking / error states
- 🕶️ **Minimal mode** — hide all buttons/log, leaving only the floating orb;
  toggle by voice, double-click, or the tray menu
- 🪟 **Voice-controlled window** — fullscreen, minimize, mute, hide/show controls
- 🖥️ Screen analysis — "what's on my screen", "summarize this document"
- 📸 **Screenshot capture** — saves straight to disk, no LLM/API call needed
- 🌦️ **Weather** — by city name (no permission needed) or your current
  location (asks first; tries precise Windows Location Services, falls
  back to approximate IP-based location)
- 📊 System vitals — CPU, RAM, disk, battery, network
- 🚀 **App control with auto-discovery** — "open X" works for anything
  installed (desktop apps *and* Microsoft Store/UWP apps like Netflix),
  scanned via Windows' own Start Menu index — no hand-maintained list
  required. Includes fuzzy name correction ("sportify" → "spotify")
- 🪟 **Window management** — snap left/right, maximize/minimize, switch to
  a window by name *or* by position ("switch to the second window"),
  gently close the current window, list/enumerate open windows, create
  and switch between virtual desktops
- 🔊 Media control — volume, play/pause/skip
- 📁 File search across common folders
- ⏰ Local reminders and notes with OS notifications
- 💬 General conversation, powered by **independently configurable LLM
  providers** for chat vs. vision — mix free services so no single
  provider outage takes everything down
- 🔇 Noise-reduced, vocabulary-biased, fuzzy-corrected speech recognition

- can assist you in simple mathematics calculation

- can hit your bluetooth on your command

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

**Windows-specific:** `pycaw`, `comtypes`, `winsdk`, and `pywin32` install
automatically via platform markers in requirements.txt — they're needed
for volume control, precise location, and window management respectively.

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
environment, or cause the whole app to exit instantly with no error at all
(thousands of small files syncing at once confuses things). If you hit
inexplicable "nothing happens" behavior, move the project to a plain local
folder like `C:\Waguri` and recreate the venv there — this is a known,
confirmed fix.

### 2. Configure API keys

```bash
cp .env.example .env
```

Waguri uses **two independent provider settings** — one for general
conversation, one for screen analysis — so a problem with one service
never takes down the other:

```
CHAT_PROVIDER=groq
VISION_PROVIDER=openrouter
```

Supported values: `gemini`, `groq`, `anthropic`, `openrouter`. Only `groq`
lacks vision support, so don't assign it to `VISION_PROVIDER`.

| Provider | Free? | Get a key at | Notes |
|---|---|---|---|
| **Groq** | Yes, no card | console.groq.com/keys | Fast, chat only, no vision |
| **OpenRouter** | Yes, no card | openrouter.ai/keys | Free vision-capable model (`meta-llama/llama-4-maverick:free`), rate-limited |
| **Gemini** | Yes, no card | aistudio.google.com/apikey | Vision-capable, but some accounts currently hit a `403 PERMISSION_DENIED` "project denied access" bug on Google's side — a widely-reported issue, not something wrong with your setup |
| **Anthropic** | Paid | console.anthropic.com | Vision-capable, most reliable if you're willing to pay |

You only need the key(s) for whichever provider(s) you actually assign —
unused providers are never initialized.

**Also install these two extra packages** (needed for OpenRouter and Groq,
beyond what's pinned in requirements.txt if you set up your `.env` after
first installing):
```bash
pip install openai groq
```

### 3. First run

```bash
python main.py
```

Grant microphone permission if your OS prompts for it. Say **"Waguri"**,
wait for the greeting, then try things like:

- "How's my battery?"
- "Open Chrome" / "Open Netflix" / literally any installed app
- "What's on my screen?"
- "Take a screenshot"
- "What's the weather in Tokyo?"
- "Switch to the second window"
- "Remind me to take a break in 20 minutes"
- "Shut down" *(will ask for confirmation)*

If something goes wrong on startup, check `waguri_debug.log` (created next
to `main.py`) — every startup step and any crash traceback is logged there,
even if the console window closes too fast to read.

## Conversation mode

Say "Waguri" once, then keep talking — no need to repeat the wake word
between commands. Ends when you say **"stop listening"**, **"that's all"**,
**"goodbye"**, or **"never mind"**, or after about 8 seconds of silence
(`IDLE_TIMEOUT_SECONDS` in `config.py`).

## Wake greeting & health check

Every time it wakes, you'll hear a short randomized greeting. Silently, it
also checks CPU/RAM/disk/battery and whether your configured LLM providers
are actually reachable — and only mentions it if something's genuinely off:

> "Hey, I'm here. Heads up — I don't have a working connection for screen
> analysis right now."

## Voice-controlled window

| Say this | What happens |
|---|---|
| "Just show the orb" / "hide the controls" | Only the orb stays visible |
| "Show the controls" | Restores the full UI |
| "Go full screen" / "Exit full screen" | Toggles the orb window's fullscreen |
| "Minimize" | Hides Waguri's own window to the tray |
| "Mute yourself" | Stops listening entirely (voice can't undo this — click the 🎤 button or use the tray menu) |

Double-click the orb anytime to instantly toggle minimal mode, and the tray
menu's "Show Controls" is always available as a guaranteed fallback.

## Window & desktop management (for *other* apps)

| Say this | What happens |
|---|---|
| "Snap this window left / right" | Native Windows snap |
| "Maximize / minimize this window" | *(the word "window" disambiguates this from Waguri's own minimize)* |
| "Switch to Chrome" | Focuses a window by (fuzzy) name match |
| "List open windows" | Speaks back a numbered list |
| "Show me all my open windows" | Opens Task View |
| "Switch to the second window" / "go to window 3" | Focuses by position — numbering matches whatever you last heard/saw listed |
| "Close this window" | Gently closes the focused window (Alt+F4 — respects unsaved-work prompts), unlike "close Chrome" which force-kills the whole app |
| "Open a new desktop" / "switch to the next desktop" / "close this desktop" | Virtual desktop management |

**Known limitation:** a window on a *different virtual desktop* than the
one you're currently on can't be focused without switching desktops first
— that's a Windows restriction, not a bug. If "switch to X" says it found
the window but nothing visibly changes, try switching desktops first.

## Weather & location privacy

- "What's the weather in [city]" — direct lookup, **no location access at all**
- "What's the weather" (no city) — asks permission the first time:
  > "I don't have permission to check your location yet. I'd use your
  > device's location services if available, or your approximate IP-based
  > location otherwise. Say yes to allow it, or just tell me a city."
- Your answer is remembered (`memory/settings.json`, gitignored) so you're
  only asked once. Location lookup tries Windows Location Services first
  (Wi-Fi/GPS positioning, triggers its own native Windows permission
  prompt too — check Settings → Privacy & Security → Location if it never
  appears) and falls back to approximate IP-based location automatically.

## App auto-discovery

"Open X" checks, in order: a small hand-verified list of very common apps
(Chrome, Spotify, VS Code, Firefox) → an auto-discovered index built from
Windows' own Start Menu (`Get-StartApps`, which covers both traditional
desktop apps *and* Microsoft Store/UWP apps like Netflix) → a generic
fallback. Say **"refresh my apps"** to rescan after installing new software
mid-session (a fresh run of `python main.py` also naturally re-scans).

## How wake word detection works (important caveat)

By default, `core/wake_word.py` runs in **fallback mode**: it periodically
records short audio windows and runs a tiny local Whisper model to check for
"waguri" in the transcript. Works out of the box, but uses more CPU than a
dedicated wake-word model and has a short detection delay.

For a snappier, lower-CPU experience, train a **custom "Waguri" wake word
model** using [openWakeWord's training
notebook](https://github.com/dscripka/openWakeWord), drop the resulting
`.onnx` file into `assets/waguri.onnx`, then in `core/wake_word.py`:
set `WAKE_WORD_MODE = "openwakeword"`, point `Model(wakeword_models=[...])`
at your file, and `pip install openwakeword`.

## Speech recognition accuracy

Several layers work together to reduce mis-transcriptions:

- **Noise reduction** — spectral-gating suppression before transcription
  (toggle: `ENABLE_NOISE_REDUCTION` in `.env`)
- **Vocabulary biasing** — Whisper gets a hint listing known app names and
  commands before transcribing (toggle: `ENABLE_VOCAB_BIASING`; capped at
  40 names even if auto-discovery finds hundreds, to avoid diluting the hint)
- **Fuzzy correction** — near-miss app names ("crome", "spootify") snap back
  to the correct name; unrecognized names pass through untouched
- **VAD filtering** — skips non-speech segments, reducing hallucinated
  repeated words/numbers on silence or background noise

If accuracy is still inconsistent, try bumping `WHISPER_MODEL_SIZE` in
`.env` from `small.en` to `medium.en` (more accurate, more CPU/RAM).

## Project structure

```
waguri/
├── main.py                  # entry point — GUI + voice thread + wake greeting
├── config.py                 # settings, loads .env
├── waguri_debug.log           # created on run — full startup/crash log
├── core/
│   ├── wake_word.py           # always-listening wake word detection
│   ├── stt.py                 # speech-to-text (faster-whisper + noise reduction + vocab biasing)
│   ├── tts.py                 # text-to-speech (edge-tts / pyttsx3 fallback)
│   ├── llm_client.py           # unified interface: gemini/groq/anthropic/openrouter
│   ├── brain.py                # orchestration + skill dispatch + conversation memory
│   └── intent_router.py        # keyword-based intent classification + fuzzy correction
├── skills/
│   ├── system_vitals.py        # CPU/RAM/disk/battery/network + wake-time health check
│   ├── app_control.py          # open/close apps (known paths + auto-discovery + generic fallback)
│   ├── app_discovery.py         # Start Menu scanning via Get-StartApps (desktop + Store apps)
│   ├── screen_analysis.py       # screenshot + vision LLM description/Q&A
│   ├── screenshot.py             # save-to-disk screenshot, no LLM needed
│   ├── weather.py                # Open-Meteo forecasts + city geocoding
│   ├── gps_location.py            # Windows Location Services, with IP fallback
│   ├── window_control.py          # snap/switch/list/close windows, virtual desktops
│   ├── media_control.py           # volume/playback
│   ├── file_ops.py                # file search
│   ├── reminders_notes.py          # local reminders/notes + notifications
│   └── system_power.py             # shutdown/restart/sleep/lock (confirm-gated)
├── gui/
│   ├── orb_widget.py             # the glowing orb (QPainter animation)
│   └── main_window.py             # frameless HUD window, tray icon, minimal mode
└── memory/                        # local JSON storage (gitignored): notes, reminders, weather consent
```

## Extending Waguri

- **Add a new skill:** create `skills/your_skill.py` with a `handle()`
  function, add a matching pattern in `core/intent_router.py`, and dispatch
  to it in `core/brain.py`'s `handle()` method.
- **Change the voice:** browse voices with `edge-tts --list-voices` and set
  `TTS_VOICE` in `.env`.
- **Add another LLM provider:** `core/llm_client.py` is the single
  abstraction point — add a new `_ensure_provider()` branch plus
  `_yourprovider_chat()` / `_yourprovider_vision()` methods.
- **Add more known apps:** extend `APP_ALIASES` / `WINDOWS_KNOWN_PATHS` /
  `WINDOWS_PROCESS_NAMES` in `skills/app_control.py` for anything
  auto-discovery doesn't catch — these also feed the fuzzy-correction
  vocabulary automatically via `known_app_names()`.
- **Build a settings UI:** `MainWindow._open_settings()` in
  `gui/main_window.py` is a stub — wire up a QDialog for voice/sensitivity/
  provider configuration.

## Known limitations / things to harden before daily use

- Fallback wake word mode has noticeable CPU usage and a short detection
  lag — train a custom openWakeWord model for production use.
- Reminder time parsing only understands simple "in X minutes/hours"
  phrasing — extend with a proper date/time parser for "remind me at 5pm."
- Free-tier LLM providers (Groq, OpenRouter) have rate limits — fine for
  personal use, not built for heavy/production traffic.
- Window switching can't cross virtual desktops — a genuine Windows
  restriction, not a bug in the code.
- No authentication/access control — anyone with mic access to your
  machine can issue commands, including (confirmed) shutdown.