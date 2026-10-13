"""Text-to-speech orchestration for Celine's spoken replies.

This layer decides *whether* and *how* to speak; the speech engine is injected
and replaceable. It never runs shell commands, never accepts executable paths,
and never raises during a normal request: a failed or unavailable engine
degrades to silence with an honest reason.
"""

import time
from dataclasses import dataclass

from celine.core import config
from celine.voice.engines import SpeechEngine, VoiceError, VoiceInfo

__all__ = ["Speaker", "SpeakResult", "VoiceError", "select_voice"]


@dataclass(frozen=True)
class SpeakResult:
    """Outcome of one speak attempt, including an honest failure reason."""

    spoken: bool
    reason: str | None = None
    seconds: float = 0.0
    voice: str | None = None
    note: str | None = None


def _normalize_locale(value):
    return str(value or "").strip().lower().replace("_", "-")


def _display_locale(value):
    normalized = _normalize_locale(value)
    language, _, region = normalized.partition("-")
    if language and region:
        return f"{language}-{region.upper()}"
    return normalized


def _is_female(voice):
    return str(voice.gender or "").strip().lower() == "female"


def _note_for(voice, preferred):
    description = f"{voice.locale} {voice.gender} voice {voice.name!r}"
    if _normalize_locale(voice.locale) == preferred:
        return f"using {description}"
    return (
        f"{_display_locale(preferred)} voice unavailable; "
        f"using fallback {description}"
    )


def select_voice(
    voices,
    preferred=None,
    fallback=None,
    prefer_female=None,
):
    """Choose one voice, preferring locale then gender, and describe it.

    Returns ``(engine_voice_id | None, note)``. A ``None`` id means the engine
    will use its own default voice. The note never claims a non-preferred
    voice is the preferred locale.
    """
    preferred = _normalize_locale(
        config.VOICE_PREFERRED_LOCALE if preferred is None else preferred
    )
    fallback = _normalize_locale(
        config.VOICE_FALLBACK_LOCALE if fallback is None else fallback
    )
    if prefer_female is None:
        prefer_female = config.VOICE_PREFER_FEMALE

    if not voices:
        return None, "no voices reported by the engine; engine default used"

    def pick(pool):
        if prefer_female:
            for voice in pool:
                if _is_female(voice):
                    return voice
        return pool[0] if pool else None

    for locale in (preferred, fallback):
        pool = [v for v in voices if _normalize_locale(v.locale) == locale]
        chosen = pick(pool)
        if chosen is not None:
            return chosen.engine_voice_id, _note_for(chosen, preferred)

    chosen = pick(list(voices))
    return chosen.engine_voice_id, _note_for(chosen, preferred)


def build_engine(name):
    """Construct one known engine by name. Unknown names fail safely."""
    if name == "windows_sapi":
        from celine.voice.engines.windows_sapi import WindowsSapiEngine

        return WindowsSapiEngine()
    raise VoiceError(f"unknown voice engine: {name!r}")


class Speaker:
    """Owns one engine and speaks final assistant replies on request."""

    def __init__(self, engine=None, *, enabled=None, engine_name=None):
        requested = config.VOICE_ENABLED if enabled is None else bool(enabled)
        self.requested = requested
        self.enabled = requested
        self._engine = engine
        self._engine_name = engine_name or config.VOICE_ENGINE
        self._prepared = False
        self._voice_id = None
        self._note = None
        self._last_error = None
        self._announced = False
        self._closed = False

    def prepare(self):
        """Resolve the engine and voice once. Never raises."""
        if self._prepared or self._closed or not self.enabled:
            return
        self._prepared = True
        try:
            if self._engine is None:
                self._engine = build_engine(self._engine_name)
        except Exception as exc:  # noqa: BLE001 - degrade to silence
            self._disable(f"engine_init_failed:{exc.__class__.__name__}")
            return
        try:
            if self._engine is None or not self._engine.available():
                self._disable("engine_unavailable")
                return
        except Exception as exc:  # noqa: BLE001 - degrade to silence
            self._disable(f"engine_check_failed:{exc.__class__.__name__}")
            return
        try:
            voices = self._engine.list_voices()
        except Exception:  # noqa: BLE001 - voice list is optional metadata
            voices = []
        try:
            self._voice_id, self._note = select_voice(voices)
        except Exception:  # noqa: BLE001 - never block speaking on metadata
            self._voice_id, self._note = None, "voice selection failed"

    def speak(self, text):
        """Speak final text. Returns a result; never raises."""
        if self._closed:
            return SpeakResult(False, "closed")
        if not self.enabled:
            return SpeakResult(False, "disabled")
        if not isinstance(text, str) or not text.strip():
            return SpeakResult(False, "empty_text")

        self.prepare()
        if not self.enabled:
            return SpeakResult(False, self._last_error or "unavailable")
        self._announce_once()

        started = time.perf_counter()
        try:
            self._engine.speak(
                text,
                rate=config.VOICE_RATE,
                volume=config.VOICE_VOLUME,
                voice_id=self._voice_id,
            )
        except Exception as exc:  # noqa: BLE001 - report, do not crash Celine
            return SpeakResult(
                False,
                f"playback_failed:{exc.__class__.__name__}",
                time.perf_counter() - started,
                voice=self._voice_id,
                note=self._note,
            )
        return SpeakResult(
            True,
            None,
            time.perf_counter() - started,
            voice=self._voice_id,
            note=self._note,
        )

    def shutdown(self):
        """Release engine resources. Safe to call more than once."""
        self._closed = True
        engine = self._engine
        self._engine = None
        self._prepared = False
        self._voice_id = None
        if engine is not None:
            try:
                engine.shutdown()
            except Exception:  # noqa: BLE001 - shutdown must never raise
                pass

    def _announce_once(self):
        if self._announced or not self._note:
            return
        self._announced = True
        print(f"[voice] {self._note}")

    def _disable(self, reason):
        self.enabled = False
        self._last_error = reason
