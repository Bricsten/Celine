"""Offline speech-to-text through Vosk (Kaldi).

The transcriber turns one PCM clip into text entirely on this machine: no
network access, no upload, no cloud service. The speech model path is trusted
local configuration and is never supplied by the model or the conversation.

An optional word list can bias recognition toward expected commands; when it is
empty the recogniser runs with its full general vocabulary. If Vosk or the
configured model is unavailable, ``available()`` returns ``False`` and the
caller stays silent rather than guessing.
"""

import json
from pathlib import Path

from celine.core import config
from celine.voice.input import InputError, audio

try:  # vosk is an optional dependency
    from vosk import KaldiRecognizer, Model, SetLogLevel

    _VOSK_IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - any import failure disables STT
    KaldiRecognizer = None
    Model = None
    SetLogLevel = None
    _VOSK_IMPORT_ERROR = exc


# ``src/celine/voice/input/transcription.py`` -> repository root.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _resolve_model_path(path):
    """Return an absolute model path, trusting only configured locations."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = _PROJECT_ROOT / candidate
    return candidate


class VoskTranscriber:
    """Single-shot Vosk recognition over one in-memory PCM clip."""

    name = "vosk"

    def __init__(
        self,
        *,
        model_path=None,
        samplerate=None,
        vocabulary=None,
        model_factory=None,
    ):
        self._model_path = _resolve_model_path(
            config.STT_VOSK_MODEL if model_path is None else model_path
        )
        self._samplerate = int(
            config.MICROPHONE_SAMPLE_RATE if samplerate is None else samplerate
        )
        self._vocabulary = list(
            config.STT_VOCABULARY if vocabulary is None else vocabulary
        )
        # Injectable seam: tests supply a fake model and never load ONNX/Kaldi.
        self._model_factory = model_factory
        self._model = None
        self._loaded = False
        self._closed = False

    def available(self):
        """True when Vosk and the configured model directory are present."""
        if self._model_factory is not None:
            return True
        if _VOSK_IMPORT_ERROR is not None:
            return False
        return self._model_path.is_dir()

    def _ensure_model(self):
        if self._loaded:
            return
        if self._model_factory is not None:
            self._model = self._model_factory(str(self._model_path))
            self._loaded = True
            return
        if Model is None:
            raise InputError("vosk is not installed")
        if not self._model_path.is_dir():
            raise InputError("the configured speech model was not found")
        try:
            SetLogLevel(-1)
        except Exception:  # noqa: BLE001 - logging level is cosmetic
            pass
        try:
            self._model = Model(str(self._model_path))
        except Exception as exc:  # noqa: BLE001 - report, do not crash Celine
            raise InputError(f"could not load the speech model: {exc}") from exc
        self._loaded = True

    def _new_recognizer(self, samplerate):
        if self._vocabulary:
            grammar = json.dumps(list(self._vocabulary) + ["[unk]"])
            return KaldiRecognizer(self._model, samplerate, grammar)
        return KaldiRecognizer(self._model, samplerate)

    def transcribe(self, pcm, *, samplerate=None):
        """Return the recognized text (trimmed, possibly empty). Never guesses."""
        if self._closed:
            raise InputError("transcriber is closed")
        if not pcm:
            return ""
        self._ensure_model()
        rate = int(self._samplerate if samplerate is None else samplerate)
        if rate != self._samplerate and rate > 0:
            # Vosk models expect their training rate; convert rather than lie.
            samples = audio.resample(
                audio.pcm_to_samples(pcm), rate, self._samplerate
            )
            pcm = audio.samples_to_pcm(samples)
            rate = self._samplerate
        chunk_bytes = max(2, rate) * 2  # about half a second of 16-bit mono
        try:
            recognizer = self._new_recognizer(rate)
            for start in range(0, len(pcm), chunk_bytes):
                recognizer.AcceptWaveform(pcm[start:start + chunk_bytes])
            result = json.loads(recognizer.FinalResult())
        except InputError:
            raise
        except Exception as exc:  # noqa: BLE001 - report, do not crash Celine
            raise InputError(f"speech recognition failed: {exc}") from exc
        return str(result.get("text") or "").strip()

    def close(self):
        self._model = None
        self._loaded = False
        self._closed = True
