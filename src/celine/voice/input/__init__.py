"""Celine's offline microphone input boundary types.

A recorder captures one short, bounded clip of raw audio; a transcriber turns
that clip into text locally. The rest of Celine only sees the small protocols
below, so both can be faked in tests without touching real audio hardware or a
real speech model.

This package never runs a shell command, never opens the network, and never
listens in the background: a recording only happens when ``PushToTalk`` is
asked to capture one.
"""

from dataclasses import dataclass
from typing import Protocol


class InputError(Exception):
    """A recoverable microphone or speech-to-text failure."""


@dataclass(frozen=True)
class Recording:
    """One captured clip of raw mono PCM audio (16-bit signed little-endian).

    ``source_samplerate`` records the device rate actually captured when it
    differs from ``samplerate`` (the recogniser rate after conversion), so
    diagnostics can be honest about any resampling.
    """

    pcm: bytes
    samplerate: int
    seconds: float
    truncated: bool = False
    channels: int = 1
    source_samplerate: int | None = None
    overflowed: int = 0


class Recorder(Protocol):
    """The minimal surface the input layer needs from a microphone backend."""

    name: str

    def available(self) -> bool:
        """Return True when the recorder can attempt to capture audio."""

    def record(self, *, max_seconds: float, stop=None) -> Recording:
        """Capture one bounded clip; stop early when ``stop`` signals it."""

    def close(self) -> None:
        """Release the device. Must not raise."""


class Transcriber(Protocol):
    """The minimal surface the input layer needs from a speech-to-text backend."""

    name: str

    def available(self) -> bool:
        """Return True when transcription can be attempted."""

    def transcribe(self, pcm: bytes, *, samplerate: int) -> str:
        """Return the recognized text for a PCM clip (possibly empty)."""

    def close(self) -> None:
        """Release the model. Must not raise."""


__all__ = [
    "InputError",
    "Recording",
    "Recorder",
    "Transcriber",
    "AudioStats",
    "Microphone",
    "VoskTranscriber",
    "PushToTalk",
    "PushToTalkResult",
    "build_recorder",
    "build_transcriber",
    "run_push_to_talk",
    "run_mic_test",
    "run_mic_devices",
    "analyse",
]

# Imported last so the boundary types above exist before submodules use them.
from celine.voice.input.audio import AudioStats, analyse  # noqa: E402
from celine.voice.input.microphone import (  # noqa: E402
    Microphone,
    list_input_devices,
)
from celine.voice.input.transcription import VoskTranscriber  # noqa: E402
from celine.voice.input.push_to_talk import (  # noqa: E402
    PushToTalk,
    PushToTalkResult,
    build_recorder,
    build_transcriber,
    run_push_to_talk,
)
from celine.voice.input.diagnostics import (  # noqa: E402
    run_mic_devices,
    run_mic_test,
)
