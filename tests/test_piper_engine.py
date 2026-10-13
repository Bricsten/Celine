"""Tests for the Piper neural voice engine. No real audio or ONNX work."""

import inspect

import pytest

from celine.core import config
from celine.voice import Speaker, VoiceError, build_engine
from celine.voice.engines import VoiceInfo
from celine.voice.engines import piper_engine
from celine.voice.engines.piper_engine import PiperEngine


class FakeVoice:
    """Stand-in for PiperVoice; writes a tiny well-formed WAV."""

    def __init__(self):
        self.calls = []

    def synthesize_wav(self, text, wav_file, syn_config=None, set_wav_format=True):
        self.calls.append((text, syn_config))
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x00\x00" * 128)


def make_engine(**kwargs):
    loader = kwargs.pop("loader", None)
    player = kwargs.pop("player", None)
    return PiperEngine(
        model_path=kwargs.pop("model_path", "models/piper/en_GB-cori-medium.onnx"),
        loader=loader,
        player=player,
        **kwargs,
    )


def test_build_engine_returns_piper_engine():
    engine = build_engine("piper")
    assert isinstance(engine, PiperEngine)
    assert engine.name == "piper"


def test_build_engine_unknown_name_fails_safely():
    with pytest.raises(VoiceError):
        build_engine("does-not-exist")


def test_list_voices_reports_british_female():
    engine = make_engine(locale="en-GB")
    voices = engine.list_voices()
    assert len(voices) == 1
    voice = voices[0]
    assert voice.locale == "en-GB"
    assert voice.gender == "Female"
    assert voice.engine_voice_id == config.VOICE_PIPER_VOICE


def test_locale_read_from_model_config(tmp_path):
    cfg = tmp_path / "voice.onnx.json"
    cfg.write_text('{"language": {"code": "en_GB"}}', encoding="utf-8")
    engine = PiperEngine(config_path=str(cfg))
    assert engine.list_voices()[0].locale == "en-GB"


def test_locale_is_honestly_unknown_when_config_missing(tmp_path):
    engine = PiperEngine(config_path=str(tmp_path / "missing.onnx.json"))
    assert engine.list_voices()[0].locale == "unknown"


def test_model_unavailable_when_file_missing():
    engine = make_engine(model_path="models/piper/nope.onnx")
    assert engine.available() is False


def test_missing_dependency_disables_engine(monkeypatch):
    monkeypatch.setattr(piper_engine, "_PIPER_IMPORT_ERROR", RuntimeError("boom"))
    engine = make_engine()
    assert engine.available() is False


def test_missing_winsound_disables_engine(monkeypatch):
    monkeypatch.setattr(piper_engine, "_WINSOUND_IMPORT_ERROR", RuntimeError("boom"))
    engine = make_engine()
    assert engine.available() is False


def test_speak_synthesises_and_plays_captured_wav():
    voice = FakeVoice()
    played = []
    engine = make_engine(
        locale="en-GB",
        loader=lambda path: voice,
        player=played.append,
    )

    engine.speak("Hello there.", rate=0, volume=100)

    assert len(voice.calls) == 1
    assert voice.calls[0][0] == "Hello there."
    assert len(played) == 1
    assert played[0][:4] == b"RIFF"  # a real WAV header was produced


def test_model_is_loaded_once_and_reused():
    voice = FakeVoice()
    loads = []

    def loader(path):
        loads.append(path)
        return voice

    engine = make_engine(locale="en-GB", loader=loader, player=lambda _b: None)
    engine.speak("one", rate=0, volume=100)
    engine.speak("two", rate=0, volume=100)

    assert len(loads) == 1
    assert len(voice.calls) == 2


def test_rate_maps_to_length_scale():
    voice = FakeVoice()
    engine = make_engine(locale="en-GB", loader=lambda p: voice, player=lambda _b: None)

    engine.speak("normal", rate=0, volume=100)
    engine.speak("fast", rate=10, volume=100)

    normal = voice.calls[0][1]
    fast = voice.calls[1][1]
    assert normal is not None and fast is not None
    assert fast.length_scale < normal.length_scale


