"""Bounded latency benchmark for Celine's planning requests.

This is a measurement tool that never dispatches a Celine tool: tool results
are simulated so the model can plan another round. It posts the same payload
shape as ``ollama_client.chat`` but keeps Ollama's native timing fields.

Usage (from the project root, with Ollama running):

    python scripts/benchmark_latency.py [label]

The optional label is printed with the results so a before/after comparison
is easy to read. Keep the run short; it warms up once and is then excluded.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests  # noqa: E402

from celine.core import config, prompts  # noqa: E402
from celine.tools.registry import TOOL_SCHEMAS  # noqa: E402

# (label, user text, planned tool sequence to simulate, expect_tool)
SCENARIOS = (
    ("chat", "What is the capital of Cameroon?", (), False),
    ("time", "What time is it?", ("get_current_time",), True),
    ("open_notepad", "Open Notepad.", ("open_application",), True),
    ("write_notepad", 'Write "Hello" in Notepad.', ("write_text",), True),
    (
        "save_word",
        "Save this as Letter.docx in Documents.",
        ("save_word_document",),
        True,
    ),
    (
        "multi_word",
        'Open Word, write "Hello", and save it as Hello.docx in Documents.',
        (
            "open_application",
            "create_word_document",
            "write_word_text",
            "save_word_document",
        ),
        True,
    ),
)

SIMULATED = (
    "Simulated successful tool result for planning only. "
    "No real tool was executed."
)
REQUEST_TIMEOUT = 90


def _post(messages, tools):
    payload = {
        "model": config.MODEL,
        "messages": messages,
        "tools": tools,
        "stream": False,
        "think": False,
        "options": {
            "temperature": config.OLLAMA_TEMPERATURE,
            "num_predict": config.OLLAMA_NUM_PREDICT,
        },
    }
    started = time.perf_counter()
    response = requests.post(
        config.OLLAMA_URL, json=payload, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    return response.json(), time.perf_counter() - started


def _seconds(nanoseconds):
    return (nanoseconds or 0) / 1e9


def probe(user_text, tools):
    messages = [
        {"role": "system", "content": prompts.SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]
    calls = []
    rounds = 0
    while rounds < config.MAX_TOOL_ROUNDS:
        data, wall = _post(messages, tools)
        message = data.get("message") or {}
        calls.append(
            {
                "wall": wall,
                "prompt_count": data.get("prompt_eval_count") or 0,
                "prompt_seconds": _seconds(data.get("prompt_eval_duration")),
                "eval_count": data.get("eval_count") or 0,
                "eval_seconds": _seconds(data.get("eval_duration")),
            }
        )
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            break
        rounds += 1
        messages.append(message)
        for tool_call in tool_calls:
            name = (tool_call.get("function") or {}).get("name") or ""
            messages.append(
                {"role": "tool", "tool_name": name, "content": SIMULATED}
            )
    return calls, rounds, len(json.dumps(messages, ensure_ascii=False))


def run(label):
    print(f"CELINE LATENCY BENCHMARK  model={config.MODEL}  label={label}")
    print(f"tool_count={len(TOOL_SCHEMAS)} "
          f"system_chars={len(prompts.SYSTEM_PROMPT)} "
          f"tool_chars={len(json.dumps(TOOL_SCHEMAS, separators=(',', ':')))}")

    # Warm-up request, excluded from results.
    try:
        _post(
            [
                {"role": "system", "content": prompts.SYSTEM_PROMPT},
                {"role": "user", "content": "Reply with the single word OK."},
            ],
            TOOL_SCHEMAS,
        )
        print("warm-up complete (excluded)")
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"warm-up failed: {type(exc).__name__}: {exc}")
        return

    print()
    print(f"{'scenario':<15}{'total':>8}{'calls':>6}{'rounds':>7}"
          f"{'prefill':>9}{'eval':>8}{'tps':>7}{'ctx':>7}")
    for name, user_text, _expected, _has_tool in SCENARIOS:
        started = time.perf_counter()
        calls, rounds, ctx_chars = probe(user_text, TOOL_SCHEMAS)
        total = time.perf_counter() - started
        prompt_seconds = sum(c["prompt_seconds"] for c in calls)
        eval_seconds = sum(c["eval_seconds"] for c in calls)
        eval_tokens = sum(c["eval_count"] for c in calls)
        tps = eval_tokens / eval_seconds if eval_seconds else 0.0
        print(
            f"{name:<15}{total:>7.2f}s{len(calls):>6}{rounds:>7}"
            f"{prompt_seconds:>8.2f}s{eval_seconds:>7.2f}s"
            f"{tps:>7.1f}{ctx_chars:>7}"
        )


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    run(label)
