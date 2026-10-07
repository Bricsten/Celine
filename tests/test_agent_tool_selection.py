"""Planning-policy and fake orchestration tests; no live apps or LLM."""

from celine.core import prompts
from celine.core.assistant import Assistant
from celine.tools import registry


class FakeChat:
    def __init__(self, *responses):
        self.responses = list(responses)

    def __call__(self, messages, tools):
        return self.responses.pop(0)


def tool_request(name, arguments):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "function": {"name": name, "arguments": arguments}
        }],
    }


def install_recording_tools(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "open_application",
        lambda name: calls.append(("open_application", name)) or "opened",
    )
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "control_window",
        lambda application, action: calls.append(
            ("control_window", application, action)
        ) or "controlled",
    )
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "write_text",
        lambda application, text, mode: calls.append(
            ("write_text", application, text, mode)
        ) or "written",
    )
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "write_word_text",
        lambda text, mode: calls.append(
            ("write_word_text", text, mode)
        ) or "written",
    )
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "create_word_document",
        lambda: calls.append(("create_word_document",)) or "created",
    )
    return calls


def test_word_write_plan_uses_write_tool_only(monkeypatch):
    calls = install_recording_tools(monkeypatch)
    chat = FakeChat(
        tool_request(
            "write_word_text",
            {"text": "Hello", "mode": "append"},
        ),
        {"role": "assistant", "content": "Done."},
    )

    Assistant(chat=chat).ask('Write "Hello" in Word.')

    assert calls == [("write_word_text", "Hello", "append")]


def test_explicit_open_word_plan_uses_launcher_only(monkeypatch):
    calls = install_recording_tools(monkeypatch)
    chat = FakeChat(
        tool_request("open_application", {"name": "word"}),
        {"role": "assistant", "content": "Opened."},
    )

    Assistant(chat=chat).ask("Open Word.")

    assert calls == [("open_application", "word")]


def test_explicit_open_then_write_plan_preserves_order(monkeypatch):
    calls = install_recording_tools(monkeypatch)
    chat = FakeChat(
        tool_request("open_application", {"name": "word"}),
        tool_request(
            "write_word_text",
            {"text": "Hello", "mode": "append"},
        ),
        {"role": "assistant", "content": "Done."},
    )

    Assistant(chat=chat).ask('Open Word and write "Hello".')

    assert calls == [
        ("open_application", "word"),
        ("write_word_text", "Hello", "append"),
    ]


def test_minimize_word_plan_uses_window_tool_only(monkeypatch):
    calls = install_recording_tools(monkeypatch)
    chat = FakeChat(
        tool_request(
            "control_window",
            {"application": "word", "action": "minimize"},
        ),
        {"role": "assistant", "content": "Minimised."},
    )

    Assistant(chat=chat).ask("Minimize Word.")

    assert calls == [("control_window", "word", "minimize")]


def test_notepad_write_plan_uses_write_tool_only(monkeypatch):
    calls = install_recording_tools(monkeypatch)
    chat = FakeChat(
        tool_request(
            "write_text",
            {"application": "notepad", "text": "Hello", "mode": "append"},
        ),
        {"role": "assistant", "content": "Done."},
    )

    Assistant(chat=chat).ask('Write "Hello" in Notepad.')

    assert calls == [("write_text", "notepad", "Hello", "append")]


def test_open_then_create_word_document_orchestration(monkeypatch):
    calls = install_recording_tools(monkeypatch)
    chat = FakeChat(
        tool_request("open_application", {"name": "word"}),
        tool_request("create_word_document", {}),
        {"role": "assistant", "content": "Created."},
    )

    Assistant(chat=chat).ask("Open Word and create a blank document.")

    assert calls == [
        ("open_application", "word"),
        ("create_word_document",),
    ]


def test_create_then_write_word_orchestration(monkeypatch):
    calls = install_recording_tools(monkeypatch)
    chat = FakeChat(
        tool_request("create_word_document", {}),
        tool_request(
            "write_word_text",
            {"text": "Hello", "mode": "append"},
        ),
        {"role": "assistant", "content": "Done."},
    )

    Assistant(chat=chat).ask("Create a blank Word document and write Hello.")

    assert calls == [
        ("create_word_document",),
        ("write_word_text", "Hello", "append"),
    ]


def test_open_create_then_write_word_orchestration(monkeypatch):
    calls = install_recording_tools(monkeypatch)
    chat = FakeChat(
        tool_request("open_application", {"name": "word"}),
        tool_request("create_word_document", {}),
        tool_request(
            "write_word_text",
            {"text": "Hello", "mode": "append"},
        ),
        {"role": "assistant", "content": "Done."},
    )

    Assistant(chat=chat).ask('Open Word and write "Hello".')

    assert calls == [
        ("open_application", "word"),
        ("create_word_document",),
        ("write_word_text", "Hello", "append"),
    ]


def test_write_no_document_then_create_and_retry_orchestration(monkeypatch):
    calls = install_recording_tools(monkeypatch)
    chat = FakeChat(
        tool_request(
            "write_word_text",
            {"text": "Hello", "mode": "append"},
        ),
        tool_request("create_word_document", {}),
        tool_request(
            "write_word_text",
            {"text": "Hello", "mode": "append"},
        ),
        {"role": "assistant", "content": "Done."},
    )

    Assistant(chat=chat).ask('Write "Hello" in Word.')

    assert calls == [
        ("write_word_text", "Hello", "append"),
        ("create_word_document",),
        ("write_word_text", "Hello", "append"),
    ]


def test_write_closed_word_open_create_then_retry_orchestration(monkeypatch):
    calls = install_recording_tools(monkeypatch)
    chat = FakeChat(
        tool_request(
            "write_word_text",
            {"text": "Hello", "mode": "append"},
        ),
        tool_request("open_application", {"name": "word"}),
        tool_request("create_word_document", {}),
        tool_request(
            "write_word_text",
            {"text": "Hello", "mode": "append"},
        ),
        {"role": "assistant", "content": "Done."},
    )

    Assistant(chat=chat).ask('Write "Hello" in Word.')

    assert calls == [
        ("write_word_text", "Hello", "append"),
        ("open_application", "word"),
        ("create_word_document",),
        ("write_word_text", "Hello", "append"),
    ]


def test_prompt_requires_minimum_necessary_tool_sequence():
    prompt = prompts.SYSTEM_PROMPT
    assert "Use the minimum necessary tool sequence" in prompt
    assert "Do not open an application merely because" in prompt
    assert "use the dedicated action tool first" in prompt
    assert "explicitly asks to open, launch, or start" in prompt
    assert "does not itself request opening it" in prompt
    assert "call write_word_text first" in prompt
    assert "create_word_document and then retry write_word_text" in prompt


def test_action_tool_descriptions_discourage_implicit_launching():
    descriptions = {
        item["function"]["name"]: item["function"]["description"]
        for item in registry.TOOL_SCHEMAS
    }
    assert "Use only to launch" in descriptions["open_application"]
    assert "only asked to act inside" in descriptions["open_application"]
    assert "window actions only" in descriptions["control_window"]
    assert "do not launch an application first" in descriptions[
        "control_window"
    ]
    assert "Use directly" in descriptions["write_text"]
    assert "do not launch Notepad first" in descriptions["write_text"]
    assert "Use directly" in descriptions["write_word_text"]
    assert "does not launch Word" in descriptions["write_word_text"]
    assert "no document is open" in descriptions["write_word_text"]
    assert "blank unsaved document" in descriptions["create_word_document"]
    assert "Does not launch Word or save" in descriptions[
        "create_word_document"
    ]
