"""Tests for assistant orchestration. The Ollama call is faked."""

from datetime import datetime

from celine.core import prompts
from celine.core.assistant import Assistant


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


def test_prompt_limits_type_text_success_to_confirmed_action():
    prompt = prompts.SYSTEM_PROMPT
    assert "requested text was inserted or appended" in prompt
    assert "does not reveal or confirm the complete document contents" in prompt
    assert "unless a tool has actually read and returned it" in prompt
    assert "information you merely inferred" in prompt
