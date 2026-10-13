"""Tests for offline push-to-talk input. No real mic, model, or audio is used."""

import inspect

import pytest

from celine import main as main_module
from celine.core import config
from celine.voice.input import (
    InputError,
    PushToTalk,
    Recording,
    build_recorder,
    build_transcriber,
    run_push_to_talk,
)
from celine.voice.input import microphone, transcription
from celine.voice.input.microphone import Microphone
from celine.voice.input.transcription import VoskTranscriber


class FakeRecorder:
    """Recorder double; never touches audio hardware."""

    name = "fake-recorder"

    def __init__(self, recording=None, available=True, error=None):
        self._recording = recording or Recording(b"\x01\x02" * 1600, 16000, 0.1)
        self._available = available
        self._error = error
        self.record_calls = []
        self.closed = 0

    def available(self):
        return self._available

    def record(self, *, max_seconds, stop=None):
        self.record_calls.append(max_seconds)
        if self._error is not None:
            raise self._error
        return self._recording

    def close(self):
        self.closed += 1


class FakeTranscriber:
    """Transcriber double; never loads a speech model."""

    name = "fake-transcriber"

    def __init__(self, text="open notepad", available=True, error=None):
        self._text = text
        self._available = available
        self._error = error
        self.calls = []
        self.closed = 0

    def available(self):
        return self._available

    def transcribe(self, pcm, *, samplerate):
        self.calls.append((pcm, samplerate))
        if self._error is not None:
            raise self._error
        return self._text

    def close(self):
        self.closed += 1


def make_ptt(**kwargs):
    kwargs.setdefault("enabled", True)
    kwargs.setdefault("recorder", FakeRecorder())
    kwargs.setdefault("transcriber", FakeTranscriber())
    return PushToTalk(**kwargs)


def test_microphone_disabled_by_default(monkeypatch):
    monkeypatch.setattr(config, "MICROPHONE_ENABLED", False)
    ptt = PushToTalk(recorder=FakeRecorder(), transcriber=FakeTranscriber())

    result = ptt.capture()

    assert result.ok is False
    assert result.reason == "disabled"


def test_capture_returns_confirmed_text():
    recorder = FakeRecorder()
    transcriber = FakeTranscriber(text="open notepad")
    ptt = make_ptt(recorder=recorder, transcriber=transcriber)

    result = ptt.capture()

    assert result.ok is True
    assert result.text == "open notepad"
    assert result.seconds >= 0.0
    assert recorder.record_calls == [ptt.max_seconds]
    assert transcriber.calls[0][1] == 16000


def test_capture_without_microphone_degrades():
    ptt = make_ptt(recorder=FakeRecorder(available=False))

    result = ptt.capture()

    assert result.ok is False
    assert result.reason == "no_microphone"


def test_capture_without_speech_model_degrades():
    ptt = make_ptt(transcriber=FakeTranscriber(available=False))

    result = ptt.capture()

    assert result.ok is False
    assert result.reason == "no_speech_model"


def test_capture_with_no_audio_reports_it():
    ptt = make_ptt(recorder=FakeRecorder(Recording(b"", 16000, 0.0)))

    result = ptt.capture()

    assert result.ok is False
    assert result.reason == "no_audio"


def test_empty_transcript_never_reaches_the_assistant():
    ptt = make_ptt(transcriber=FakeTranscriber(text="   "))

    result = ptt.capture()

    assert result.ok is False
    assert result.reason == "empty_transcript"


def test_transcript_shorter_than_min_chars_is_discarded():
    ptt = make_ptt(transcriber=FakeTranscriber(text="hi"), min_chars=5)

    result = ptt.capture()

    assert result.ok is False
    assert result.reason == "empty_transcript"


def test_recording_error_is_reported_not_raised():
    ptt = make_ptt(recorder=FakeRecorder(error=InputError("device busy")))

    result = ptt.capture()

    assert result.ok is False
    assert result.reason == "recording_failed"


def test_transcription_error_is_reported_not_raised():
    ptt = make_ptt(transcriber=FakeTranscriber(error=InputError("bad audio")))

    result = ptt.capture()

    assert result.ok is False
    assert result.reason == "transcription_failed"


def test_shutdown_closes_backends_once_and_is_idempotent():
    recorder = FakeRecorder()
    transcriber = FakeTranscriber()
    ptt = make_ptt(recorder=recorder, transcriber=transcriber)

    ptt.shutdown()
    ptt.shutdown()

    assert recorder.closed == 1
    assert transcriber.closed == 1
    assert ptt.capture().reason == "closed"


