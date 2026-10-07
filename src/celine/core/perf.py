"""Optional performance instrumentation.

Everything here is inert unless config.PERF_LOG is True, so normal users
never see debug output and business logic stays unchanged.
"""

import time

from celine.core import config


class PerfLog:
    """Collects timing events for a single ask() call, then prints them."""

    def __init__(self, enabled=None):
        if enabled is None:
            enabled = config.PERF_LOG
        self.enabled = enabled
        self._events = []
        self._ollama_calls = 0
        self._tool_calls = 0
        self._started = None

    def start(self):
        """Begin timing the whole request."""
        if self.enabled:
            self._started = time.perf_counter()

    def now(self):
        """A timestamp to hand back to since()."""
        return time.perf_counter()

    def since(self, started):
        """Seconds elapsed since now() was called."""
        return time.perf_counter() - started

    def add_ollama_call(self, seconds):
        if not self.enabled:
            return
        self._ollama_calls += 1
        self._events.append((f"ollama_call_{self._ollama_calls}", seconds))

    def add_tool_call(self, name, seconds):
        if not self.enabled:
            return
        self._tool_calls += 1
        self._events.append((f"tool:{name}", seconds))

    def finish(self):
        """Print the report, then reset for the next request."""
        if not self.enabled or self._started is None:
            return
        total = time.perf_counter() - self._started
        for label, seconds in self._events:
            print(f"[perf] {label}={_fmt(seconds)}s")
        print(
            f"[perf] total={_fmt(total)}s "
            f"ollama_calls={self._ollama_calls} "
            f"tool_calls={self._tool_calls}"
        )
        self._events = []
        self._ollama_calls = 0
        self._tool_calls = 0
        self._started = time.perf_counter()


def _fmt(seconds):
    """Format seconds compactly: 6.42, 0.001, 11.31."""
    return str(round(seconds, 3))
