# Celine

Celine is a minimal, local AI assistant that runs entirely on your own
machine through [Ollama](https://ollama.com). She chats in the terminal,
keeps the conversation in memory, and calls tools through a fixed, safe
tool-calling architecture — currently the current time, opening and controlling
a small allowlist of Windows applications, and Notepad-only text entry.

## Current milestone

**Milestone 4.3B — structured Notepad text operations.**
Celine can append plain Unicode text to an already-running Notepad using one
of two fixed modes: `append` or `new_line`. Notepad is located through fixed
process and window rules, then its editable child is verified through fixed UI
Automation control rules. No global keyboard input, clipboard, arbitrary
handle, PID, title, or regular expression comes from model input.

Supported examples: `Write 'Hello' in Notepad.` and `Add 'Second line' on a
new line in Notepad.` The agent can call `open_application` and then
`write_text` through the normal tool loop; `write_text` itself never opens,
reads, or saves Notepad.

## Prerequisites

- Python 3.12
- [Ollama](https://ollama.com) installed and running locally
- The model pulled: `ollama pull qwen3:4b-instruct`

## Installation

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## How to run Celine

```powershell
python run.py
```

Type your message and press Enter. Type `exit` or `quit` (or press
`Ctrl+C`) to close.

## Performance logging (optional, off by default)

To see where latency comes from, edit `src/celine/core/config.py`:

```python
PERF_LOG = True
```

Run Celine normally. Each request then prints concise timings (no model
reasoning is ever printed):

```
[perf] ollama_call_1=6.42s
[perf] tool:get_current_time=0.001s
[perf] ollama_call_2=4.87s
[perf] total=11.31s ollama_calls=2 tool_calls=1
```

A plain chat shows a single Ollama call:

```
[perf] ollama_call_1=6.08s
[perf] total=6.09s ollama_calls=1 tool_calls=0
```

Set `PERF_LOG = False` again to turn it off.

Tool debug logging works the same way: set `TOOL_LOG = True` to print
`[tool] open_application ...` request/result lines (never model
reasoning).

## Current architecture

```
src/celine/
  __init__.py
  main.py              # terminal entry point: input loop, shutdown
  core/
    config.py          # OLLAMA_URL, MODEL, MAX_TOOL_ROUNDS, PERF_LOG, ...
    prompts.py         # system prompt (personality vs capability rules)
    assistant.py       # history + tool-round orchestration (no HTTP)
    perf.py            # optional [perf] timing instrumentation
  llm/
    ollama_client.py   # the only module that talks to Ollama
  tools/
    system_time.py     # get_current_time implementation
    windows_apps.py    # open_application allowlist + launcher (no shell)
    window_control.py  # fixed matching + approved window actions
    text_input.py      # control-scoped, Notepad-only text append
    registry.py        # fixed whitelist, schemas, validation
tests/
  test_tool_registry.py
  test_assistant.py
  test_perf.py
  test_open_application.py
  test_window_control.py
  test_text_input.py
run.py                 # launcher: puts src/ on the path, starts main
pytest.ini             # test config (src/ on path, tests/ folder)
```

### Execution flow

1. `run.py` starts `main.main()` (src/ on `sys.path`).
2. `main.py` builds an `Assistant(chat=ollama_client.chat)` and loops on
   user input.
3. `assistant.py` appends the user message, calls the model, and — if the
   model requests a tool — validates and runs it via `registry.py`,
   appends a `role: "tool"` result, and calls the model again
   (up to `MAX_TOOL_ROUNDS`).
4. `ollama_client.py` is the only place that performs HTTP (`/api/chat`),
   translating failures into simple, named exceptions.
5. `main.py` prints Celine's reply or a friendly error.

## Current capabilities

- Local chat with `qwen3:4b-instruct` via Ollama's `/api/chat`
- In-memory conversation history (per session)
- Native tool calling with a fixed whitelist registry
- Four tools: `get_current_time()` (no arguments),
  `open_application(name)`, `control_window(application, action)`, and
  `write_text(application, text, mode)`
- The application allowlist is `notepad`, `calculator`, `word`, and
  `file_explorer`
- Approved window actions are `minimize`, `restore`, `focus`, and `close`;
  close posts a normal window-close request rather than killing a process
- Text entry is restricted to Notepad and accepts ordinary Unicode. `append`
  adds text directly at the end; `new_line` first adds one `\r\n` unless the
  document is empty. The 10,000-character limit applies to user-supplied text,
  excluding the trusted line-break prefix.
- App names are trimmed/lowercased and alias-mapped; anything outside
  the allowlist (arbitrary strings, paths, commands) is rejected
- Unknown tools rejected safely; tool arguments validated
- `MAX_TOOL_ROUNDS` prevents infinite tool loops
- Automated tests that need no running Ollama server (`pytest`)

## Current limitations

- Window control applies only to visible top-level windows matched by fixed,
  code-owned rules for the four approved applications
- No typing into Word or other applications, clicking, global keyboard/mouse
  automation, keyboard shortcuts, screenshots, or arbitrary window control
- No document saving, file opening, formatting, or unrestricted clipboard use
- No document reading, replacement, deletion, or Word typing
- No arbitrary titles, regular expressions, process IDs, or window handles
- No process termination or force-killing
- No file access, shell/PowerShell execution, or web search
- No voice, persistent memory, or database
- Chat history is lost when the program exits
- Privacy: the current chat runs locally through Ollama, but Celine
  describes privacy based on active capabilities — future internet-using
  tools (e.g. web search) would change that picture
