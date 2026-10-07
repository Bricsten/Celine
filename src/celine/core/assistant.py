"""Conversation history and tool-round orchestration.

No HTTP details live here: the Ollama call is injected as ``chat``,
which must accept ``(messages, tools)`` and return Ollama's message dict.
Timing is delegated to the optional PerfLog (silent unless config.PERF_LOG).
"""

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
        self.history.append({"role": "user", "content": user_text})

        for _ in range(config.MAX_TOOL_ROUNDS):
            message = self._call_model(perf)

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
                self.history.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": result,
                })

            # Loop sends the updated history back to the model.

        # Too many tool rounds; ask once more for a plain final reply.
        message = self._call_model(perf)
        reply = message.get("content") or ""
        self.history.append({"role": "assistant", "content": reply})
        perf.finish()
        return reply

    def _call_model(self, perf):
        """One Ollama round-trip, timed by the perf log."""
        started = perf.now()
        message = self._chat(self.history, registry.TOOL_SCHEMAS)
        perf.add_ollama_call(perf.since(started))
        return message
