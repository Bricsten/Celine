# Celine

Celine is a minimal, local AI assistant that runs entirely on your own
machine through [Ollama](https://ollama.com). She chats in the terminal,
keeps the conversation in memory, and calls tools through a fixed, safe
tool-calling architecture — currently the current time, opening and controlling
a small allowlist of Windows applications, structured Notepad writing, and
narrowly scoped Microsoft Word text writing.

## Current milestone

**Milestone 4.3D — safe Microsoft Word document creation.**
Celine can create exactly one blank unsaved document in an already-running,
unambiguous Word instance when no document is open. Creation, launching, and
writing remain separate fixed tools. The creation tool accepts no paths,
templates, filenames, document names, or COM operations from the model.

Supported examples include `Create a blank Word document.`, `Open Word and
create a blank document.`, and `Open Word and write 'Hello from Celine.'.` For
the last example, the agent can launch Word, create one blank document if Word
has none, and then call `write_word_text`. `Documents.Add()` is attempted at
most once, and the result must pass document-count, editability, protection,
window-count, and triple-HWND confirmation before success is reported. After
confirmation, the exact verified document window is activated once so it is
shown instead of Word's Start screen.

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

For read-only Word integration diagnostics, run:

```powershell
python scripts/diagnose_word.py
```

This developer utility is not registered as a Celine tool. It reports trusted
window and COM targeting metadata without reading or modifying document text.

To inspect Qwen's proposed tool choices without executing any tools or touching
applications, run the optional planning probe:

```powershell
python scripts/probe_tool_selection.py
```

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
    word/
      __init__.py      # intended public Word tool export
      adapter.py       # private fixed COM target + range operations
      tool.py          # public validation, safe results, metadata logs
tests/
  test_tool_registry.py
  test_assistant.py
  test_perf.py
  test_open_application.py
  test_window_control.py
  test_text_input.py
  test_word_adapter.py
  test_word_tool.py
  test_agent_tool_selection.py
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
- Six tools: `get_current_time()` (no arguments),
  `open_application(name)`, `control_window(application, action)`, and
  `write_text(application, text, mode)`, `write_word_text(text, mode)`, and
  `create_word_document()`
- The application allowlist is `notepad`, `calculator`, `word`, and
  `file_explorer`
- Approved window actions are `minimize`, `restore`, `focus`, and `close`;
  close posts a normal window-close request rather than killing a process
- Text entry is restricted to Notepad and accepts ordinary Unicode. `append`
  adds text directly at the end; `new_line` first adds one `\r\n` unless the
  document is empty. The 10,000-character limit applies to user-supplied text,
  excluding the trusted line-break prefix.
- Word writing accepts ordinary Unicode and is restricted to exactly one
  trusted, enabled Word window with exactly one editable document and document
  window. `append` uses a fixed document-range insertion; `new_paragraph`
  prefixes one Word paragraph mark unless the document is empty. The
  10,000-character limit applies to user-supplied text, excluding that trusted
  paragraph mark.
- Word document creation is allowed only when Word is already running safely
  with zero open documents. It creates one blank unsaved document with one
  fixed `Documents.Add()` call, then confirms the trusted application and
  document window ownership before reporting success.
- App names are trimmed/lowercased and alias-mapped; anything outside
  the allowlist (arbitrary strings, paths, commands) is rejected
- Unknown tools rejected safely; tool arguments validated
- `MAX_TOOL_ROUNDS` prevents infinite tool loops
- Automated tests that need no running Ollama server (`pytest`)

## Current limitations

- Window control applies only to visible top-level windows matched by fixed,
  code-owned rules for the four approved applications
- No typing into applications other than Notepad and the narrowly scoped Word
  capability; no clicking, global keyboard/mouse automation, keyboard
  shortcuts, screenshots, or arbitrary window control
- Word must already be running for creation or writing. Celine refuses
  ambiguous multiple-document/window states, read-only documents, protected
  documents, disabled windows, and Protected View.
- No saving, file paths, templates, file opening, content reading, formatting,
  replacement, deletion, arbitrary creation options, selection manipulation,
  macros, VBA, or arbitrary COM operations
- No arbitrary titles, regular expressions, process IDs, or window handles
- No process termination or force-killing
- No file access, shell/PowerShell execution, or web search
- No voice, persistent memory, or database
- Chat history is lost when the program exits
- Privacy: the current chat runs locally through Ollama, but Celine
  describes privacy based on active capabilities — future internet-using
  tools (e.g. web search) would change that picture
