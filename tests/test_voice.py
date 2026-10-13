"""Tests for the offline voice layer. No real audio is produced or required."""

from celine import main as main_module
from celine.core import config
from celine.voice import SpeakResult, Speaker, VoiceError, select_voice
from celine.voice.engines import VoiceInfo


class FakeEngine:
    """A speech engine double; never touches audio hardware."""

    name = "fake"

    def __init__(self, voices=(), available=True, speak_error=None):
        self._voices = list(voices)
        self._available = available
        self._speak_error = speak_error
        self.speak_calls = []
        self.stop_calls = 0
        self.shutdown_calls = 0

    def available(self):
        return self._available

    def list_voices(self):
        return list(self._voices)

    def speak(self, text, *, rate, volume, voice_id):
        self.speak_calls.append((text, rate, volume, voice_id))
        if self._speak_error is not None:
            raise self._speak_error

    def stop(self):
        self.stop_calls += 1

    def shutdown(self):
        self.shutdown_calls += 1


ZIRA = VoiceInfo("Microsoft Zira Desktop", "en-US", "Female", "zira")
HAZEL = VoiceInfo("Microsoft Hazel Desktop", "en-GB", "Female", "hazel")


def test_voice_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(config, "VOICE_ENABLED", False)
    engine = FakeEngine(voices=[ZIRA])
    speaker = Speaker(engine=engine)

    result = speaker.speak("Good morning")

    assert result.spoken is False
    assert result.reason == "disabled"
    assert engine.speak_calls == []


def test_enabled_speaks_text_with_configured_settings(monkeypatch):
    monkeypatch.setattr(config, "VOICE_ENABLED", True)
    engine = FakeEngine(voices=[ZIRA])
    speaker = Speaker(engine=engine)

    result = speaker.speak("Good morning!")

    assert result.spoken is True
    assert result.voice == "zira"
    assert result.seconds >= 0.0
    assert engine.speak_calls == [
        ("Good morning!", config.VOICE_RATE, config.VOICE_VOLUME, "zira")
    ]


def test_unavailable_engine_degrades_to_silence(monkeypatch):
    monkeypatch.setattr(config, "VOICE_ENABLED", True)
    engine = FakeEngine(available=False)
    speaker = Speaker(engine=engine)

    result = speaker.speak("Hello")

    assert result.spoken is False
    assert result.reason == "engine_unavailable"
    assert speaker.enabled is False
    assert engine.speak_calls == []


def test_missing_preferred_voice_falls_back_and_says_so(monkeypatch):
    monkeypatch.setattr(config, "VOICE_ENABLED", True)
    monkeypatch.setattr(config, "VOICE_PREFERRED_LOCALE", "en-GB")
    engine = FakeEngine(voices=[ZIRA])
    speaker = Speaker(engine=engine)

    result = speaker.speak("Hello")

    assert result.spoken is True
    assert result.voice == "zira"
    assert "en-GB" in result.note
    assert "unavailable" in result.note
    assert "en-US" in result.note


def test_playback_failure_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(config, "VOICE_ENABLED", True)
    engine = FakeEngine(voices=[ZIRA], speak_error=VoiceError("device busy"))
    speaker = Speaker(engine=engine)

    result = speaker.speak("Hello")

    assert result.spoken is False
    assert result.reason == "playback_failed:VoiceError"
    assert len(engine.speak_calls) == 1


def test_empty_or_missing_response_is_not_spoken(monkeypatch):
    monkeypatch.setattr(config, "VOICE_ENABLED", True)
    engine = FakeEngine(voices=[ZIRA])
    speaker = Speaker(engine=engine)

    for text in ("", "   ", None):
        result = speaker.speak(text)
        assert result.spoken is False
        assert result.reason == "empty_text"

    assert engine.speak_calls == []


def test_shutdown_is_idempotent_and_stops_speech(monkeypatch):
    monkeypatch.setattr(config, "VOICE_ENABLED", True)
    engine = FakeEngine(voices=[ZIRA])
    speaker = Speaker(engine=engine)
    speaker.speak("Hello")

    speaker.shutdown()
    speaker.shutdown()

    assert engine.shutdown_calls == 1
    after = speaker.speak("Again")
    assert after.spoken is False
    assert after.reason == "closed"
    assert len(engine.speak_calls) == 1


def test_select_voice_prefers_locale_then_gender():
    voice_id, note = select_voice(
        [ZIRA, HAZEL], preferred="en-GB", fallback="en-US", prefer_female=True
    )
    assert voice_id == "hazel"
    assert "using" in note


def test_select_voice_fallback_note_is_honest():
    voice_id, note = select_voice(
        [ZIRA], preferred="en-GB", fallback="en-US", prefer_female=True
    )
    assert voice_id == "zira"
    assert "en-GB" in note
    assert "unavailable" in note


def test_select_voice_with_no_voices_uses_engine_default():
    voice_id, note = select_voice([], preferred="en-GB")
    assert voice_id is None
    assert "default" in note


def test_locale_from_language_maps_and_marks_unknown():
    from celine.voice.engines.windows_sapi import locale_from_language

    assert locale_from_language("409") == "en-US"
    assert locale_from_language("809") == "en-GB"
    assert locale_from_language(None) == "unknown"
    assert locale_from_language("not-a-lcid") == "unknown"


def test_speak_reply_reports_failure_only_when_voice_was_requested(capsys):
    class FailingSpeaker:
        requested = True

        def speak(self, text):
            return SpeakResult(False, "playback_failed:VoiceError")

    main_module._speak_reply(FailingSpeaker(), "Hello")
    assert "speech was not played" in capsys.readouterr().out

    class DisabledSpeaker:
        requested = False

        def speak(self, text):
            return SpeakResult(False, "disabled")

    main_module._speak_reply(DisabledSpeaker(), "Hello")
    assert capsys.readouterr().out == ""


def test_main_speaks_only_the_final_reply(monkeypatch):
    spoken = []

    class RecordingSpeaker:
        requested = True
        enabled = True

        def speak(self, text):
            spoken.append(text)
            return SpeakResult(True, seconds=0.05)

        def shutdown(self):
            pass

    class FakeAssistant:
        def __init__(self, chat):
            pass

        def ask(self, user_text):
            # Stands in for a run that included an internal tool call: only
            # the final user-facing reply is ever returned.
            return "Notepad has been opened."

    inputs = iter(["Open Notepad.", "quit"])
    monkeypatch.setattr(main_module, "Assistant", FakeAssistant)
    monkeypatch.setattr(main_module, "Speaker", lambda: RecordingSpeaker())
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

    main_module.main()

    assert spoken == ["Notepad has been opened."]


def test_voice_engine_does_not_execute_shell_or_paths():
    import inspect

    from celine.voice.engines import windows_sapi

    source = inspect.getsource(windows_sapi)
    assert "subprocess" not in source
    assert "os.system" not in source
    assert "shell=True" not in source
    assert "eval(" not in source
    assert "exec(" not in source
