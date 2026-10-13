"""Tests for assistant orchestration. The Ollama call is faked."""

from datetime import datetime

import pytest

from celine.core import config, prompts
from celine.core.assistant import Assistant, _drop_incomplete_tool_turns
from celine.llm.ollama_client import OllamaTimeoutError
from celine.tools import registry


class FakeChat:
    """Stands in for ollama_client.chat so no server is needed."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0
        self.seen_tools = None

    def __call__(self, messages, tools):
        self.calls += 1
        self.seen_tools = tools
        return self.responses.pop(0)


def test_normal_response_does_not_require_a_tool():
    chat = FakeChat({"role": "assistant", "content": "Hello there."})
    assistant = Assistant(chat=chat)

    reply = assistant.ask("Say hello.")

    assert reply == "Hello there."
    assert chat.calls == 1
    roles = [m["role"] for m in assistant.history]
    assert roles == ["system", "user", "assistant"]


def test_tool_result_is_returned_into_the_conversation():
    tool_request = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"function": {"name": "get_current_time", "arguments": {}}}
        ],
    }
    final_answer = {"role": "assistant", "content": "It is 03:48."}
    chat = FakeChat(tool_request, final_answer)
    assistant = Assistant(chat=chat)

    reply = assistant.ask("What time is it?")

    assert reply == "It is 03:48."
    assert chat.calls == 2
    roles = [m["role"] for m in assistant.history]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]

    tool_message = assistant.history[3]
    assert tool_message["tool_name"] == "get_current_time"
    datetime.strptime(tool_message["content"], "%Y-%m-%d %H:%M:%S")

    schema_names = [t["function"]["name"] for t in chat.seen_tools]
    assert "get_current_time" in schema_names


def test_prompt_limits_write_text_success_to_confirmed_action():
    prompt = prompts.SYSTEM_PROMPT
    assert "requested text was appended, optionally after a new line" in prompt
    assert "does not reveal or confirm the complete document contents" in prompt
    assert "unless a tool has actually read and returned it" in prompt
    assert "information you merely inferred" in prompt


def test_timeout_before_tool_selection_is_classified_without_tool_result():
    def timeout_chat(messages, tools):
        raise OllamaTimeoutError("timed out")

    assistant = Assistant(chat=timeout_chat)
    with pytest.raises(OllamaTimeoutError) as caught:
        assistant.ask("Save the document.")
    assert caught.value.after_tool_result is False
    assert caught.value.tool_results == ()
    assert not any(m.get("role") == "tool" for m in assistant.history)


def test_timeout_after_mutation_does_not_duplicate_tool_call(monkeypatch):
    save_calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "save_word_document",
        lambda filename, folder: save_calls.append((filename, folder))
        or "Microsoft Word document saved successfully.",
    )
    responses = iter([
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "function": {
                    "name": "save_word_document",
                    "arguments": {
                        "filename": "Reliable.docx",
                        "folder": "documents",
                    },
                }
            }],
        },
        OllamaTimeoutError("timed out"),
    ])

    def chat(messages, tools):
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    with pytest.raises(OllamaTimeoutError) as caught:
        Assistant(chat=chat).ask("Save this as Reliable.docx in Documents.")
    assert save_calls == [("Reliable.docx", "documents")]
    assert caught.value.after_tool_result is True
    assert caught.value.tool_results == ((
        "save_word_document",
        "Microsoft Word document saved successfully.",
    ),)


def test_prior_history_is_bounded_by_complete_turns(monkeypatch):
    monkeypatch.setattr(config, "MAX_HISTORY_TURNS", 2)
    monkeypatch.setattr(config, "MAX_HISTORY_CHARS", 10_000)
    seen = []

    def chat(messages, tools):
        seen.extend(messages)
        return {"role": "assistant", "content": "Current reply"}

    assistant = Assistant(chat=chat)
    for number in range(4):
        assistant.history.extend([
            {"role": "user", "content": f"old user {number}"},
            {"role": "assistant", "content": f"old answer {number}"},
        ])
    assistant.ask("current user")
    contents = [message.get("content") for message in seen]
    assert "old user 0" not in contents
    assert "old user 1" not in contents
    assert "old user 2" in contents
    assert "old user 3" in contents
    assert contents[-1] == "current user"


def test_oversized_prior_turn_is_dropped_whole(monkeypatch):
    monkeypatch.setattr(config, "MAX_HISTORY_TURNS", 6)
    monkeypatch.setattr(config, "MAX_HISTORY_CHARS", 100)
    seen = []

    def chat(messages, tools):
        seen.extend(messages)
        return {"role": "assistant", "content": "Done"}

    assistant = Assistant(chat=chat)
    assistant.history.extend([
        {"role": "user", "content": "private prior text " * 20},
        {"role": "assistant", "content": "prior result"},
    ])
    assistant.ask("current")
    assert [message["role"] for message in seen] == ["system", "user"]
    assert seen[-1]["content"] == "current"


def test_incomplete_tool_sequence_is_not_sent_to_the_model():
    seen = []

    def chat(messages, tools):
        seen.extend(messages)
        return {"role": "assistant", "content": "Hi."}

    assistant = Assistant(chat=chat)
    assistant.history.extend([
        {"role": "user", "content": "old request"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "get_current_time", "arguments": {}}}
            ],
        },
    ])
    assistant.ask("current request")

    # The orphaned tool request is dropped, but both user turns survive.
    assert not any(message.get("tool_calls") for message in seen)
    user_texts = [
        message["content"] for message in seen if message["role"] == "user"
    ]
    assert "current request" in user_texts
    assert "old request" in user_texts


def test_drop_incomplete_tool_turns_keeps_complete_exchanges():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "what time"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "get_current_time", "arguments": {}}}
            ],
        },
        {"role": "tool", "tool_name": "get_current_time", "content": "03:48"},
        {"role": "assistant", "content": "It is 03:48."},
    ]
    assert _drop_incomplete_tool_turns(messages) == messages


def test_drop_incomplete_tool_turns_removes_partial_and_stray_results():
    partial = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "do two things"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "one", "arguments": {}}},
                {"function": {"name": "two", "arguments": {}}},
            ],
        },
        {"role": "tool", "tool_name": "one", "content": "done"},
        {"role": "assistant", "content": "finished"},
    ]
    assert _drop_incomplete_tool_turns(partial) == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "do two things"},
        {"role": "assistant", "content": "finished"},
    ]

    stray = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "tool", "tool_name": "orphan", "content": "orphan"},
    ]
    assert _drop_incomplete_tool_turns(stray) == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]
