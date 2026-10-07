"""Tests for safe window control. No real windows are manipulated."""

from types import SimpleNamespace

import pytest

from celine.core import config
from celine.tools import registry, window_control


class FakeWindow:
    """Small HwndWrapper stand-in that records only approved actions."""

    def __init__(self):
        self.calls = []

    def minimize(self):
        self.calls.append("minimize")

    def restore(self):
        self.calls.append("restore")

    def set_focus(self):
        self.calls.append("focus")

    def close(self):
        self.calls.append("close")


def install_window(monkeypatch, *, title, class_name, process_name):
    """Install mocked enumeration, PID lookup, and window wrapping."""
    element = SimpleNamespace(
        name=title,
        class_name=class_name,
        process_id=1234,
        handle=5678,
    )
    window = FakeWindow()
    monkeypatch.setattr(window_control, "_find_windows", lambda: [element])
    monkeypatch.setattr(window_control, "_process_name", lambda pid: process_name)
    monkeypatch.setattr(window_control, "_wrap", lambda handle: window)
    return window


@pytest.mark.parametrize("action", ["minimize", "restore", "focus"])
def test_notepad_actions(monkeypatch, action):
    window = install_window(
        monkeypatch,
        title="Untitled - Notepad",
        class_name="Notepad",
        process_name="notepad.exe",
    )
    result = window_control.control_window("notepad", action)
    assert "completed successfully" in result
    assert window.calls == [action]


def test_close_calculator_is_graceful(monkeypatch):
    window = install_window(
        monkeypatch,
        title="Calculator",
        class_name="ApplicationFrameWindow",
        process_name="calculatorapp.exe",
    )
    result = window_control.control_window("calculator", "close")
    assert "completed successfully" in result
    assert window.calls == ["close"]
    assert not hasattr(window, "terminate")
    assert not hasattr(window, "kill")


def test_microsoft_word_alias_resolves(monkeypatch):
    window = install_window(
        monkeypatch,
        title="Document1 - Word",
        class_name="OpusApp",
        process_name="winword.exe",
    )
    result = window_control.control_window("Microsoft Word", "focus")
    assert "for word" in result
    assert window.calls == ["focus"]


def test_file_explorer_alias_resolves(monkeypatch):
    window = install_window(
        monkeypatch,
        title="Downloads",
        class_name="CabinetWClass",
        process_name="explorer.exe",
    )
    result = window_control.control_window("File Explorer", "restore")
    assert "for file_explorer" in result
    assert window.calls == ["restore"]


@pytest.mark.parametrize(
    "application",
    [
        "spotify",
        "powershell -Command Remove-Item C:\\",
        r"C:\Windows\System32\notepad.exe",
        ".*Notepad.*",
    ],
)
def test_unapproved_or_arbitrary_application_rejected(monkeypatch, application):
    def must_not_enumerate():
        raise AssertionError("window enumeration must not occur")

    monkeypatch.setattr(window_control, "_find_windows", must_not_enumerate)
    result = window_control.control_window(application, "focus")
    assert "not allowed" in result


def test_invalid_action_rejected_before_enumeration(monkeypatch):
    def must_not_enumerate():
        raise AssertionError("window enumeration must not occur")

    monkeypatch.setattr(window_control, "_find_windows", must_not_enumerate)
    result = window_control.control_window("notepad", "type")
    assert "Action is not allowed" in result


def test_no_running_window_is_handled(monkeypatch):
    monkeypatch.setattr(window_control, "_find_windows", lambda: [])
    result = window_control.control_window("notepad", "minimize")
    assert "not currently open" in result
    assert "No window was changed" in result


def test_nonmatching_window_is_not_controlled(monkeypatch):
    window = install_window(
        monkeypatch,
        title="Settings",
        class_name="ApplicationFrameWindow",
        process_name="applicationframehost.exe",
    )
    result = window_control.control_window("calculator", "close")
    assert "not currently open" in result
    assert window.calls == []


def test_pywinauto_enumeration_exception_is_handled(monkeypatch):
    def fail_enumeration():
        raise RuntimeError("pywinauto unavailable")

    monkeypatch.setattr(window_control, "_find_windows", fail_enumeration)
    result = window_control.control_window("notepad", "focus")
    assert "could not be completed" in result


def test_pywinauto_action_exception_is_handled(monkeypatch):
    window = install_window(
        monkeypatch,
        title="Untitled - Notepad",
        class_name="Notepad",
        process_name="notepad.exe",
    )

    def fail_focus():
        raise RuntimeError("focus denied")

    window.set_focus = fail_focus
    result = window_control.control_window("notepad", "focus")
    assert "could not be completed" in result


def test_registry_rejects_missing_control_window_argument(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "control_window",
        lambda **kwargs: calls.append(kwargs),
    )
    name, result = registry.run_tool_call({
        "function": {
            "name": "control_window",
            "arguments": {"application": "notepad"},
        }
    })
    assert name == "control_window"
    assert "missing required arguments: action" in result
    assert "Nothing was executed" in result
    assert calls == []


def test_registry_rejects_extra_control_window_argument(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "control_window",
        lambda **kwargs: calls.append(kwargs),
    )
    name, result = registry.run_tool_call({
        "function": {
            "name": "control_window",
            "arguments": {
                "application": "notepad",
                "action": "focus",
                "title": ".*",
            },
        }
    })
    assert name == "control_window"
    assert "unexpected arguments: title" in result
    assert "Nothing was executed" in result
    assert calls == []


def test_control_window_schema_has_exact_arguments():
    schema = next(
        item["function"]
        for item in registry.TOOL_SCHEMAS
        if item["function"]["name"] == "control_window"
    )
    parameters = schema["parameters"]
    assert set(parameters["properties"]) == {"application", "action"}
    assert parameters["required"] == ["application", "action"]
    assert parameters["additionalProperties"] is False


def test_debug_logging_is_concise(monkeypatch, capsys):
    window = install_window(
        monkeypatch,
        title="Untitled - Notepad",
        class_name="Notepad",
        process_name="notepad.exe",
    )
    monkeypatch.setattr(config, "TOOL_LOG", True)
    window_control.control_window("notepad", "minimize")
    output = capsys.readouterr().out
    assert window.calls == ["minimize"]
    assert "[tool] control_window requested application=notepad action=minimize" in output
    assert "[tool] control_window success application=notepad action=minimize" in output
