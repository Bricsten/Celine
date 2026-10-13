"""Offline neural text-to-speech through Piper (piper-tts + onnxruntime).

This engine synthesises speech locally with a Piper voice model and plays it
through the Windows ``winsound`` API. Both the voice model and the playback
path come from trusted local configuration, never from the model or the
conversation: the engine never runs a shell command, never accepts an
executable path, and never touches the network while speaking.

If Piper or its voice model is unavailable, ``available()`` returns ``False``
and the voice layer can fall back to the built-in Windows SAPI engine.
"""

import json
import wave
from io import BytesIO
from pathlib import Path

from celine.core import config
from celine.voice.engines import VoiceError, VoiceInfo

try:  # piper-tts is an optional, heavyweight dependency
    from piper import PiperVoice
    from piper import SynthesisConfig as _SynthesisConfig

    _PIPER_IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - any import failure disables the engine
    PiperVoice = None
    _SynthesisConfig = None
    _PIPER_IMPORT_ERROR = exc

try:  # winsound is part of the Windows standard library
    import winsound

    _WINSOUND_IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - non-Windows disables the engine
    winsound = None
    _WINSOUND_IMPORT_ERROR = exc


# ``src/celine/voice/engines/piper_engine.py`` -> repository root.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _resolve_model_path(path):
    """Return an absolute model path, trusting only configured locations."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = _PROJECT_ROOT / candidate
    return candidate


def _locale_from_config_file(path):
    """Read the Piper voice's locale from its JSON sidecar, honestly."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return "unknown"
    language = data.get("language") or {}
    code = language.get("code")
    if not code:
        return "unknown"
    return str(code).replace("_", "-")


class PiperEngine:
    """Synchronous Piper synthesis with in-memory WAV playback."""

    name = "piper"

    def __init__(
        self,
        *,
        model_path=None,
        config_path=None,
        voice_name=None,
        locale=None,
        gender=None,
        loader=None,
        player=None,
    ):
        self._model_path = _resolve_model_path(
            config.VOICE_PIPER_MODEL if model_path is None else model_path
        )
        self._config_path = (
            _resolve_model_path(config_path)
            if config_path is not None
            else Path(f"{self._model_path}.json")
        )
        self._voice_name = voice_name or config.VOICE_PIPER_VOICE
        self._locale = locale
        self._gender = gender or config.VOICE_PIPER_GENDER
        # Injectable seams keep automated tests free of real audio/ONNX work.
        self._loader = loader
        self._player = player
        self._voice = None
        self._loaded = False

    def available(self):
        """True when Piper, winsound, and the configured model are present."""
        if self._loader is not None:
            return True
        if _PIPER_IMPORT_ERROR is not None or _WINSOUND_IMPORT_ERROR is not None:
            return False
        return self._model_path.is_file()

    def _locale_value(self):
        if self._locale:
            return self._locale
        return _locale_from_config_file(self._config_path)

    def list_voices(self):
        """Piper voices are single-speaker: report the one configured voice."""
        return [
            VoiceInfo(
                name=self._voice_name,
                locale=self._locale_value(),
                gender=self._gender,
                engine_voice_id=self._voice_name,
            )
        ]

    def _ensure_voice(self):
        if self._loaded:
            return
        if self._loader is not None:
            self._voice = self._loader(str(self._model_path))
            self._loaded = True
            return
        if PiperVoice is None:
            raise VoiceError("piper is not installed")
        if not self._model_path.is_file():
            raise VoiceError("the configured voice model was not found")
        self._voice = PiperVoice.load(str(self._model_path))
        self._loaded = True

    @staticmethod
    def _length_scale(rate):
        """Map a SAPI-style rate (-10..10) to a Piper length scale."""
        try:
            value = int(rate)
        except (TypeError, ValueError):
            value = 0
        value = max(-10, min(10, value))
        return 2.0 ** (-value / 10.0)

    @staticmethod
    def _normalized_volume(volume):
        try:
            value = float(volume)
        except (TypeError, ValueError):
            value = 100.0
        return max(0.0, min(1.0, value / 100.0))

    def _synthesis_config(self, rate, volume):
        if _SynthesisConfig is None:
            return None
        return _SynthesisConfig(
            volume=self._normalized_volume(volume),
            length_scale=self._length_scale(rate),
        )

    def _synthesize(self, text, syn_config):
        buffer = BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            self._voice.synthesize_wav(text, wav_file, syn_config=syn_config)
        return buffer.getvalue()

    def _play(self, wav_bytes):
        if self._player is not None:
            self._player(wav_bytes)
            return
        if winsound is None:
            raise VoiceError("winsound is unavailable on this platform")
        winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_NODEFAULT)

    def speak(self, text, *, rate=0, volume=100, voice_id=None):
        self._ensure_voice()
        syn_config = self._synthesis_config(rate, volume)
        try:
            wav_bytes = self._synthesize(str(text), syn_config)
        except Exception as exc:  # noqa: BLE001 - report, do not crash Celine
            raise VoiceError(f"piper synthesis failed: {exc}") from exc
        if not wav_bytes:
            raise VoiceError("piper produced no audio")
        try:
            self._play(wav_bytes)
        except VoiceError:
            raise
        except Exception as exc:  # noqa: BLE001 - report, do not crash Celine
            raise VoiceError(f"piper playback failed: {exc}") from exc

    def stop(self):
        if winsound is None:
            return
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

    def shutdown(self):
        self._voice = None
        self._loaded = False
