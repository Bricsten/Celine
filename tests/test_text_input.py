"""Tests for Notepad-only text insertion. No real UI is manipulated."""

import ctypes
import inspect
from types import SimpleNamespace

import pytest

from celine.core import config
from celine.core.assistant import Assistant
from celine.tools import registry, text_input


class FakeControl:
    def __init__(self, class_name="RichEditD2DPT", handle=222):
        self.handle = handle
        self.element_info = SimpleNamespace(
            class_name=class_name,
            handle=handle,
        )

    def is_visible(self):
        return True

    def is_enabled(self):
        return True


class FakeUiaWindow:
    def __init__(self, documents=(), edits=()):
        self._controls = {
            "Document": list(documents),
            "Edit": list(edits),
        }

    def descendants(self, *, control_type):
        return self._controls[control_type]


class FakeHwndWrapper:
    def __init__(self, handle, existing_length=8, error=None):
        self.handle = handle
        self.existing_length = existing_length
        self.error = error
        self.calls = []

    def verify_actionable(self):
        self.calls.append(("verify_actionable",))
        if self.error:
            raise self.error

    def send_message(self, message, wparam=0, lparam=0):
        if message == text_input.win32defines.WM_GETTEXTLENGTH:
            self.calls.append(("length",))
            return self.existing_length
        if message == text_input.win32defines.EM_SETSEL:
            self.calls.append(("select", wparam, lparam))
            return 0
        if message == text_input.win32defines.EM_REPLACESEL:
            self.calls.append(("replace", bool(wparam), ctypes.wstring_at(lparam)))
            return 0
        raise AssertionError(f"unexpected message: {message}")


def install_notepad(monkeypatch, *, controls=None, wrapper=None):
    control = FakeControl() if controls is None else controls
    if isinstance(control, FakeControl):
        control = [control]
    top = FakeUiaWindow(documents=control)
    wrapped = wrapper or FakeHwndWrapper(222)
    seen_handles = []

    monkeypatch.setattr(text_input, "_find_window", lambda app: 111)
    monkeypatch.setattr(text_input, "_uia_window", lambda hwnd: top)

    def make_wrapper(handle):
        seen_handles.append(handle)
        return wrapped

    monkeypatch.setattr(text_input, "HwndWrapper", make_wrapper)
    return wrapped, seen_handles


def test_valid_notepad_text_is_appended_to_verified_child(monkeypatch):
    wrapper, seen_handles = install_notepad(monkeypatch)

    result = text_input.write_text("notepad", "Hello, 世界 😀", "append")

    assert "appended successfully" in result
    assert seen_handles == [222]
    assert wrapper.calls == [
        ("verify_actionable",),
        ("length",),
        ("select", 8, 8),
        ("replace", True, "Hello, 世界 😀"),
    ]


def test_new_line_adds_crlf_before_text(monkeypatch):
    wrapper, _ = install_notepad(monkeypatch)
    result = text_input.write_text("notepad", "Second line", "new_line")
    assert "new line successfully" in result
    assert ("replace", True, "\r\nSecond line") in wrapper.calls


def test_new_line_on_empty_document_has_no_leading_crlf(monkeypatch):
    wrapper = FakeHwndWrapper(222, existing_length=0)
    install_notepad(monkeypatch, wrapper=wrapper)
    result = text_input.write_text("notepad", "Hello", "new_line")
    assert "new line successfully" in result
    assert ("replace", True, "Hello") in wrapper.calls


def test_notepad_name_is_normalized(monkeypatch):
    wrapper, _ = install_notepad(monkeypatch)
    result = text_input.write_text("  NOTEPAD  ", "hello", "append")
    assert "appended successfully" in result
    assert ("replace", True, "hello") in wrapper.calls


@pytest.mark.parametrize("application", ["word", "calculator", "spotify"])
def test_other_applications_are_rejected(monkeypatch, application):
    monkeypatch.setattr(
        text_input,
        "_find_window",
        lambda app: pytest.fail("window discovery must not run"),
    )
    result = text_input.write_text(application, "hello", "append")
    assert "only allowed for notepad" in result
    assert "No text was entered" in result


def test_executable_path_is_rejected(monkeypatch):
    monkeypatch.setattr(
        text_input,
        "_find_window",
        lambda app: pytest.fail("window discovery must not run"),
    )
    result = text_input.write_text(
        r"C:\Windows\notepad.exe", "hello", "append"
    )
    assert "only allowed for notepad" in result


