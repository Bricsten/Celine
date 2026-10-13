# Celine

Celine is a minimal, local AI assistant that runs entirely on your own
machine through [Ollama](https://ollama.com). She chats in the terminal,
keeps the conversation in memory, and calls tools through a fixed, safe
tool-calling architecture — currently the current time, opening and controlling
a small allowlist of Windows applications, structured Notepad writing, and
narrowly scoped Microsoft Word creation, text writing, block formatting, and
DOCX saving.

## Current milestone

**Milestone 5.1 — offline voice output (text-to-speech only).**
Celine can now speak her final replies aloud through the Windows SAPI voice
using the already-installed `pywin32` dependency. Speech is **off by default**
and stays entirely local. Only the final assistant reply is spoken: never
tool arguments, raw JSON, internal reasoning, or diagnostics. There is no
microphone input, speech recognition, wake word, or background listening in
this milestone.

A British (`en-GB`) female voice is **not installed on this machine** — only
Microsoft David (en-US, male) and Microsoft Zira (en-US, female) are
available. Celine therefore falls back to an honest choice (currently Zira)
and prints a one-line `[voice]` note saying the British voice was unavailable,
rather than misrepresenting the voice.

**Milestone 4.3H — local performance and reliability optimisation.**
Celine's requests bound output generation with a smaller `num_predict` cap and
ask the model for brief confirmations, which cuts the long trailing replies
that dominated interactive latency on CPU. The model is kept resident with
`keep_alive` so an idle gap no longer forces a cold reload. The system prompt
drops duplicated tool enumeration while keeping every safety and honesty rule.
Conversation history is sanitised before every request: a tool request without
its matching tool results is removed so a half-finished exchange can never
reach Ollama, while the current user request is always retained. No new
capabilities, paths, automation, or security relaxations were introduced.

**Milestone 4.3G — Word tool selection and session reliability.**
Celine now treats registered action tools as the authority on external app
state: restarting the terminal does not imply that Word or its document was
closed. Explicit save requests go directly to `save_word_document` without
asking the user to reconfirm Word state or creating another document.

Ollama requests use deterministic, bounded generation and explicitly disable
thinking for this tool-driven assistant. The 120-second HTTP deadline remains
unchanged. Timeouts are reported separately from Word failures, never trigger
automatic mutation retries, and retain any already-produced sanitized tool
result. Prior conversation history is bounded by complete turns and a fixed
character budget to prevent indefinite context growth.

**Milestone 4.3F — safe Microsoft Word formatting (phase 1).**
Celine can add a new isolated Word block using fixed, code-owned style and
alignment presets. Supported styles are `normal`, `heading_1`, `heading_2`,
and `title`; supported alignments are `left`, `center`, `right`, and `justify`.
Formatting never targets existing text and does not expose Word COM property
or method names to the model.

Examples include `Add a centred heading that says My Internship Report.`,
`Add a heading that says Results.`, and `Add a left-aligned paragraph
explaining artificial intelligence.` Saving remains a separate tool action.

**Milestone 4.3E — safe Microsoft Word save/save as.**
Celine can save the single safely targeted Word document as DOCX in one of
three logical folders: Documents, Desktop, or Downloads. Python resolves the
actual location through Windows Known Folder APIs. The model supplies only a
validated filename and logical folder; it cannot supply a filesystem path or
Word file-format value.

Supported examples include `Save this as Letter.docx in Documents.`, `Save
this as Notes on Desktop.`, and `Open Word, write 'Hello', and save it as
Hello.docx in Documents.` The last example uses the fixed sequence of launch,
blank-document creation, text writing, and saving. Saving uses one fixed DOCX
`SaveAs2` operation and refuses an existing destination rather than
overwriting or automatically renaming it.

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
[perf] ollama_call_1=6.42s round=1 messages=2 approx_message_chars=4200 tools=8 approx_tool_chars=3400 after_tool_result=false timed_out=false
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

The metadata contains counts and approximate serialized sizes only. It never
prints user messages or document contents.

Tool debug logging works the same way: set `TOOL_LOG = True` to print
`[tool] open_application ...` request/result lines (never model
reasoning).

## Voice output

Voice output uses the offline Windows SAPI voice through the existing
`pywin32` dependency. No extra packages or model downloads are required.
Speech is disabled by default.

Enable it in `src/celine/core/config.py`:

```python
VOICE_ENABLED = True
VOICE_ENGINE = "windows_sapi"      # only this engine exists in 5.1
VOICE_RATE = 0                     # SAPI: -10 (slow) .. 10 (fast)
VOICE_VOLUME = 100                 # 0 .. 100
VOICE_PREFERRED_LOCALE = "en-GB"   # desired British female voice
VOICE_FALLBACK_LOCALE = "en-US"    # used when no en-GB voice is installed
VOICE_PREFER_FEMALE = True
```

Then run Celine normally:

```powershell
python run.py
```

Celine prints each reply and speaks it. The first spoken reply prints one
`[voice]` line describing the voice actually used, for example:

```
[voice] en-GB voice unavailable; using fallback en-US Female voice 'Microsoft Zira Desktop'
```

To add a real British voice on Windows 11, open **Settings → Time & language
→ Speech → Voices → Add voices**, install an English (United Kingdom) voice,
then restart Celine. Celine will pick it up automatically and the fallback
note will disappear. The voice is chosen by locale and gender; the preferred
voice is never misrepresented as British if the British one is absent.

Playback is synchronous: Celine finishes speaking before the next prompt
appears. On this machine the fixed startup cost is a few milliseconds after
the first use, and a short sentence plays in roughly five seconds.

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

To measure planning latency with Ollama's native timing fields (prefill,
generation, tokens per second) without dispatching any tool, run:

