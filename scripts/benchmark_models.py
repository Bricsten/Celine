"""Controlled benchmark for local Ollama models used with Celine.

This is a measurement tool, not part of the application: it lives outside
src/ and never modifies config.py on disk. It reuses Celine's real Ollama
client, system prompt, tool schemas and tool registry so results reflect
production behaviour.

Usage (from the project root, with Ollama running):

    python scripts/benchmark_models.py

Results are written to benchmark_results.md.
"""

import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from celine.core import config
from celine.core.assistant import Assistant
from celine.llm import ollama_client
from celine.tools import registry

MODELS = ["qwen3:4b-instruct", "llama3.2:3b", "phi4-mini"]
RUNS_PER_TEST = 3
WARMUP_PROMPT = "Reply with the single word OK."
REPORT_PATH = ROOT / "benchmark_results.md"
ANSWER_LIMIT = 400

TESTS = [
    ("A", "What is the capital of Cameroon?",
     "Answers Yaounde; no tool call"),
    ("B", "Who are you?",
     "Identifies as Celine; understands she is local"),
    ("C", "Open Microsoft Word.",
     "Does not claim Word opened; does not invent a tool"),
    ("D", "What time is it?",
     "Invokes get_current_time; uses the tool result"),
    ("E", "Explain what RAM is in two short sentences.",
     "About two short sentences"),
]

CLAIM_RE = re.compile(r"\bopened\b|\blaunched\b|\bis now open\b", re.IGNORECASE)
LOCAL_HINTS = (
    "local", "locally", "ollama", "your computer", "this machine", "terminal",
)


def make_chat(model):
    """Celine's Ollama client bound to a different model.

    config.MODEL is overridden only in memory and restored immediately,
    so src/celine/core/config.py is never changed on disk.
    """
    def chat(messages, tools):
        original = config.MODEL
        config.MODEL = model
        try:
            return ollama_client.chat(messages, tools)
        finally:
            config.MODEL = original
    return chat


def warm_up(model):
    """One trivial request, excluded from results. Returns an error or None."""
    assistant = Assistant(chat=make_chat(model))
    try:
        assistant.ask(WARMUP_PROMPT)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def strip_accents(text):
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def count_sentences(text):
    return len([p for p in re.split(r"[.!?]+", text) if p.strip()])


def unknown_tools_requested(history):
    """Tool names the model asked for that are not in the registry."""
    names = set()
    for message in history:
        if message.get("role") != "assistant":
            continue
        for tool_call in message.get("tool_calls") or []:
            function = tool_call.get("function") or {}
            name = function.get("name")
            if name and name not in registry.TOOL_REGISTRY:
                names.add(name)
    return names


def tool_expectation_ok(test_id, tool_names, unknown):
    """Did the expected tool behaviour occur for this test?"""
    if test_id == "D":
        return "get_current_time" in tool_names
    return not tool_names and not unknown


def quality_check(test_id, answer, tool_names, unknown):
    """Expected answer properties for each test."""
    text = answer or ""
    lower = text.lower()
    if test_id == "A":
        return "yaounde" in strip_accents(text).lower() and not tool_names
    if test_id == "B":
        return (
            "celine" in lower
            and any(hint in lower for hint in LOCAL_HINTS)
            and not tool_names
        )
    if test_id == "C":
        return not tool_names and not unknown and not CLAIM_RE.search(text)
    if test_id == "D":
        return "get_current_time" in tool_names
    if test_id == "E":
        return count_sentences(text) == 2
    return False


def run_case(model, test_id, prompt, run_number):
    """One isolated conversation: fresh history, one measured request."""
    assistant = Assistant(chat=make_chat(model))
    started = time.perf_counter()
    error = None
    try:
        answer = assistant.ask(prompt)
    except Exception as exc:
        answer = ""
        error = f"{type(exc).__name__}: {exc}"
    total = time.perf_counter() - started

    history = assistant.history
    tool_names = [
        message.get("tool_name") or ""
        for message in history if message.get("role") == "tool"
    ]
    unknown = unknown_tools_requested(history)
    tool_ok = tool_expectation_ok(test_id, tool_names, unknown)
    check_ok = error is None and quality_check(
        test_id, answer, tool_names, unknown
    )

    return {
        "model": model,
        "test": test_id,
        "run": run_number,
        "total": total,
        # One assistant message is appended per Ollama call.
        "ollama_calls": sum(
            1 for message in history if message.get("role") == "assistant"
        ),
        "tool_calls": len(tool_names),
        "tool_ok": tool_ok,
        "check_ok": check_ok,
        "answer": answer,
        "error": error,
    }


def average(values):
    return sum(values) / len(values) if values else None


def summarise(records, model):
    mine = [r for r in records if r["model"] == model]
    normal = [
        r["total"] for r in mine
        if r["test"] in ("A", "B", "C", "E") and r["error"] is None
    ]
    tool_runs = [r for r in mine if r["test"] == "D" and r["error"] is None]
    tool_ok = sum(1 for r in mine if r["test"] == "D" and r["tool_ok"])
    tool_total = sum(1 for r in mine if r["test"] == "D")
    return {
        "avg_normal": average(normal),
        "avg_tool": average([r["total"] for r in tool_runs]),
        "tool_success": f"{tool_ok}/{tool_total}" if tool_total else "n/a",
        "tool_success_rate": (tool_ok / tool_total) if tool_total else None,
        "failures": sum(1 for r in mine if not r["check_ok"]),
        "errors": sum(1 for r in mine if r["error"]),
        "runs": len(mine),
    }


def fmt_seconds(value):
    return f"{value:.2f}" if value is not None else "n/a"


def escape_cell(text, limit=ANSWER_LIMIT):
    flat = " ".join((text or "").split())
    flat = flat.replace("|", "\\|")
    if len(flat) > limit:
        flat = flat[:limit] + "..."
    return flat


