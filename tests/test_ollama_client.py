"""Tests for Ollama request construction and error classification."""

import pytest
import requests

from celine.llm import ollama_client


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"role": "assistant", "content": "Done."}}


def test_chat_disables_thinking_and_preserves_tools(monkeypatch):
    seen = {}

    def fake_post(url, *, json, timeout):
        seen.update(url=url, payload=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(ollama_client.requests, "post", fake_post)
    tools = [{"type": "function", "function": {"name": "safe_tool"}}]
    result = ollama_client.chat(
        [{"role": "user", "content": "Use the safe tool."}],
        tools,
    )
    assert result["content"] == "Done."
    assert seen["payload"]["think"] is False
    assert seen["payload"]["tools"] is tools
    assert seen["payload"]["stream"] is False
    assert seen["payload"]["keep_alive"] == ollama_client.config.OLLAMA_KEEP_ALIVE
    assert seen["payload"]["options"] == {
        "temperature": 0,
        "num_predict": 128,
    }


def test_timeout_has_a_distinct_exception(monkeypatch):
    def fake_post(*args, **kwargs):
        raise requests.exceptions.ReadTimeout("deadline reached")

    monkeypatch.setattr(ollama_client.requests, "post", fake_post)
    with pytest.raises(ollama_client.OllamaTimeoutError) as caught:
        ollama_client.chat([], [])
    assert caught.value.is_timeout is True
    assert caught.value.after_tool_result is False
    assert caught.value.tool_results == ()
