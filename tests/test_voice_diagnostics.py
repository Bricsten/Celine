"""Tests for /mic-test and /mic-devices. No real microphone is ever opened."""

from celine import main as main_module
from celine.core import config
from celine.voice.input import PushToTalkResult, Recording
from celine.voice.input import diagnostics
from celine.voice.input.audio import AudioStats


class FakeMic:
    def device_info(self):
        return {
            "backend": "sounddevice",
            "device": None,
            "channels": 1,
            "target_samplerate": 16000,
            "warming_up_seconds": 0.15,
        }


class FakePtt:
    enabled = True
    max_seconds = 6.0

    def __init__(self, result):
        self._result = result
        self.calls = []

    def capture(self, *, stop=None, diagnostics=False):
        self.calls.append(diagnostics)
        return self._result


class NullSpeaker:
    requested = False
    enabled = False

    def speak(self, text):
        from celine.voice import SpeakResult

        return SpeakResult(False, "disabled")

    def shutdown(self):
        pass


def make_stats():
    return AudioStats(
        seconds=1.0,
        samplerate=16000,
        source_samplerate=48000,
        channels=1,
        sample_count=16000,
        rms=0.1,
        peak=0.3,
        silence_ratio=0.2,
        clipping_ratio=0.0,
        noise_floor=0.001,
        snr_db=20.0,
        frames_received=True,
        overflowed=0,
        truncated=False,
        classification="valid audio for recognition",
    )


def fake_devices(monkeypatch):
    monkeypatch.setattr(
        diagnostics.microphone,
        "list_input_devices",
        lambda: [
            {
                "index": 0,
                "name": "Test Mic",
                "channels": 1,
                "default_samplerate": 48000,
            }
        ],
    )
    monkeypatch.setattr(
        diagnostics.microphone, "Microphone", lambda: FakeMic()
    )


def collect():
    output = []
    return output, output.append


def test_run_mic_test_reports_devices_stats_and_transcript(monkeypatch):
    fake_devices(monkeypatch)
    output, sink = collect()
    result = PushToTalkResult(
        True,
        "hello",
        None,
        1.0,
        make_stats(),
        Recording(b"\x00\x00" * 16000, 16000, 1.0),
    )

    returned = diagnostics.run_mic_test(
        FakePtt(result), output=sink, input_fn=lambda p: "n"
    )

    assert returned is None
    joined = "\n".join(output)
    assert "Test Mic" in joined
    assert "assessment" in joined
    assert 'Transcript: "hello"' in joined
    assert "Saved" not in joined


def test_run_mic_test_empty_transcript_stays_offline_and_explains(monkeypatch):
    fake_devices(monkeypatch)
    output, sink = collect()
    result = PushToTalkResult(
        False, "", "empty_transcript", 1.0, make_stats(), None
    )

    diagnostics.run_mic_test(FakePtt(result), output=sink, input_fn=lambda p: "")

    joined = "\n".join(output)
    assert "couldn't make out" in joined
    assert "never changes your microphone" in joined


def test_run_mic_test_without_audio_reports_it(monkeypatch):
    fake_devices(monkeypatch)
    output, sink = collect()
    result = PushToTalkResult(False, "", "no_audio", 0.1, None, None)

    diagnostics.run_mic_test(FakePtt(result), output=sink, input_fn=lambda p: "")

    joined = "\n".join(output)
    assert "No audio was captured" in joined


def test_run_mic_devices_lists_without_recording(monkeypatch):
    fake_devices(monkeypatch)
    output, sink = collect()

    diagnostics.run_mic_devices(output=sink)

    joined = "\n".join(output)
    assert "Test Mic" in joined
    assert "no recording is made" in joined


def test_save_fixture_writes_a_valid_wav(tmp_path):
    recording = Recording(b"\x10\x00" * 1600, 16000, 0.1)
    path = diagnostics.save_fixture(
        recording, directory=tmp_path, filename="clip.wav"
    )
    assert path.exists()
    assert path.read_bytes()[:4] == b"RIFF"


def test_run_mic_test_saves_fixture_only_when_confirmed(monkeypatch, tmp_path):
    fake_devices(monkeypatch)
    monkeypatch.setattr(config, "MICROPHONE_SAVE_FIXTURES", True)
    monkeypatch.setattr(config, "MICROPHONE_FIXTURE_DIR", str(tmp_path))
    result = PushToTalkResult(
        True,
        "hello",
        None,
        1.0,
        make_stats(),
        Recording(b"\x10\x00" * 1600, 16000, 0.1),
    )

    output, sink = collect()
    diagnostics.run_mic_test(FakePtt(result), output=sink, input_fn=lambda p: "n")
    assert "Saved" not in "\n".join(output)
    assert list(tmp_path.iterdir()) == []

    output, sink = collect()
    diagnostics.run_mic_test(FakePtt(result), output=sink, input_fn=lambda p: "y")
    assert "Saved" in "\n".join(output)
    assert len(list(tmp_path.iterdir())) == 1


def make_main(monkeypatch, inputs):
    asked = []

    class FakeAssistant:
        def __init__(self, chat):
            pass

        def ask(self, user_text):
            asked.append(user_text)
            return "ok"

    monkeypatch.setattr(main_module, "Assistant", FakeAssistant)
    monkeypatch.setattr(main_module, "Speaker", lambda: NullSpeaker())
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    return asked


def test_main_mic_test_never_reaches_the_assistant(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(config, "MICROPHONE_ENABLED", True)
    monkeypatch.setattr(config, "MICROPHONE_DIAGNOSTICS", True)
    monkeypatch.setattr(
        "celine.voice.input.run_mic_test",
        lambda ptt, **kwargs: called.append(True) or None,
    )
    asked = make_main(monkeypatch, iter(["/mic-test", "quit"]))

    main_module.main()

    assert called == [True]
    assert asked == []


def test_main_mic_test_requires_diagnostics_flag(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(config, "MICROPHONE_ENABLED", True)
    monkeypatch.setattr(config, "MICROPHONE_DIAGNOSTICS", False)
    monkeypatch.setattr(
        "celine.voice.input.run_mic_test",
        lambda ptt, **kwargs: called.append(True) or None,
    )
    make_main(monkeypatch, iter(["/mic-test", "quit"]))

    main_module.main()

    assert called == []
    assert "Diagnostics are off" in capsys.readouterr().out


def test_main_mic_devices_command_lists_devices(monkeypatch):
    called = []
    monkeypatch.setattr(config, "MICROPHONE_ENABLED", True)
    monkeypatch.setattr(
        "celine.voice.input.run_mic_devices",
        lambda **kwargs: called.append(True) or None,
    )
    make_main(monkeypatch, iter(["/mic-devices", "quit"]))

    main_module.main()

    assert called == [True]


def test_main_mic_commands_disabled_are_reported(monkeypatch, capsys):
    monkeypatch.setattr(config, "MICROPHONE_ENABLED", False)
    make_main(monkeypatch, iter(["/mic-test", "quit"]))

    main_module.main()

    assert "Microphone input is off" in capsys.readouterr().out