def test_build_recorder_and_transcriber_fail_safely_on_unknown():
    assert build_recorder("sounddevice").name == "sounddevice"
    assert build_transcriber("vosk").name == "vosk"
    with pytest.raises(InputError):
        build_recorder("nope")
    with pytest.raises(InputError):
        build_transcriber("nope")


class FakeStream:
    """Minimal RawInputStream double that yields silent PCM blocks."""

    def __init__(self, factory_kwargs):
        self.factory_kwargs = factory_kwargs
        self.reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, frames):
        self.reads += 1
        return b"\x03\x04" * frames, False


def test_microphone_records_bounded_pcm_with_injected_stream():
    streams = []

    def stream_factory(**kwargs):
        stream = FakeStream(kwargs)
        streams.append(stream)
        return stream

    mic = Microphone(stream_factory=stream_factory)

    assert mic.available() is True
    recording = mic.record(max_seconds=5, stop=lambda: streams[0].reads >= 2)

    assert streams[0].reads == 2
    assert recording.samplerate == 16000
    assert len(recording.pcm) == 2 * 1600 * 2
    assert recording.truncated is False
    assert streams[0].factory_kwargs["dtype"] == "int16"


class FakeStereoStream(FakeStream):
    """Yields interleaved stereo PCM so downmixing can be exercised."""

    def read(self, frames):
        self.reads += 1
        return b"\x03\x04" * (frames * 2), False


def test_microphone_downmixes_stereo_and_reports_source_rate():
    streams = []

    def stream_factory(**kwargs):
        stream = FakeStereoStream(kwargs)
        streams.append(stream)
        return stream

    mic = Microphone(channels=2, stream_factory=stream_factory)

    recording = mic.record(max_seconds=5, stop=lambda: streams[0].reads >= 1)

    assert recording.channels == 1
    assert recording.source_samplerate == 16000
    assert len(recording.pcm) == 1600 * 2


def test_microphone_device_info_is_safe_metadata():
    info = Microphone().device_info()

    assert set(info) == {
        "backend",
        "device",
        "channels",
        "target_samplerate",
        "warming_up_seconds",
    }
    assert info["target_samplerate"] == 16000


def test_list_input_devices_without_backend(monkeypatch):
    monkeypatch.setattr(microphone, "_sd", None)

    assert microphone.list_input_devices() == []


def test_microphone_is_bounded_by_max_seconds(monkeypatch):
    class FakeClock:
        def __init__(self, values):
            self._values = list(values)

        def perf_counter(self):
            return self._values.pop(0) if self._values else 999.0

    monkeypatch.setattr(microphone, "time", FakeClock([0.0, 0.0, 0.0, 10.0]))
    mic = Microphone(stream_factory=lambda **kw: FakeStream(kw))

    recording = mic.record(max_seconds=1)

    assert recording.truncated is True
    assert mic._closed is False


def test_microphone_unavailable_without_backend(monkeypatch):
    monkeypatch.setattr(microphone, "_sd", None)
    monkeypatch.setattr(microphone, "_SD_IMPORT_ERROR", RuntimeError("boom"))
    assert Microphone().available() is False


def test_microphone_closed_rejects_recording():
    mic = Microphone(stream_factory=lambda **kw: FakeStream(kw))
    mic.close()
    with pytest.raises(InputError):
        mic.record(max_seconds=1)


class FakeRecognizer:
    """KaldiRecognizer double; returns canned JSON without any decoding."""

    instances = []

    def __init__(self, *args):
        self.args = args
        self.fed = []
        self.final = '{"text": "hello there"}'
        FakeRecognizer.instances.append(self)

    def AcceptWaveform(self, data):
        self.fed.append(data)
        return False

    def FinalResult(self):
        return self.final


def test_transcriber_reports_missing_dependency(monkeypatch):
    monkeypatch.setattr(transcription, "_VOSK_IMPORT_ERROR", RuntimeError("boom"))
    assert VoskTranscriber().available() is False


def test_transcriber_reports_missing_model(tmp_path):
    transcriber = VoskTranscriber(model_path=str(tmp_path / "missing"))
    assert transcriber.available() is False


def test_transcriber_parses_text_with_fake_recognizer(monkeypatch):
    FakeRecognizer.instances = []
    monkeypatch.setattr(transcription, "KaldiRecognizer", FakeRecognizer)
    transcriber = VoskTranscriber(model_factory=lambda path: "MODEL")

    text = transcriber.transcribe(b"\x01\x02" * 100, samplerate=16000)

    assert text == "hello there"
    assert FakeRecognizer.instances[0].args[:2] == ("MODEL", 16000)
    assert FakeRecognizer.instances[0].fed  # audio was actually fed in


