"""Celine's offline voice output (text-to-speech only).

This milestone implements spoken replies only. There is no microphone input,
speech recognition, wake word, or background listening anywhere in this
package. Speech is off by default (see ``config.VOICE_ENABLED``).
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
