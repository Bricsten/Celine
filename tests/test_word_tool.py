"""Tests for the public Word tool and registry. Word is never launched."""

import ast
import inspect

import pytest

from celine.core import config, prompts
from celine.core.assistant import Assistant
from celine.tools import registry
from celine.tools.word import adapter as adapter_module
from celine.tools.word import tool as word_tool
from celine.tools.word.adapter import (
    ATTACHMENT_FAILED,
    CREATION_ACTIVATION_FAILED,
    CREATION_FAILED,
    CREATION_UNCONFIRMED,
    VALIDATION_REJECTED,
    WRITE_FAILED,
    WordAdapterError,
)


class FakeAdapter:
    def __init__(self, error=None):
        self.error = error
        self.calls = []
        self.create_calls = 0

    def write_text(self, text, mode):
        self.calls.append((text, mode))
        if self.error:
            raise self.error

    def create_document(self):
        self.create_calls += 1
        if self.error:
            raise self.error


def install_adapter(monkeypatch, error=None):
    adapter = FakeAdapter(error)
    monkeypatch.setattr(word_tool, "_adapter_factory", lambda: adapter)
    return adapter


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("append", "Text appended successfully in Microsoft Word."),
        ("new_paragraph", "Paragraph added successfully in Microsoft Word."),
    ],
)
def test_valid_word_modes(monkeypatch, mode, expected):
    adapter = install_adapter(monkeypatch)
    result = word_tool.write_word_text("Hello 😀", mode)
    assert result == expected
    assert adapter.calls == [("Hello 😀", mode)]


@pytest.mark.parametrize(
    ("text", "mode", "message"),
    [
        ("", "append", "Text is empty"),
        (None, "append", "Text must be a string"),
        ("hello", "replace", "mode is not allowed"),
        ("hello", None, "mode is not allowed"),
    ],
)
def test_invalid_tool_arguments_never_reach_adapter(
    monkeypatch, text, mode, message
):
    adapter = install_adapter(monkeypatch)
    result = word_tool.write_word_text(text, mode)
    assert message in result
    assert adapter.calls == []


def test_exact_text_limit_is_accepted(monkeypatch):
    adapter = install_adapter(monkeypatch)
    text = "界" * word_tool.MAX_WORD_TEXT_LENGTH
    result = word_tool.write_word_text(text, "new_paragraph")
    assert "Paragraph added successfully" in result
    assert adapter.calls == [(text, "new_paragraph")]


def test_over_limit_is_rejected_before_adapter(monkeypatch):
    adapter = install_adapter(monkeypatch)
    result = word_tool.write_word_text(
        "x" * (word_tool.MAX_WORD_TEXT_LENGTH + 1),
        "append",
    )
    assert "10,000-character limit" in result
    assert adapter.calls == []


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (
            VALIDATION_REJECTED,
            "Microsoft Word could not be safely targeted. "
            "No write was attempted.",
        ),
        (
            ATTACHMENT_FAILED,
            "Microsoft Word could not be safely attached. "
            "No write was attempted.",
        ),
        (WRITE_FAILED, "The Word write operation could not be confirmed."),
    ],
)
def test_adapter_failure_reports_safe_operation_stage(
    monkeypatch, outcome, expected
):
    error = WordAdapterError(
        "ambiguous_word_target",
        "internal detail",
        outcome=outcome,
    )
    install_adapter(monkeypatch, error)
    result = word_tool.write_word_text("hello", "append")
    assert result == expected
    assert "success" not in result.lower()