def test_transcriber_uses_vocabulary_when_configured(monkeypatch):
    FakeRecognizer.instances = []
    monkeypatch.setattr(transcription, "KaldiRecognizer", FakeRecognizer)
    transcriber = VoskTranscriber(
        vocabulary=["open", "notepad"], model_factory=lambda path: "MODEL"
    )

    transcriber.transcribe(b"\x01\x02" * 100, samplerate=16000)

    args = FakeRecognizer.instances[0].args
    assert len(args) == 3
    assert "open" in args[2] and "[unk]" in args[2]


def test_transcriber_empty_clip_returns_empty_without_loading():
    loads = []
    transcriber = VoskTranscriber(model_factory=lambda p: loads.append(p) or "MODEL")

    assert transcriber.transcribe(b"", samplerate=16000) == ""
    assert loads == []


def test_transcriber_resamples_mismatched_rate(monkeypatch):
    FakeRecognizer.instances = []
    monkeypatch.setattr(transcription, "KaldiRecognizer", FakeRecognizer)
    transcriber = VoskTranscriber(model_factory=lambda path: "MODEL")

    text = transcriber.transcribe(b"\x01\x02" * 4800, samplerate=48000)

    assert text == "hello there"
    assert FakeRecognizer.instances[0].args[:2] == ("MODEL", 16000)


def test_transcriber_wraps_backend_failure(monkeypatch):
    class BrokenRecognizer(FakeRecognizer):
        def AcceptWaveform(self, data):
            raise RuntimeError("decoder exploded")

    monkeypatch.setattr(transcription, "KaldiRecognizer", BrokenRecognizer)
    transcriber = VoskTranscriber(model_factory=lambda path: "MODEL")

    with pytest.raises(InputError):
        transcriber.transcribe(b"\x01\x02" * 100, samplerate=16000)


def test_transcriber_closed_rejects_further_use():
    transcriber = VoskTranscriber(model_factory=lambda path: "MODEL")
    transcriber.close()
    with pytest.raises(InputError):
        transcriber.transcribe(b"\x01\x02" * 100, samplerate=16000)


def collect():
    output = []
    return output, output.append


def test_run_push_to_talk_confirms_before_returning():
    output, sink = collect()
    ptt = make_ptt(transcriber=FakeTranscriber(text="open notepad"))

    text = run_push_to_talk(
        ptt,
        input_fn=lambda prompt: "",
        output=sink,
    )

    assert text == "open notepad"
    assert any("You said" in line for line in output)


def test_run_push_to_talk_can_re_record_then_send():
    output, sink = collect()
    recorder = FakeRecorder()
    ptt = make_ptt(recorder=recorder, transcriber=FakeTranscriber(text="open word"))
    answers = iter(["r", ""])

    text = run_push_to_talk(
        ptt,
        input_fn=lambda prompt: next(answers),
        output=sink,
    )

    assert text == "open word"
    assert len(recorder.record_calls) == 2


def test_run_push_to_talk_cancel_returns_none():
    output, sink = collect()
    ptt = make_ptt()

    text = run_push_to_talk(
        ptt,
        input_fn=lambda prompt: "c",
        output=sink,
    )

    assert text is None
    assert any("Cancelled" in line for line in output)


def test_run_push_to_talk_disabled_explains_itself():
    output, sink = collect()
    ptt = make_ptt(enabled=False)

    text = run_push_to_talk(ptt, input_fn=lambda prompt: "", output=sink)

    assert text is None
    assert any("off" in line for line in output)


def test_main_microphone_command_is_off_by_default(monkeypatch, capsys):
    asked = []

    class FakeAssistant:
        def __init__(self, chat):
            pass

        def ask(self, user_text):
            asked.append(user_text)
            return "ok"

    monkeypatch.setattr(config, "MICROPHONE_ENABLED", False)
    monkeypatch.setattr(main_module, "Assistant", FakeAssistant)
    monkeypatch.setattr(main_module, "Speaker", lambda: _NullSpeaker())
    inputs = iter(["/mic", "quit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

    main_module.main()

    printed = capsys.readouterr().out
    assert "Microphone input is off" in printed
    assert asked == []


class _NullSpeaker:
    requested = False
    enabled = False

    def speak(self, text):
        from celine.voice import SpeakResult

        return SpeakResult(False, "disabled")

    def shutdown(self):
        pass


def test_input_modules_do_not_execute_shell_or_use_network():
    for module in (microphone, transcription):
        source = inspect.getsource(module)
        for token in ("subprocess", "os.system", "shell=True", "eval(", "exec("):
            assert token not in source
        for token in ("import socket", "urllib", "requests", "http://", "https://"):
            assert token not in source
