"""Speech-engine boundary types shared by Celine's voice layer.

A speech engine is a thin, replaceable adapter around one offline TTS
technology. The rest of Celine only sees ``VoiceInfo`` metadata and the small
``SpeechEngine`` protocol below, so engines can be faked in tests without
touching real audio hardware.
"""

from dataclasses import dataclass
from typing import Protocol


class VoiceError(Exception):
    """A recoverable speech failure (engine, voice selection, or playback)."""


@dataclass(frozen=True)
class VoiceInfo:
    """One voice offered by an engine, using engine-neutral terminology."""

    name: str
    locale: str
    gender: str
    engine_voice_id: str


class SpeechEngine(Protocol):
    """The minimal surface the voice layer needs from a TTS backend."""

    name: str

    def available(self) -> bool:
        """Return True when the engine can attempt playback."""

    def list_voices(self) -> list[VoiceInfo]:
        """Return the voices the engine can offer (possibly empty)."""

    def speak(
        self,
        text: str,
        *,
        rate: int,
        volume: int,
        voice_id: str | None,
    ) -> None:
        """Play text synchronously; raise VoiceError on failure."""

    def stop(self) -> None:
        """Request that any current playback stop."""

    def shutdown(self) -> None:
        """Release engine resources. Must not raise."""
