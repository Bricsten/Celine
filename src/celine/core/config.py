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

# --- Voice output (offline text-to-speech only) --------------------------
# Speech is optional and off by default. This milestone adds spoken replies
# only: no microphone, speech recognition, wake word, or background listening.
# SAPI rate is an integer from -10 (slowest) to 10 (fastest); 0 is normal.
VOICE_ENABLED = False
VOICE_ENGINE = "windows_sapi"
VOICE_RATE = 0
VOICE_VOLUME = 100
# Celine is written for a British female voice. If that locale is not
# installed, the layer falls back honestly rather than misreporting the voice.
VOICE_PREFERRED_LOCALE = "en-GB"
VOICE_FALLBACK_LOCALE = "en-US"
VOICE_PREFER_FEMALE = True
