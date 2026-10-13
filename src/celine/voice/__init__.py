"""Celine's offline voice output (text-to-speech).

This package holds the output side: spoken replies only. Microphone input lives
in the separate, opt-in ``celine.voice.input`` subpackage, which never listens
in the background. Speech output is off by default (see ``config.VOICE_ENABLED``).
"""

from celine.voice.tts import (
    SpeakResult,
    Speaker,
    VoiceError,
    build_engine,
    select_voice,
)

__all__ = [
    "Speaker",
    "SpeakResult",
    "VoiceError",
    "build_engine",
    "select_voice",
]
