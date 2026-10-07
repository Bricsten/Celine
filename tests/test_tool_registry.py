"""Tests for the fixed tool registry. No Ollama server required."""

from datetime import datetime

from celine.tools import registry


def test_registered_time_tool_executes():
    name, result = registry.run_tool_call(
        {"function": {"name": "get_current_time", "arguments": {}}}
    )
    assert name == "get_current_time"
    parsed = datetime.strptime(result, "%Y-%m-%d %H:%M:%S")
    assert parsed.year >= 2020


def test_unknown_tool_is_rejected():
    name, result = registry.run_tool_call(
        {"function": {"name": "delete_everything", "arguments": {}}}
    )
    assert name == "delete_everything"
    assert "not a registered tool" in result
    assert "delete_everything" not in registry.TOOL_REGISTRY


def test_time_tool_rejects_unexpected_arguments():
    name, result = registry.run_tool_call(
        {"function": {"name": "get_current_time", "arguments": {"zone": "UTC"}}}
    )
    assert name == "get_current_time"
    assert "takes no arguments" in result