def test_create_word_document_success_returns_no_document_contents(monkeypatch):
    adapter = install_adapter(monkeypatch)
    result = word_tool.create_word_document()
    assert result == "Blank Microsoft Word document created successfully."
    assert adapter.create_calls == 1
    assert "Document1" not in result
    assert "content" not in result.lower()


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (
            VALIDATION_REJECTED,
            "Microsoft Word could not be safely targeted. "
            "No document creation was attempted.",
        ),
        (
            ATTACHMENT_FAILED,
            "Microsoft Word could not be safely attached. "
            "No document creation was attempted.",
        ),
        (
            CREATION_FAILED,
            "The Word document creation operation could not be confirmed.",
        ),
        (
            CREATION_UNCONFIRMED,
            "A Word document may have been created, but the result could not "
            "be safely confirmed.",
        ),
        (
            CREATION_ACTIVATION_FAILED,
            "A blank Word document was created, but its window could not be "
            "brought to the foreground.",
        ),
    ],
)
def test_create_word_document_reports_safe_operation_stage(
    monkeypatch, outcome, expected
):
    error = WordAdapterError("classified", "internal", outcome=outcome)
    adapter = install_adapter(monkeypatch, error)
    assert word_tool.create_word_document() == expected
    assert adapter.create_calls == 1


def test_create_refuses_existing_document_with_specific_result(monkeypatch):
    error = WordAdapterError("document_already_open", "internal")
    install_adapter(monkeypatch, error)
    assert word_tool.create_word_document() == (
        "Microsoft Word already has an open document. "
        "No new document was created."
    )


def test_write_reports_no_document_for_safe_planning(monkeypatch):
    error = WordAdapterError("no_document", "internal")
    install_adapter(monkeypatch, error)
    assert word_tool.write_word_text("Hello", "append") == (
        "Microsoft Word is running, but no document is open. "
        "No write was attempted."
    )


def registry_call(arguments):
    return registry.run_tool_call({
        "function": {"name": "write_word_text", "arguments": arguments}
    })


def creation_registry_call(arguments):
    return registry.run_tool_call({
        "function": {
            "name": "create_word_document",
            "arguments": arguments,
        }
    })


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"mode": "append"}, "missing required arguments: text"),
        ({"text": "hello"}, "missing required arguments: mode"),
        (
            {"text": "hello", "mode": "append", "application": "word"},
            "unexpected arguments: application",
        ),
        ({"text": 123, "mode": "append"}, "'text' must be a string"),
        ({"text": "hello", "mode": 123}, "'mode' must be a string"),
        (
            {"text": "hello", "mode": "replace"},
            "mode must be one of: append, new_paragraph",
        ),
    ],
)
def test_registry_rejects_invalid_arguments_before_execution(
    monkeypatch, arguments, expected
):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "write_word_text",
        lambda **kwargs: calls.append(kwargs),
    )
    _, result = registry_call(arguments)
    assert expected in result
    assert calls == []


@pytest.mark.parametrize("extra_name", ["method", "property", "path", "vba"])
def test_model_cannot_supply_com_or_file_controls(monkeypatch, extra_name):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "write_word_text",
        lambda **kwargs: calls.append(kwargs),
    )
    arguments = {"text": "hello", "mode": "append", extra_name: "unsafe"}
    _, result = registry_call(arguments)
    assert f"unexpected arguments: {extra_name}" in result
    assert calls == []


def test_word_schema_is_exact():
    schema = next(
        item["function"]
        for item in registry.TOOL_SCHEMAS
        if item["function"]["name"] == "write_word_text"
    )
    parameters = schema["parameters"]
    assert set(parameters["properties"]) == {"text", "mode"}
    assert parameters["properties"]["mode"]["enum"] == [
        "append",
        "new_paragraph",
    ]
    assert parameters["required"] == ["text", "mode"]
    assert parameters["additionalProperties"] is False


def test_create_word_document_schema_has_no_arguments():
    schema = next(
        item["function"]
        for item in registry.TOOL_SCHEMAS
        if item["function"]["name"] == "create_word_document"
    )
    parameters = schema["parameters"]
    assert parameters == {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }


def test_create_registry_accepts_no_arguments(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "create_word_document",
        lambda: calls.append(()) or "created",
    )
    _, result = creation_registry_call({})
    assert result == "created"
    assert calls == [()]


@pytest.mark.parametrize(
    "arguments",
    [
        {"path": "C:/unsafe.docx"},
        {"template": "unsafe.dotx"},
        {"filename": "unsafe.docx"},
        {"method": "Add"},
    ],
)
def test_create_registry_rejects_all_arguments(monkeypatch, arguments):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "create_word_document",
        lambda: calls.append(()),
    )
    _, result = creation_registry_call(arguments)
    assert "takes no arguments" in result
    assert calls == []