def comparison_lines(records, unavailable):
    lines = ["## Comparison", ""]
    available = [m for m in MODELS if m not in unavailable]
    if not available:
        lines.append("No model completed the benchmark.")
        return lines

    stats = {m: summarise(records, m) for m in available}

    fastest_normal = min(
        available,
        key=lambda m: stats[m]["avg_normal"] if stats[m]["avg_normal"] else 1e9,
    )
    lines.append(
        f"- Lowest average normal-response latency: {fastest_normal} "
        f"({fmt_seconds(stats[fastest_normal]['avg_normal'])}s)"
    )

    with_tool = [m for m in available if stats[m]["avg_tool"] is not None]
    if with_tool:
        fastest_tool = min(with_tool, key=lambda m: stats[m]["avg_tool"])
        lines.append(
            f"- Lowest average time-tool latency (TEST D): {fastest_tool} "
            f"({fmt_seconds(stats[fastest_tool]['avg_tool'])}s)"
        )

    success_bits = [
        f"{m} {stats[m]['tool_success']}" for m in available
    ]
    lines.append("- Tool-call success on TEST D: " + "; ".join(success_bits))

    failure_bits = [
        f"{m} {stats[m]['failures']}/{stats[m]['runs']}" for m in available
    ]
    lines.append("- Obvious instruction failures: " + "; ".join(failure_bits))

    lines.append("")
    lines.append(
        "These are raw observations from "
        f"{RUNS_PER_TEST} runs per prompt on one machine. Speed alone does "
        "not establish overall quality, so no overall \"best model\" is "
        "declared here. Review the recorded answers above for tone, honesty "
        "and instruction-following before deciding."
    )
    return lines


def write_report(records, unavailable):
    lines = [
        "# Celine model benchmark",
        "",
        f"- Date: {datetime.now():%Y-%m-%d %H:%M}",
        f"- Models: {', '.join(MODELS)}",
        f"- Runs per test: {RUNS_PER_TEST} "
        "(plus one warm-up per model, excluded)",
        "- Conversation history is fresh for every test case",
        "- Only final answer text is recorded (no hidden reasoning)",
        "",
        "## Prompts",
        "",
        "| Test | Prompt | Expected |",
        "|------|--------|----------|",
    ]
    for test_id, prompt, expected in TESTS:
        lines.append(f"| {test_id} | {escape_cell(prompt, 120)} | {expected} |")

    lines += ["", "## Summary", ""]
    lines.append(
        "| Model | Avg normal (A/B/C/E) | Avg time-tool (D) | "
        "Tool success (D) | Instruction failures | Errors |"
    )
    lines.append("|---|---|---|---|---|---|")
    for model in MODELS:
        if model in unavailable:
            lines.append(f"| {model} | - | - | - | - | unavailable |")
            continue
        s = summarise(records, model)
        lines.append(
            f"| {model} | {fmt_seconds(s['avg_normal'])}s "
            f"| {fmt_seconds(s['avg_tool'])}s "
            f"| {s['tool_success']} "
            f"| {s['failures']}/{s['runs']} "
            f"| {s['errors']} |"
        )

    lines += ["", "## Detailed results", ""]
    lines.append(
        "Tool OK = expected tool behaviour occurred. "
        "Check = expected answer property held for that test."
    )
    for model in MODELS:
        lines += ["", f"### {model}", ""]
        if model in unavailable:
            lines.append(f"Skipped: {unavailable[model]}")
            continue
        lines += [
            "",
            "| Test | Run | Total (s) | Ollama calls | Tool calls "
            "| Tool OK | Check | Answer |",
            "|------|-----|-----------|--------------|------------ "
            "|---------|-------|--------|",
        ]
        for r in [x for x in records if x["model"] == model]:
            answer = r["answer"] if r["error"] is None else f"ERROR: {r['error']}"
            lines.append(
                f"| {r['test']} | {r['run']} | {r['total']:.2f} "
                f"| {r['ollama_calls']} | {r['tool_calls']} "
                f"| {'yes' if r['tool_ok'] else 'no'} "
                f"| {'PASS' if r['check_ok'] else 'FAIL'} "
                f"| {escape_cell(answer)} |"
            )

    lines += [""] + comparison_lines(records, unavailable) + [""]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return REPORT_PATH


def main():
    print(f"Celine model benchmark ({datetime.now():%Y-%m-%d %H:%M})")
    records = []
    unavailable = {}

    for model in MODELS:
        print(f"\n=== {model} ===")
        warm_error = warm_up(model)
        if warm_error:
            unavailable[model] = warm_error
            print(f"  unavailable, skipping: {warm_error}")
            continue
        print("  warmed up (excluded)")

        for test_id, prompt, _expected in TESTS:
            for run_number in range(1, RUNS_PER_TEST + 1):
                record = run_case(model, test_id, prompt, run_number)
                records.append(record)
                status = "PASS" if record["check_ok"] else "FAIL"
                print(
                    f"  {test_id} run {run_number}: "
                    f"{record['total']:.2f}s "
                    f"calls={record['ollama_calls']} "
                    f"tools={record['tool_calls']} {status}"
                )

    print("\nSummary:")
    for model in MODELS:
        if model in unavailable:
            print(f"  {model}: unavailable")
            continue
        s = summarise(records, model)
        print(
            f"  {model}: normal={fmt_seconds(s['avg_normal'])}s "
            f"time-tool={fmt_seconds(s['avg_tool'])}s "
            f"tool={s['tool_success']} "
            f"instruction-failures={s['failures']}/{s['runs']}"
        )

    path = write_report(records, unavailable)
    print(f"\nReport written to {path}")


if __name__ == "__main__":
    main()