def test_non_string_text_is_rejected_before_discovery(monkeypatch):
    monkeypatch.setattr(
        text_input,
        "_find_window",
        lambda app: pytest.fail("window discovery must not run"),
    )
    result = text_input.write_text("notepad", None, "append")
    assert "Text must be a string" in result


def test_empty_text_is_rejected_before_discovery(monkeypatch):
    monkeypatch.setattr(
        text_input,
        "_find_window",
        lambda app: pytest.fail("window discovery must not run"),
    )
    result = text_input.write_text("notepad", "", "append")
    assert "Text is empty" in result


def test_over_limit_text_is_rejected_before_discovery(monkeypatch):
    monkeypatch.setattr(
        text_input,
        "_find_window",
        lambda app: pytest.fail("window discovery must not run"),
    )
    result = text_input.write_text(
        "notepad",
        "x" * (text_input.MAX_TEXT_LENGTH + 1),
        "append",
    )
    assert "10,000-character limit" in result


def test_exact_text_limit_is_accepted(monkeypatch):
    wrapper, _ = install_notepad(monkeypatch)
    text = "界" * text_input.MAX_TEXT_LENGTH
    result = text_input.write_text("notepad", text, "new_line")
    assert "new line successfully" in result
    assert ("replace", True, "\r\n" + text) in wrapper.calls


def test_unsupported_mode_is_rejected_before_discovery(monkeypatch):
    monkeypatch.setattr(
        text_input,
        "_find_window",
        lambda app: pytest.fail("window discovery must not run"),
    )
    result = text_input.write_text("notepad", "hello", "replace")
    assert "Text mode is not allowed" in result


def test_notepad_not_running_is_handled(monkeypatch):
    monkeypatch.setattr(text_input, "_find_window", lambda app: None)
    monkeypatch.setattr(
        text_input,
        "_uia_window",
        lambda hwnd: pytest.fail("UIA discovery must not run"),
    )
    result = text_input.write_text("notepad", "hello", "append")
    assert result == "Notepad is not currently open. No text was entered."


def test_editable_control_not_found_is_handled(monkeypatch):
    monkeypatch.setattr(text_input, "_find_window", lambda app: 111)
    monkeypatch.setattr(
        text_input,
        "_uia_window",
        lambda hwnd: FakeUiaWindow(),
    )
    result = text_input.write_text("notepad", "hello", "append")
    assert "editable control could not be identified" in result


def test_classic_notepad_edit_control_is_supported(monkeypatch):
    edit = FakeControl(class_name="Edit", handle=333)
    top = FakeUiaWindow(edits=[edit])
    wrapper = FakeHwndWrapper(333, existing_length=4)
    monkeypatch.setattr(text_input, "_find_window", lambda app: 111)
    monkeypatch.setattr(text_input, "_uia_window", lambda hwnd: top)
    monkeypatch.setattr(text_input, "HwndWrapper", lambda handle: wrapper)
    result = text_input.write_text("notepad", "more", "append")
    assert "appended successfully" in result
    assert ("select", 4, 4) in wrapper.calls


def test_automation_exception_is_handled(monkeypatch):
    wrapper = FakeHwndWrapper(222, error=RuntimeError("denied"))
    install_notepad(monkeypatch, wrapper=wrapper)
    result = text_input.write_text("notepad", "hello", "append")
    assert "automation failed" in result
    assert "No text was entered" in result


def test_multiple_matching_controls_are_rejected(monkeypatch):
    controls = [FakeControl(handle=222), FakeControl(handle=333)]
    install_notepad(monkeypatch, controls=controls)
    result = text_input.write_text("notepad", "hello", "append")
    assert "editable control could not be identified" in result


def test_text_path_has_no_global_keyboard_api():
    source = inspect.getsource(text_input)
    for prohibited in (
        "send_keys",
        "type_keys",
        "pyautogui",
        "SendInput",
        "keyboard.send",
        "hotkey",
        "clipboard",
    ):
        assert prohibited not in source


def test_registry_rejects_missing_application(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY, "write_text", lambda **kw: calls.append(kw)
    )
    _, result = registry.run_tool_call({
        "function": {
            "name": "write_text",
            "arguments": {"text": "hello", "mode": "append"},
        }
    })
    assert "missing required arguments: application" in result
    assert calls == []


def test_registry_rejects_missing_text(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY, "write_text", lambda **kw: calls.append(kw)
    )
    _, result = registry.run_tool_call({
        "function": {
            "name": "write_text",
            "arguments": {"application": "notepad", "mode": "append"},
        }
    })
    assert "missing required arguments: text" in result
    assert calls == []


