"""Safe, read-only microphone diagnostics for Celine.

``/mic-test`` records one bounded clip, prints privacy-safe level statistics and
the transcript, and *never* hands the text to the assistant, executes a tool, or
saves audio unless the user explicitly opts in. Nothing here listens in the
background or changes Windows microphone settings.
"""

import time
import wave
from pathlib import Path

from celine.core import config
from celine.voice.input import microphone
from celine.voice.input.push_to_talk import _REASON_MESSAGES

__all__ = ["run_mic_test", "run_mic_devices", "save_fixture"]

# ``src/celine/voice/input/diagnostics.py`` -> repository root.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _read_answer(input_fn, prompt):
    try:
        return input_fn(prompt)
    except (EOFError, KeyboardInterrupt):
        return None


def device_report_lines():
    """Safe lines describing available and selected input devices."""
    devices = microphone.list_input_devices()
    lines = [f"[mic] Input devices found: {len(devices)}"]
    for device in devices:
        lines.append(
            f"[mic]   [{device['index']}] {device['name']} "
            f"({device['channels']} ch, {device['default_samplerate']} Hz)"
        )
    if not devices:
        lines.append("[mic]   (none - check Windows Sound settings)")

    info = microphone.Microphone().device_info()
    where = "system default" if info["device"] is None else info["device"]
    lines.append(
        f"[mic] Selected: {where}  target {info['target_samplerate']} Hz  "
        f"backend {info['backend']}"
    )
    return lines


def save_fixture(recording, *, directory=None, filename=None):
    """Write one clip as a mono 16-bit WAV fixture (explicit opt-in only)."""
    base = Path(
        config.MICROPHONE_FIXTURE_DIR if directory is None else directory
    )
    if not base.is_absolute():
        base = _PROJECT_ROOT / base
    base.mkdir(parents=True, exist_ok=True)
    name = filename or time.strftime("clip-%Y%m%d-%H%M%S.wav")
    path = base / name
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(recording.samplerate)
        wav_file.writeframes(recording.pcm)
    return path


def _maybe_save_fixture(result, *, output, input_fn):
    if not config.MICROPHONE_SAVE_FIXTURES:
        return
    recording = result.recording
    if recording is None or not recording.pcm:
        return
    answer = _read_answer(
        input_fn,
        "[mic] Save this clip as a WAV fixture for model comparison? (y/N): ",
    )
    if not answer or not answer.strip().lower().startswith("y"):
        output("[mic] Not saved.")
        return
    try:
        path = save_fixture(recording)
    except Exception as exc:  # noqa: BLE001 - never crash on a save failure
        output(f"[mic] Could not save the clip ({exc.__class__.__name__}).")
        return
    output(f"[mic] Saved: {path}")
    output(
        "[mic] Fixtures are local only, git-ignored, and never uploaded. "
        "Delete the file (or the fixtures folder) any time to remove it."
    )


def run_mic_test(ptt, *, output=print, input_fn=input):
    """Record one bounded clip and report diagnostics + transcript. Never sends."""
    output(
        "[mic] Microphone diagnostics (offline; nothing is sent to the assistant)."
    )
    for line in device_report_lines():
        output(line)
    output(
        f"[mic] Capturing up to {ptt.max_seconds:.0f}s - speak normally now..."
    )
    try:
        result = ptt.capture(diagnostics=True)
    except KeyboardInterrupt:
        output("\n[mic] Cancelled.")
        return None

    if result.audio is not None:
        for line in result.audio.report_lines():
            output(line)
    else:
        output("[mic] No audio was captured.")

    if result.ok:
        output(f'[mic] Transcript: "{result.text}"')
    else:
        reason = result.reason or "unknown"
        output(
            f"[mic] No usable transcript "
            f"({_REASON_MESSAGES.get(reason, reason)})."
        )
        output(
            "[mic] Tip: if the level is low, raise the Windows input level or "
            "speak closer; Celine never changes your microphone for you."
        )

    _maybe_save_fixture(result, output=output, input_fn=input_fn)
    return None


def run_mic_devices(*, output=print):
    """List input devices without recording anything."""
    output("[mic] Input devices (no recording is made):")
    for line in device_report_lines():
        output(line)
    return None