def test_open_then_write_word_orchestration(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "open_application",
        lambda name: calls.append(("open_application", name)) or "opened",
    )
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "write_word_text",
        lambda text, mode: calls.append(("write_word_text", text, mode))
        or "written",
    )
    responses = iter([
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "function": {
                    "name": "open_application",
                    "arguments": {"name": "word"},
                }
            }],
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "function": {
                    "name": "write_word_text",
                    "arguments": {"text": "Hello", "mode": "append"},
                }
            }],
        },
        {"role": "assistant", "content": "Done."},
    ])
    assistant = Assistant(chat=lambda messages, tools: next(responses))
    assert assistant.ask("Open Word and write Hello.") == "Done."
    assert calls == [
        ("open_application", "word"),
        ("write_word_text", "Hello", "append"),
    ]


def test_failure_result_is_available_to_final_model_round(monkeypatch):
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "write_word_text",
        lambda text, mode: "Microsoft Word is not currently open.",
    )
    calls = 0

    def chat(messages, tools):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "function": {
                        "name": "write_word_text",
                        "arguments": {"text": "Hello", "mode": "append"},
                    }
                }],
            }
        assert messages[-1]["role"] == "tool"
        assert "not currently open" in messages[-1]["content"]
        return {"role": "assistant", "content": "I couldn't write it."}

    assert Assistant(chat=chat).ask("Write Hello in Word.") == "I couldn't write it."


def test_tool_log_contains_metadata_only(monkeypatch, capsys):
    adapter = install_adapter(monkeypatch)
    monkeypatch.setattr(config, "TOOL_LOG", True)
    secret = "do not log this"
    word_tool.write_word_text(secret, "append")
    output = capsys.readouterr().out
    assert adapter.calls == [(secret, "append")]
    assert "requested mode=append chars=15" in output
    assert "success outcome=write_succeeded mode=append chars=15" in output
    assert secret not in output


def test_create_tool_log_contains_no_document_data(monkeypatch, capsys):
    adapter = install_adapter(monkeypatch)
    monkeypatch.setattr(config, "TOOL_LOG", True)
    word_tool.create_word_document()
    output = capsys.readouterr().out
    assert adapter.create_calls == 1
    assert "[tool] create_word_document requested" in output
    assert "success outcome=creation_succeeded" in output


def test_prompt_preserves_word_epistemic_boundary():
    prompt = prompts.SYSTEM_PROMPT
    assert "exactly one unambiguous editable Microsoft Word document" in prompt
    assert "does not reveal the document contents" in prompt
    assert "no write was attempted" in prompt
    assert "outcome is unknown" in prompt
    assert "number of write attempts" in prompt
    assert "successful create_word_document result confirms only" in prompt
    assert "Never claim it was saved, named" in prompt
    assert "If creation is unconfirmed, do not claim success" in prompt
    assert "blank document was created and only its visibility activation" in prompt
    assert "must never claim to have performed an action" in prompt


def test_word_production_path_has_no_prohibited_calls():
    sources = inspect.getsource(adapter_module) + inspect.getsource(word_tool)
    trees = [ast.parse(inspect.getsource(adapter_module)), ast.parse(inspect.getsource(word_tool))]
    calls = []
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)

    prohibited_calls = {
        "Dispatch",
        "DispatchEx",
        "Run",
        "Open",
        "Save",
        "SaveAs",
        "send_keys",
        "type_keys",
        "kill",
        "terminate",
        "eval",
        "exec",
    }
    assert prohibited_calls.isdisjoint(calls)
    assert calls.count("Add") == 1
    assert calls.count("Activate") == 1
    for prohibited_text in (
        "application.Hwnd",
        "ActiveWindow",
        "ActiveDocument",
        "Selection",
        "pyautogui",
        "clipboard",
        "shell=True",
        "taskkill",
    ):
        assert prohibited_text not in sources
