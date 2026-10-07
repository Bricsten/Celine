"""Optional live Ollama planning probe that never executes Celine tools.

Run from the project root with Ollama available:

    python scripts/probe_tool_selection.py

The script prints proposed tool names and arguments. Tool results are simulated
only to let the model plan another round; no registry function is dispatched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from celine.core import config, prompts  # noqa: E402
from celine.llm import ollama_client  # noqa: E402
from celine.tools.registry import TOOL_SCHEMAS  # noqa: E402


SCENARIOS = (
    ('Write "Hello" in Word.', ["write_word_text"]),
    ("Open Word.", ["open_application"]),
    (
        'Open Word and write "Hello".',
        ["open_application", "create_word_document", "write_word_text"],
    ),
    ("Create a blank Word document.", ["create_word_document"]),
    ("Minimize Word.", ["control_window"]),
    ('Write "Hello" in Notepad.', ["write_text"]),
)


def probe(user_text):
    messages = [
        {"role": "system", "content": prompts.SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]
    proposed = []
    for _ in range(config.MAX_TOOL_ROUNDS):
        message = ollama_client.chat(messages, TOOL_SCHEMAS)
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            break
        messages.append(message)
        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            name = function.get("name") or ""
            arguments = function.get("arguments")
            proposed.append((name, arguments))
            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": (
                    "Simulated successful tool result for planning only. "
                    "No real tool was executed."
                ),
            })
    return proposed


def main():
    print("TOOL-SELECTION PROBE: NO TOOLS WILL BE EXECUTED")
    for user_text, expected in SCENARIOS:
        proposed = probe(user_text)
        names = [name for name, _ in proposed]
        print(f"\nUser: {user_text}")
        print(f"Expected: {expected}")
        print(f"Proposed: {names}")
        for name, arguments in proposed:
            print(
                f"  {name} arguments="
                f"{json.dumps(arguments, ensure_ascii=False, sort_keys=True)}"
            )
        print(f"Result: {'PASS' if names == expected else 'REVIEW'}")


if __name__ == "__main__":
    main()