def test_playback_error_is_wrapped_as_voice_error():
    voice = FakeVoice()

    def broken_player(_bytes):
        raise RuntimeError("audio device busy")

    engine = make_engine(
        locale="en-GB", loader=lambda p: voice, player=broken_player
    )
    with pytest.raises(VoiceError):
        engine.speak("Hello", rate=0, volume=100)


def test_synthesis_error_is_wrapped_as_voice_error():
    class BrokenVoice(FakeVoice):
        def synthesize_wav(self, *args, **kwargs):
            raise RuntimeError("model exploded")

    engine = make_engine(
        locale="en-GB", loader=lambda p: BrokenVoice(), player=lambda _b: None
    )
    with pytest.raises(VoiceError):
        engine.speak("Hello", rate=0, volume=100)


def test_speak_raises_when_piper_is_not_installed(monkeypatch):
    monkeypatch.setattr(piper_engine, "PiperVoice", None)
    engine = make_engine(locale="en-GB")
    with pytest.raises(VoiceError):
        engine.speak("Hello", rate=0, volume=100)


def test_shutdown_releases_loaded_model():
    voice = FakeVoice()
    engine = make_engine(locale="en-GB", loader=lambda p: voice, player=lambda _b: None)
    engine.speak("Hello", rate=0, volume=100)
    assert engine._voice is voice

    engine.shutdown()
    assert engine._voice is None
    assert engine._loaded is False


def list_via(*names):
    return [
        VoiceInfo(name=n, locale="en-US", gender="Female", engine_voice_id=n)
        for n in names
    ]


class RecordingEngine:
    def __init__(self, name, available=True, voices=()):
        self.name = name
        self._available = available
        self._voices = list(voices)
        self.spoken = []

    def available(self):
        return self._available

    def list_voices(self):
        return list(self._voices)

    def speak(self, text, *, rate, volume, voice_id):
        self.spoken.append((text, voice_id))

    def stop(self):
        pass

    def shutdown(self):
        pass


def test_speaker_falls_back_to_sapi_when_piper_unavailable(monkeypatch):
    piper = RecordingEngine("piper", available=False)
    sapi = RecordingEngine("windows_sapi", available=True, voices=list_via("zira"))

    def fake_build(name):
        return piper if name == "piper" else sapi

    monkeypatch.setattr("celine.voice.tts.build_engine", fake_build)
    speaker = Speaker(enabled=True, engine_name="piper")

    result = speaker.speak("Hello")

    assert result.spoken is True
    assert result.voice == "zira"
    assert sapi.spoken == [("Hello", "zira")]


def test_speaker_stays_silent_when_fallback_not_permitted(monkeypatch):
    piper = RecordingEngine("piper", available=False)
    monkeypatch.setattr(
        "celine.voice.tts.build_engine", lambda name: piper
    )
    speaker = Speaker(enabled=True, engine_name="piper", allow_fallback=False)

    result = speaker.speak("Hello")

    assert result.spoken is False
    assert result.reason == "engine_unavailable"


def test_speaker_reports_when_both_engines_unavailable(monkeypatch):
    def fake_build(name):
        return RecordingEngine(name, available=False)

    monkeypatch.setattr("celine.voice.tts.build_engine", fake_build)
    speaker = Speaker(enabled=True, engine_name="piper")

    result = speaker.speak("Hello")

    assert result.spoken is False
    assert result.reason == "engine_unavailable"


def test_piper_engine_does_not_execute_shell_or_use_network():
    source = inspect.getsource(piper_engine)
    for token in ("subprocess", "os.system", "shell=True", "eval(", "exec("):
        assert token not in source
    for token in ("import socket", "import urllib", "import requests", "http"):
        assert token not in source
