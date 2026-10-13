"""Controlled push-to-talk: one recording, one transcript, explicit confirm.

This is the only place that ties a microphone to speech recognition. It records
at most one bounded clip when asked, transcribes it locally, shows the text, and
waits for the user to confirm before the text is ever handed to the assistant.
The user can always re-record or cancel, and an empty transcript is discarded
without reaching Ollama.

Nothing here listens continuously, reacts to a wake word, or acts on the model:
the microphone is opened only for the length of one requested clip, which is
hard-bounded by ``MICROPHONE_MAX_SECONDS``.
"""

from dataclasses import dataclass

from celine.core import config
from celine.voice.input import InputError, audio
from celine.voice.input.microphone import Microphone
from celine.voice.input.transcription import VoskTranscriber

__all__ = [
    "PushToTalk",
    "PushToTalkResult",
    "build_recorder",
    "build_transcriber",
    "run_push_to_talk",
]


_REASON_MESSAGES = {
    "disabled": (
        "Microphone input is off. Set MICROPHONE_ENABLED = True to use /mic."
    ),
    "closed": "Microphone input is closed.",
    "setup_failed": "Microphone setup failed.",
    "no_microphone": "No microphone was found.",
    "no_speech_model": "The offline speech model was not found (see README).",
    "recording_failed": "Recording failed.",
    "no_audio": "I didn't hear anything.",
    "transcription_failed": "Speech recognition failed.",
    "empty_transcript": "I couldn't make out any words.",
}


@dataclass(frozen=True)
class PushToTalkResult:
    """Outcome of one capture attempt, including an honest failure reason."""

    ok: bool
    text: str = ""
    reason: str | None = None
    seconds: float = 0.0
    audio: "audio.AudioStats | None" = None
    recording: "object | None" = None


def build_recorder(name):
    """Construct one known microphone backend by name. Unknown names fail."""
    if name in (None, "sounddevice"):
        return Microphone()
    raise InputError(f"unknown microphone backend: {name!r}")


def build_transcriber(name):
    """Construct one known speech-to-text backend by name. Unknown fails."""
    if name in (None, "vosk"):
        return VoskTranscriber()
    raise InputError(f"unknown speech-to-text backend: {name!r}")


class PushToTalk:
    """Owns one recorder and one transcriber for a single bounded capture."""

    def __init__(
        self,
        *,
        recorder=None,
        transcriber=None,
        enabled=None,
        max_seconds=None,
        min_chars=None,
    ):
        requested = (
            config.MICROPHONE_ENABLED if enabled is None else bool(enabled)
        )
        self.requested = requested
        self.enabled = requested
        self._recorder = recorder
        self._transcriber = transcriber
        self.max_seconds = float(
            config.MICROPHONE_MAX_SECONDS if max_seconds is None else max_seconds
        )
        self._min_chars = int(
            config.STT_MIN_CHARS if min_chars is None else min_chars
        )
        self._closed = False

    def _ensure_backends(self):
        if self._recorder is None:
            self._recorder = build_recorder("sounddevice")
        if self._transcriber is None:
            self._transcriber = build_transcriber(config.STT_ENGINE)

    def _fail(self, reason, seconds=0.0, audio_stats=None, recording=None):
        return PushToTalkResult(False, "", reason, seconds, audio_stats, recording)

    def capture(self, *, stop=None, diagnostics=False):
        """Record once, transcribe locally, and return the text. Never raises.

        With ``diagnostics`` the result also carries privacy-safe
        :class:`~celine.voice.input.audio.AudioStats` (level, silence, clipping,
        noise floor) and the raw :class:`Recording`, so ``/mic-test`` can report
        on the signal. Recordings are never written to disk here.
        """
        if self._closed:
            return self._fail("closed")
        if not self.enabled:
            return self._fail("disabled")

        try:
            self._ensure_backends()
        except Exception:  # noqa: BLE001 - missing backend degrades to silence
            return self._fail("setup_failed")

        if not self._recorder.available():
            return self._fail("no_microphone")
        if not self._transcriber.available():
            return self._fail("no_speech_model")

        try:
            recording = self._recorder.record(
                max_seconds=self.max_seconds, stop=stop
            )
        except InputError:
            return self._fail("recording_failed")
        except Exception:  # noqa: BLE001 - report, do not crash Celine
            return self._fail("recording_failed")

        stats = audio.analyse(recording) if diagnostics else None
        kept = recording if diagnostics else None

        if not recording.pcm:
            return self._fail("no_audio", recording.seconds, stats, kept)

        try:
            text = self._transcriber.transcribe(
                recording.pcm, samplerate=recording.samplerate
            )
        except InputError:
            return self._fail("transcription_failed", recording.seconds, stats, kept)
        except Exception:  # noqa: BLE001 - report, do not crash Celine
            return self._fail("transcription_failed", recording.seconds, stats, kept)

        text = (text or "").strip()
        if len(text) < max(1, self._min_chars):
            return self._fail("empty_transcript", recording.seconds, stats, kept)
        return PushToTalkResult(True, text, None, recording.seconds, stats, kept)

    def shutdown(self):
        """Release recorder and transcriber. Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        for backend in (self._recorder, self._transcriber):
            if backend is not None:
                try:
                    backend.close()
                except Exception:  # noqa: BLE001 - shutdown must never raise
                    pass


def _read_line(input_fn, prompt):
    try:
        return input_fn(prompt)
    except (EOFError, KeyboardInterrupt):
        return None


def run_push_to_talk(ptt, *, input_fn=input, output=print):
    """Terminal push-to-talk flow; returns confirmed text or ``None``.

    Records one bounded clip, shows the transcript, and only returns text the
    user explicitly accepts. ``r`` records again, ``c`` cancels.
    """
    if not ptt.enabled:
        output(f"[mic] {_REASON_MESSAGES['disabled']}")
        return None

    while True:
        output(
            f"[mic] Recording for up to {ptt.max_seconds:.0f}s "
            "- please speak now."
        )
        try:
            result = ptt.capture()
        except KeyboardInterrupt:
            output("\n[mic] Cancelled.")
            return None

        if not result.ok:
            output(f"[mic] {_REASON_MESSAGES.get(result.reason, 'No speech captured.')}")
            return None

        output(f'[mic] You said: "{result.text}"')
        answer = _read_line(
            input_fn, "[mic] [Enter] send, 'r' record again, 'c' cancel: "
        )
        if answer is None:
            output("[mic] Cancelled.")
            return None
        answer = answer.strip().lower()
        if answer == "r":
            continue
        if answer in ("c", "q", "quit", "exit"):
            output("[mic] Cancelled.")
            return None
        return result.text