```powershell
python scripts/benchmark_latency.py baseline
```

The optional label argument makes before/after runs easy to compare.

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
  voice/
    __init__.py        # public voice API (text-to-speech only)
    tts.py             # engine/voice selection + safe speak orchestration
    engines/
      __init__.py      # VoiceInfo + SpeechEngine protocol (shared boundary)
      windows_sapi.py  # offline Windows SAPI engine (pywin32/COM)
  tools/
    system_time.py     # get_current_time implementation
    windows_apps.py    # open_application allowlist + launcher (no shell)
    window_control.py  # fixed matching + approved window actions
    text_input.py      # control-scoped, Notepad-only text append
    registry.py        # fixed whitelist, schemas, validation
    word/
      __init__.py      # intended public Word tool export
      adapter.py       # private fixed COM target + bounded range operations
      folders.py       # fixed Windows Known Folder resolution
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
  test_word_save.py
  test_word_formatting.py
  test_agent_tool_selection.py
  test_voice.py
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
- Eight tools: `get_current_time()` (no arguments),
  `open_application(name)`, `control_window(application, action)`,
  `write_text(application, text, mode)`, `write_word_text(text, mode)`,
  `create_word_document()`, `add_word_block(text, style, alignment)`, and
  `save_word_document(filename, folder)`
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
- Word block formatting inserts one standalone block at the document end with
  fixed Aptos presets: normal (12 pt, not bold), heading 1 (18 pt, bold),
  heading 2 (14 pt, bold), or title (22 pt, bold). Alignment is selected from
  left, centre, right, or justify. Bounded `Range` objects restrict formatting
  to the inserted block, and one neutral trailing paragraph prevents later
  ordinary text from inheriting heading formatting. No document text is read.
- Word document creation is allowed only when Word is already running safely
  with zero open documents. It creates one blank unsaved document with one
  fixed `Documents.Add()` call, then confirms the trusted application and
  document window ownership before reporting success.
- Word saving is DOCX-only and resolves `documents`, `desktop`, or `downloads`
  through fixed Windows Known Folder identifiers. Filename validation rejects
  paths, traversal, illegal/control characters, reserved Windows names, other
  extensions, and names over 120 characters. Existing files are never
  overwritten or automatically renamed; success requires the expected exact
  path to exist after the fixed save operation.
- App names are trimmed/lowercased and alias-mapped; anything outside
  the allowlist (arbitrary strings, paths, commands) is rejected
- Unknown tools rejected safely; tool arguments validated
- `MAX_TOOL_ROUNDS` prevents infinite tool loops
- Optional offline voice output: Celine can speak her final reply through the
  Windows SAPI voice (off by default). Only the final user-facing reply is
  spoken; there is no microphone, speech recognition, wake word, or background
  listening.
- Automated tests that need no running Ollama server (`pytest`)

## Current limitations

- Window control applies only to visible top-level windows matched by fixed,
  code-owned rules for the four approved applications
- No typing into applications other than Notepad and the narrowly scoped Word
  capability; no clicking, global keyboard/mouse automation, keyboard
  shortcuts, screenshots, or arbitrary window control
- Word must already be running for creation, writing, or saving. Celine refuses
  ambiguous multiple-document/window states, read-only documents, protected
  documents, disabled windows, and Protected View.
- No arbitrary save folders, overwrite, automatic rename, file deletion,
  templates, file opening, saved-file reading, PDF export, existing-text
  formatting, arbitrary font choices, replacement, arbitrary creation
  options, selection manipulation, macros,
  VBA, or arbitrary COM operations
- No arbitrary titles, regular expressions, process IDs, or window handles
- No process termination or force-killing
- No other file access, shell/PowerShell execution, or web search
- Voice is text-to-speech output only: no speech-to-text, microphone input,
  wake word, or background listening. No British (`en-GB`) voice is installed
  on this machine, so Celine uses an honest en-US female fallback until one is
  added in Windows Settings.
- No persistent memory or database
- Chat history is lost when the program exits
- Privacy: the current chat runs locally through Ollama, but Celine
  describes privacy based on active capabilities — future internet-using
  tools (e.g. web search) would change that picture
