# Celine

Celine is a minimal, local AI assistant that runs entirely on your own
machine through [Ollama](https://ollama.com). She chats in the terminal,
keeps the conversation in memory, and calls tools through a fixed, safe
tool-calling architecture — currently the current time, opening and controlling
a small allowlist of Windows applications, structured Notepad writing, and
narrowly scoped Microsoft Word creation, text writing, block formatting, and
DOCX saving.

## Current milestone

**Milestone 5.2A — microphone diagnostics and accuracy.**
When a transcript looks wrong, two read-only commands help you find the cause:
`/mic-devices` lists input devices and `/mic-test` records one bounded clip and
prints privacy-safe level statistics (RMS/peak dBFS, silence, clipping, estimated
SNR, dropped frames) and a plain-language assessment, plus the transcript. Neither
command sends anything to the assistant. Capture now negotiates the device rate
(properly resampling rather than relabelling), downmixes multi-channel input to
mono, discards a short warm-up, and can optionally save one confirmed clip as a
local WAV fixture for repeatable model comparison. Celine never changes Windows
microphone settings or auto-increases gain; nothing is downloaded without your
approval.

**Milestone 5.2 — offline speech-to-text and push-to-talk input.**
Celine can now accept a spoken request from the microphone. Type `/mic`, speak
one short bounded clip, and Celine transcribes it locally (**Vosk**,
`vosk-model-small-en-gb-0.15`) and shows you the text; it reaches the assistant
only after you confirm it. You can re-record or cancel, an empty transcript is
discarded, and typed input keeps working exactly as before. Microphone input is
off by default (`MICROPHONE_ENABLED = False`), there is no wake word and no
background listening, and nothing is uploaded: recognition is entirely offline.

**Milestone 5.1B — natural British female voice.**
Celine now speaks her final replies with an offline neural British female voice
(**Piper**, `en_GB-cori-medium`) instead of the robotic Microsoft Zira SAPI
voice. Speech stays entirely local, only the final user-facing reply is spoken,
and the existing Windows SAPI engine remains as an explicit fallback. There is
no microphone input, speech recognition, wake word, or background listening.
The neural engine is optional; if it is unavailable Celine falls back honestly
and never describes an American voice as British.

**Milestone 5.1 — offline voice output (text-to-speech only).**
Celine can speak her final replies aloud through the Windows SAPI voice using
the already-installed `pywin32` dependency. Speech stays local and only the
final assistant reply is spoken: never tool arguments, raw JSON, internal
reasoning, or diagnostics.

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

Celine speaks her final reply with an offline neural British female voice
(**Piper**, `en_GB-cori-medium`) and plays it through the Windows standard
library. Everything runs locally; there is no network access while speaking.
The built-in Windows SAPI voice remains as an explicit fallback.

The engine is chosen in `src/celine/core/config.py`:

```python
VOICE_ENABLED = True
VOICE_ENGINE = "piper"             # "piper" (neural) or "windows_sapi"
VOICE_RATE = 0                     # -10 (slow) .. 10 (fast), 0 normal
VOICE_VOLUME = 100                 # 0 .. 100
VOICE_PREFERRED_LOCALE = "en-GB"   # desired British female voice
VOICE_FALLBACK_LOCALE = "en-US"
VOICE_PREFER_FEMALE = True
VOICE_PIPER_MODEL = "models/piper/en_GB-cori-medium.onnx"  # trusted path
VOICE_PIPER_VOICE = "en_GB-cori-medium"
VOICE_PIPER_GENDER = "Female"
VOICE_ALLOW_FALLBACK = True        # use SAPI if Piper is unavailable
VOICE_FALLBACK_ENGINE = "windows_sapi"
```

The model path is trusted local configuration and is never supplied by the
model. Relative paths resolve against the project root, so run Celine from the
project root:

```powershell
python run.py
```

Celine prints each reply and speaks it. The first spoken reply prints one
`[voice]` line describing the voice actually used:

```
[voice] using en-GB Female voice 'en_GB-cori-medium'
```

If Piper cannot be used (dependency or model missing), Celine falls back to the
installed SAPI voice and says so honestly:

```
[voice] en-GB voice unavailable; using fallback en-US Female voice 'Microsoft Zira Desktop'
```

Set `VOICE_ALLOW_FALLBACK = False` to stay silent instead of falling back. An
American fallback voice is never described as British.

### Installing the neural voice

The neural engine is optional and not part of the core `requirements.txt`.
Install it once with:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-voice.txt
.venv\Scripts\python.exe -m piper.download_voices en_GB-cori-medium --download-dir models/piper
```

This adds `piper-tts` (~34 MB) and `onnxruntime` (~15 MB + numpy), and downloads
the `en_GB-cori-medium` voice (~64 MB) from the official `rhasspy/piper-voices`
collection. The model directory is git-ignored.

### Voice performance on this laptop (CPU-only)

- Model load: a one-time ~6 seconds on the first spoken reply; the model then
  stays resident and is not reloaded per reply.
- Synthesis: about 265 characters/second (19 chars in 0.13 s, 112 chars in
  0.42 s, 353 chars in 1.30 s) — roughly 16x faster than real time.
- Playback: synchronous (Celine finishes speaking before the next prompt),
  ~2 s for a short sentence.
- Memory: about +90 MB while the model is resident, released on shutdown.

To add a genuine British SAPI voice as well, open **Settings → Time & language
→ Speech → Voices → Add voices** and install an English (United Kingdom)
voice; the SAPI fallback will then use it automatically.

## Microphone input (offline speech-to-text, opt-in)

Celine can transcribe one spoken request locally and treat it like typed input.
This is off by default. Enable it in `src/celine/core/config.py`:

```python
MICROPHONE_ENABLED = False            # set True to allow /mic
MICROPHONE_COMMANDS = ("/mic",)       # typed command that starts a recording
MICROPHONE_DIAGNOSTICS = True         # allow /mic-test and /mic-devices
MICROPHONE_TEST_COMMAND = "/mic-test"
MICROPHONE_DEVICES_COMMAND = "/mic-devices"
MICROPHONE_SAMPLE_RATE = 16000
MICROPHONE_CHANNELS = 1
MICROPHONE_MAX_SECONDS = 6            # hard ceiling per recording
MICROPHONE_WARMUP_SECONDS = 0.15      # discard device startup artefacts
MICROPHONE_DEVICE = None              # None = system default input device
STT_ENGINE = "vosk"
STT_VOSK_MODEL = "models/stt/vosk-model-small-en-gb-0.15"  # trusted path
STT_VOSK_LOCALE = "en-GB"
STT_VOCABULARY = []                   # optional bias toward expected words
STT_MIN_CHARS = 2                     # shorter transcripts are treated as empty
MICROPHONE_SAVE_FIXTURES = False      # opt-in WAV fixtures for model comparison
MICROPHONE_FIXTURE_DIR = "models/stt/fixtures"
```

With it enabled, type `/mic` at the prompt:

```text
You: /mic
[mic] Recording for up to 6s - please speak now.
[mic] You said: "open notepad"
[mic] [Enter] send, 'r' record again, 'c' cancel:
```

Press Enter to send, `r` to record again, or `c` to cancel (press `Ctrl+C`
while recording to abort it). The microphone is opened only for the one bounded
clip and is always released afterwards. An empty or too-short transcript is
discarded without reaching Ollama. Typed input is unaffected; the model can
never supply a device or model path.

Install the optional speech-to-text dependency and model once:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-stt.txt
Invoke-WebRequest https://alphacephei.com/vosk/models/vosk-model-small-en-gb-0.15.zip -OutFile stt.zip
Expand-Archive stt.zip -DestinationPath models/stt
Remove-Item stt.zip
```

This adds `vosk` (~14 MB, with `cffi`, `tqdm`, `srt`, `websockets`) and
`sounddevice` (~1 MB, bundled PortAudio) and downloads the British English
model (~43 MB). The model directory is git-ignored. If Vosk or the model is
missing, `/mic` reports the problem and Celine keeps working with typed input.

### Microphone diagnostics and accuracy

When a transcript looks wrong, `MICROPHONE_ENABLED = True` also unlocks two
read-only commands. Neither command sends anything to the assistant, runs a
tool, or saves audio unless you explicitly opt in:

```text
You: /mic-devices   # list input devices, record nothing
You: /mic-test      # record one bounded clip and report its signal + transcript
```

`/mic-test` captures up to `MICROPHONE_MAX_SECONDS`, prints privacy-safe level
statistics (duration, rate/channel conversion, RMS/peak dBFS, silence %, clipping
%, estimated SNR, dropped frames) and a plain-language assessment such as
"mostly silence", "high background noise", "clipped", "quiet but present", or
"valid audio for recognition", followed by the transcript. The text is shown for
diagnosis only and is never executed.

Capture always negotiates against the device: the recogniser rate (16 kHz) is
used when the device supports it, otherwise the device's native rate is captured
and **properly resampled** (never merely relabelled), and multi-channel input is
downmixed to mono. To build a repeatable comparison set, set
`MICROPHONE_SAVE_FIXTURES = True` and answer `y` at the per-clip prompt; Celine
then writes one mono 16-bit WAV per confirmed clip into `MICROPHONE_FIXTURE_DIR`
(git-ignored, local only, never uploaded). Delete the files or the folder any
time to remove them.

Celine never changes Windows microphone settings or auto-increases gain; if the
level is low, raise the Windows input level yourself and re-run `/mic-test`.
Accuracy is limited by the small generic Vosk model — a larger English model
trades disk and CPU for fewer errors, but nothing is downloaded without your
approval.

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
      piper_engine.py  # offline neural Piper engine (ONNX + winsound)
      windows_sapi.py  # offline Windows SAPI engine (pywin32/COM)
    input/
      __init__.py      # Recording + Recorder/Transcriber protocols
      audio.py         # PCM convert/downmix/resample + safe level statistics
      microphone.py    # bounded sounddevice capture (no background listening)
      transcription.py # offline Vosk speech recognition
      push_to_talk.py  # record once, transcribe, confirm before sending
      diagnostics.py   # read-only /mic-test and /mic-devices (opt-in, no sending)
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
  test_piper_engine.py
  test_voice_input.py
  test_voice_audio.py
  test_voice_diagnostics.py
run.py                 # launcher: puts src/ on the path, starts main
pytest.ini             # test config (src/ on path, tests/ folder)
requirements.txt       # core dependencies
requirements-voice.txt # optional neural voice dependencies (Piper)
requirements-stt.txt   # optional offline speech-to-text dependencies (Vosk)
```

### Execution flow

1. `run.py` starts `main.main()` (src/ on `sys.path`).
2. `main.py` builds an `Assistant(chat=ollama_client.chat)` and loops on
   user input. Typing a microphone command (e.g. `/mic`) records one bounded
   clip, transcribes it locally, and — after confirmation — feeds the text
   through the exact same path as typed input.
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
- Optional offline voice output: Celine speaks her final reply with a neural
  British female voice (Piper, `en_GB-cori-medium`), falling back to the Windows
  SAPI voice when Piper is unavailable. Only the final user-facing reply is
  spoken; there is no wake word or background listening.
- Optional offline push-to-talk input: type `/mic` to record one bounded clip
  that is transcribed locally (Vosk) and shown for confirmation before it is
  used. Off by default; typed input is unaffected.
- Read-only microphone diagnostics: `/mic-devices` lists input devices and
  `/mic-test` records one bounded clip and reports privacy-safe level statistics
  plus the transcript, without sending anything or changing Windows settings.
  Capture negotiates the device rate (properly resampling, never relabelling),
  downmixes to mono, and rejects empty/short transcripts before Ollama.
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
- Voice is not hands-free: microphone input is opt-in and push-to-talk only —
  one bounded clip per request, started by typing a command (`/mic` to capture,
  `/mic-devices`/`/mic-test` for read-only diagnostics). There is no wake
  word, no continuous or background listening, and no speech command is acted
  on without explicit confirmation. Speech recognition is English-only and
  offline. Celine never changes Windows microphone settings or gain. The neural
  Piper voice requires a one-time optional dependency and
  model download (see "Voice output"). If Piper is unavailable, Celine may fall
  back to the installed en-US SAPI voice and always says so honestly.
- No persistent memory or database
- Chat history is lost when the program exits
- Privacy: the current chat runs locally through Ollama, but Celine
  describes privacy based on active capabilities — future internet-using
  tools (e.g. web search) would change that picture
