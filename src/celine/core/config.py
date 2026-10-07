"""Simple constants used across the whole project."""

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/chat"
MODEL = "qwen3:4b-instruct"
REQUEST_TIMEOUT = 120

# Safety limit on how many tool rounds one user message may trigger.
MAX_TOOL_ROUNDS = 3

# Optional performance logging (off by default). Set to True to print
# concise timing info for each request.
PERF_LOG = False

# Optional tool debug logging (off by default). Set to True to print
# [tool] lines for tool requests. No model reasoning is logged.
TOOL_LOG = False