def test_registry_rejects_missing_mode(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY, "write_text", lambda **kw: calls.append(kw)
    )
    _, result = registry.run_tool_call({
        "function": {
            "name": "write_text",
            "arguments": {"application": "notepad", "text": "hello"},
        }
    })
    assert "missing required arguments: mode" in result
    assert calls == []


def test_registry_rejects_extra_argument(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY, "write_text", lambda **kw: calls.append(kw)
    )
    _, result = registry.run_tool_call({
        "function": {
            "name": "write_text",
            "arguments": {
                "application": "notepad",
                "text": "hello",
                "mode": "append",
                "title": ".*",
            },
        }
    })
    assert "unexpected arguments: title" in result
    assert calls == []


def test_registry_rejects_non_string_text(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY, "write_text", lambda **kw: calls.append(kw)
    )
    _, result = registry.run_tool_call({
        "function": {
            "name": "write_text",
            "arguments": {
                "application": "notepad",
                "text": 123,
                "mode": "append",
            },
        }
    })
    assert "argument 'text' must be a string" in result
    assert calls == []


def test_registry_rejects_non_string_application(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY, "write_text", lambda **kw: calls.append(kw)
    )
    _, result = registry.run_tool_call({
        "function": {
            "name": "write_text",
            "arguments": {
                "application": 123,
                "text": "hello",
                "mode": "append",
            },
        }
    })
    assert "argument 'application' must be a string" in result
    assert calls == []


def test_registry_rejects_non_string_mode(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY, "write_text", lambda **kw: calls.append(kw)
    )
    _, result = registry.run_tool_call({
        "function": {
            "name": "write_text",
            "arguments": {
                "application": "notepad",
                "text": "hello",
                "mode": 123,
            },
        }
    })
    assert "argument 'mode' must be a string" in result
    assert calls == []


def test_registry_rejects_unsupported_application(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY, "write_text", lambda **kw: calls.append(kw)
    )
    _, result = registry.run_tool_call({
        "function": {
            "name": "write_text",
            "arguments": {
                "application": "word",
                "text": "hello",
                "mode": "append",
            },
        }
    })
    assert "supports only the notepad application" in result
    assert calls == []


def test_registry_rejects_unsupported_mode(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY, "write_text", lambda **kw: calls.append(kw)
    )
    _, result = registry.run_tool_call({
        "function": {
            "name": "write_text",
            "arguments": {
                "application": "notepad",
                "text": "hello",
                "mode": "replace",
            },
        }
    })
    assert "mode must be one of: append, new_line" in result
    assert calls == []


def test_write_text_schema_is_exact():
    schema = next(
        item["function"]
        for item in registry.TOOL_SCHEMAS
        if item["function"]["name"] == "write_text"
    )
    parameters = schema["parameters"]
    assert set(parameters["properties"]) == {"application", "text", "mode"}
    assert parameters["properties"]["mode"]["enum"] == ["append", "new_line"]
    assert parameters["required"] == ["application", "text", "mode"]
    assert parameters["additionalProperties"] is False
    assert "type_text" not in registry.TOOL_REGISTRY


def test_agent_supports_open_then_write_across_tool_rounds(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "open_application",
        lambda name: calls.append(("open_application", name)) or "opened",
    )
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "write_text",
        lambda application, text, mode: calls.append(
            ("write_text", application, text, mode)
        )
        or "typed",
    )
    responses = iter([
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "function": {
                    "name": "open_application",
                    "arguments": {"name": "notepad"},
                }
            }],
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "function": {
                    "name": "write_text",
                    "arguments": {
                        "application": "notepad",
                        "text": "Hello from Celine.",
                        "mode": "append",
                    },
                }
            }],
        },
        {"role": "assistant", "content": "Done."},
    ])
    assistant = Assistant(chat=lambda messages, tools: next(responses))

    reply = assistant.ask("Open Notepad and write Hello from Celine.")

    assert reply == "Done."
    assert calls == [
        ("open_application", "notepad"),
        ("write_text", "notepad", "Hello from Celine.", "append"),
    ]


def test_tool_log_contains_metadata_not_text(monkeypatch, capsys):
    install_notepad(monkeypatch)
    monkeypatch.setattr(config, "TOOL_LOG", True)
    secret = "do not log this"
    text_input.write_text("notepad", secret, "new_line")
    output = capsys.readouterr().out
    assert "requested application=notepad mode=new_line chars=15" in output
    assert "success application=notepad mode=new_line chars=15" in output
    assert secret not in output
