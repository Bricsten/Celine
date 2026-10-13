"""Terminal error-reporting tests; no Ollama or tools are invoked."""

from celine import main as main_module
from celine.llm.ollama_client import OllamaTimeoutError


def run_main_with_timeout(monkeypatch, error, capsys):
    class FakeAssistant:
        def __init__(self, chat):
            pass

        def ask(self, user_text):
            raise error

    inputs = iter(["request", "quit"])
    monkeypatch.setattr(main_module, "Assistant", FakeAssistant)
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    main_module.main()
    return capsys.readouterr().out


def test_timeout_before_selection_reports_no_tool_operation(monkeypatch, capsys):
    output = run_main_with_timeout(
        monkeypatch,
        OllamaTimeoutError("deadline"),
        capsys,
    )
    assert "timed out before any tool was selected" in output
    assert "No tool operation was performed" in output


def test_timeout_after_tool_reports_sanitized_result_without_retry(
    monkeypatch,
    capsys,
):
    error = OllamaTimeoutError("deadline")
    error.after_tool_result = True
    error.tool_results = ((
        "save_word_document",
        "The Word save operation could not be confirmed.",
    ),)
    output = run_main_with_timeout(monkeypatch, error, capsys)
    assert "timed out after a tool result was recorded" in output
    assert "The Word save operation could not be confirmed" in output
    assert "No automatic retry was performed" in output
