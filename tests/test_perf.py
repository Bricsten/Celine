"""Tests for the optional performance instrumentation. No server needed."""

from celine.core import config
from celine.core.assistant import Assistant
from celine.core.perf import PerfLog


class FakeChat:
    """Minimal stand-in for ollama_client.chat."""

    def __init__(self, *responses):
        self.responses = list(responses)

    def __call__(self, messages, tools):
        return self.responses.pop(0)


def test_perf_is_silent_by_default(capsys):
    perf = PerfLog()
    assert perf.enabled is False
    perf.start()
    perf.add_ollama_call(1.0)
    perf.finish()
    assert capsys.readouterr().out == ""


def test_perf_report_lines(capsys):
    perf = PerfLog(enabled=True)
    perf.start()
    perf.add_ollama_call(6.42)
    perf.add_tool_call("get_current_time", 0.001)
    perf.add_ollama_call(4.87)
    perf.finish()

    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "[perf] ollama_call_1=6.42s"
    assert lines[1] == "[perf] tool:get_current_time=0.001s"
    assert lines[2] == "[perf] ollama_call_2=4.87s"
    assert lines[3].startswith("[perf] total=")
    assert lines[3].endswith("ollama_calls=2 tool_calls=1")


def test_assistant_prints_perf_when_flag_enabled(monkeypatch, capsys):
    monkeypatch.setattr(config, "PERF_LOG", True)
    tool_request = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"function": {"name": "get_current_time", "arguments": {}}}
        ],
    }
    final_answer = {"role": "assistant", "content": "It is 03:48."}
    assistant = Assistant(chat=FakeChat(tool_request, final_answer))

    assistant.ask("What time is it?")

    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert lines[0].startswith("[perf] ollama_call_1=")
    assert any(line.startswith("[perf] tool:get_current_time=") for line in lines)
    assert lines[2].startswith("[perf] ollama_call_2=")
    assert lines[-1].startswith("[perf] total=")
    assert lines[-1].endswith("ollama_calls=2 tool_calls=1")


def test_assistant_prints_no_perf_when_flag_disabled(monkeypatch, capsys):
    monkeypatch.setattr(config, "PERF_LOG", False)
    assistant = Assistant(chat=FakeChat({"role": "assistant", "content": "Hi."}))

    reply = assistant.ask("Hello")

    assert reply == "Hi."
    assert "[perf]" not in capsys.readouterr().out
