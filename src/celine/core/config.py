"""Simple constants used across the whole project."""

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/chat"
MODEL = "qwen3:4b-instruct"
REQUEST_TIMEOUT = 120
OLLAMA_TEMPERATURE = 0
# Bound the worst-case generation length. Routine Celine replies and tool
# calls are far shorter than this, so it only caps a runaway response while
# leaving normal traffic unaffected.
OLLAMA_NUM_PREDICT = 128
# Keep the model resident between interactive requests. Without this, an
# idle gap makes the next request pay a fresh model load on this hardware.
OLLAMA_KEEP_ALIVE = "30m"

# Bound prior conversational context while preserving complete recent turns.
# The current user turn is always retained in full.
MAX_HISTORY_TURNS = 6
MAX_HISTORY_CHARS = 4_000

# Safety limit on how many tool rounds one user message may trigger.
MAX_TOOL_ROUNDS = 4

# Optional performance logging (off by default). Set to True to print
# concise timing info for each request.
PERF_LOG = False

# Optional tool debug logging (off by default). Set to True to print
# [tool] lines for tool requests. No model reasoning is logged.
TOOL_LOG = False

# --- Voice output (offline text-to-speech) -------------------------------
# Speech output is optional. The neural Piper engine gives Celine a natural
# British female voice; the built-in Windows SAPI engine remains available as
# an explicit fallback. Microphone input is separate and opt-in (see the
# "Microphone input" section below).
VOICE_ENABLED = True
VOICE_ENGINE = "piper"
# SAPI-style rate: an integer from -10 (slowest) to 10 (fastest); 0 is normal.
# For Piper this is mapped to a length scale; volume is a percentage 0..100.
VOICE_RATE = 0
VOICE_VOLUME = 100
# Celine is written for a British female voice. If that locale is not
# available, the layer falls back honestly rather than misreporting the voice.
VOICE_PREFERRED_LOCALE = "en-GB"
VOICE_FALLBACK_LOCALE = "en-US"
VOICE_PREFER_FEMALE = True
# Neural Piper voice. The path is trusted local configuration (relative paths
# resolve against the project root), never anything the model can supply.
VOICE_PIPER_MODEL = "models/piper/en_GB-cori-medium.onnx"
VOICE_PIPER_VOICE = "en_GB-cori-medium"
VOICE_PIPER_GENDER = "Female"
# When Piper is unavailable (missing dependency or model), Celine may speak
# with the built-in Windows SAPI engine instead. The announcement stays honest
# about the voice actually used, so an American fallback is never called
# British. Set to False to stay silent instead of falling back.
VOICE_ALLOW_FALLBACK = True
VOICE_FALLBACK_ENGINE = "windows_sapi"

# --- Microphone input (offline speech-to-text, opt-in) -------------------
# Push-to-talk microphone input is off by default and must be enabled
# explicitly. Speech is transcribed locally (Vosk); nothing is sent anywhere,
# and typed input keeps working exactly as before. There is no wake word and
# no continuous or background listening: a recording starts only when asked.
MICROPHONE_ENABLED = True
# Typed commands that start one recording. Typing is unaffected otherwise.
MICROPHONE_COMMANDS = ("/mic",)
# Read-only diagnostics (`/mic-test`) and device listing (`/mic-devices`).
# Both require MICROPHONE_ENABLED and never send anything to the assistant.
MICROPHONE_DIAGNOSTICS = True
MICROPHONE_TEST_COMMAND = "/mic-test"
MICROPHONE_DEVICES_COMMAND = "/mic-devices"
MICROPHONE_SAMPLE_RATE = 16000
MICROPHONE_CHANNELS = 1
# Hard ceiling on a single recording; the microphone is always released after.
# Recording runs for this long (or until Ctrl+C), then Celine transcribes it.
MICROPHONE_MAX_SECONDS = 6
# Short capture warm-up: discard this many seconds at the start of the stream so
# the first samples are not device startup artefacts. 0 disables it.
MICROPHONE_WARMUP_SECONDS = 0.15
# Optional input device index/name; None uses the system default input device.
MICROPHONE_DEVICE = None
# Offline speech-to-text. The model path is trusted local configuration and is
# never supplied by the model; relative paths resolve against the project root.
STT_ENGINE = "vosk"
STT_VOSK_MODEL = "models/stt/vosk-model-small-en-gb-0.15"
STT_VOSK_LOCALE = "en-GB"
# Optional word list to bias recognition toward expected commands. Empty means
# full, general transcription (recommended unless commands are very limited).
STT_VOCABULARY = []
# Transcripts shorter than this are treated as empty and never reach Ollama.
STT_MIN_CHARS = 2
# Off by default: when True, `/mic-test` may save one clip as a WAV fixture
# (after an explicit per-clip confirmation) for repeatable model comparison.
# Fixtures are local, git-ignored, never uploaded, and can be deleted any time.
MICROPHONE_SAVE_FIXTURES = False
MICROPHONE_FIXTURE_DIR = "models/stt/fixtures"
