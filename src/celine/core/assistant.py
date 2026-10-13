"""Conversation history and tool-round orchestration.

No HTTP details live here: the Ollama call is injected as ``chat``,
which must accept ``(messages, tools)`` and return Ollama's message dict.
Timing is delegated to the optional PerfLog (silent unless config.PERF_LOG).
"""

import json

from celine.core import config, prompts
from celine.core.perf import PerfLog
from celine.tools import registry


class Assistant:
    """Holds one conversation and drives the tool-call rounds."""

    def __init__(self, chat):
        # Injected so tests can fake the LLM boundary (no server needed).
        self._chat = chat
        # Conversation history lives only in this instance (memory only).
        self.history = [
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
        ]

    def ask(self, user_text):
        """Chat with the model, run any tools it requests, return the reply."""
        perf = PerfLog()
        perf.start()
        self._trim_history()
        self.history.append({"role": "user", "content": user_text})
        tool_results = []

        for round_number in range(1, config.MAX_TOOL_ROUNDS + 1):
            message = self._call_model(perf, round_number, tool_results)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                reply = message.get("content") or ""
                self.history.append({"role": "assistant", "content": reply})
                perf.finish()
                return reply

            # Record the model's own tool request in the history.
            self.history.append(message)

            # Run each requested tool and record the result with role "tool".
            for tool_call in tool_calls:
                started = perf.now()
                name, result = registry.run_tool_call(tool_call)
                perf.add_tool_call(name, perf.since(started))
                tool_results.append((name, result))
                self.history.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": result,
                })

            # Loop sends the updated history back to the model.

        # Too many tool rounds; ask once more for a plain final reply.
        message = self._call_model(
            perf,
            config.MAX_TOOL_ROUNDS + 1,
            tool_results,
        )
        reply = message.get("content") or ""
        self.history.append({"role": "assistant", "content": reply})
        perf.finish()
        return reply

    def _call_model(self, perf, round_number, tool_results):
        """One Ollama round-trip, timed by the perf log."""
        started = perf.now()
        message_count = len(self.history)
        message_chars = _approx_chars(self.history)
        tool_count = len(registry.TOOL_SCHEMAS)
        tool_chars = _approx_chars(registry.TOOL_SCHEMAS)
        try:
            message = self._chat(self.history, registry.TOOL_SCHEMAS)
        except Exception as exc:
            timed_out = bool(getattr(exc, "is_timeout", False))
            if timed_out:
                exc.after_tool_result = bool(tool_results)
                exc.tool_results = tuple(tool_results)
            perf.add_ollama_call(
                perf.since(started),
                round_number=round_number,
                message_count=message_count,
                message_chars=message_chars,
                tool_count=tool_count,
                tool_chars=tool_chars,
                after_tool_result=bool(tool_results),
                timed_out=timed_out,
            )
            perf.finish()
            raise
        perf.add_ollama_call(
            perf.since(started),
            round_number=round_number,
            message_count=message_count,
            message_chars=message_chars,
            tool_count=tool_count,
            tool_chars=tool_chars,
            after_tool_result=bool(tool_results),
            timed_out=False,
        )
        return message

    def _trim_history(self):
        """Keep only recent complete turns within fixed count/size limits."""
        if len(self.history) <= 1:
            return

        turns = []
        current = []
        for message in self.history[1:]:
            if message.get("role") == "user":
                if current:
                    turns.append(current)
                current = [message]
            elif current:
                current.append(message)
        if current:
            turns.append(current)

        kept = []
        kept_chars = 0
        for turn in reversed(turns[-config.MAX_HISTORY_TURNS:]):
            turn_chars = _approx_chars(turn)
            if kept_chars + turn_chars > config.MAX_HISTORY_CHARS:
                break
            kept.append(turn)
            kept_chars += turn_chars
        kept.reverse()
        rebuilt = [self.history[0]] + [
            message for turn in kept for message in turn
        ]
        # A crash or interrupt between a tool request and its results must not
        # leave a half-finished exchange in the next model request.
        self.history = _drop_incomplete_tool_turns(rebuilt)


def _drop_incomplete_tool_turns(messages):
    """Remove tool requests without their matching results (and strays)."""
    cleaned = []
    index = 0
    total = len(messages)
    while index < total:
        message = messages[index]
        role = message.get("role")
        if role == "tool":
            # A tool result with no owning request is unusable context.
            index += 1
            continue
        tool_calls = message.get("tool_calls") or []
        if role == "assistant" and tool_calls:
            end = index + 1
            while end < total and messages[end].get("role") == "tool":
                end += 1
            if end - (index + 1) < len(tool_calls):
                index = end
                continue
            # Keep exactly one result per request; any surplus is a stray.
            stop = index + 1 + len(tool_calls)
            cleaned.extend(messages[index:stop])
            index = stop
            continue
        cleaned.append(message)
        index += 1
    return cleaned


def _approx_chars(value):
    """Measure serialized context without logging its private contents."""
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
