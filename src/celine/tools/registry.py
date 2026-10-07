"""Fixed, explicit whitelist of tools Celine is allowed to run.

No eval, no dynamic imports, no shell execution. The model can only ask
for a tool by name; nothing outside TOOL_REGISTRY will ever run.
"""

import json

from celine.tools.system_time import get_current_time
from celine.tools.text_input import APPROVED_MODES, write_text
from celine.tools.window_control import control_window
from celine.tools.windows_apps import normalize_name, open_application

# Tool registry: the ONLY functions Celine is ever allowed to run.
# The model asks for a tool by name; nothing not listed here can execute.
TOOL_REGISTRY = {
    "get_current_time": get_current_time,
    "open_application": open_application,
    "control_window": control_window,
    "write_text": write_text,
}

# Tools that accept a JSON object of arguments. Every other tool must be
# called with no arguments. Arguments are passed as keyword arguments only
# after structural validation, so a tool only ever sees exactly the
# keywords declared here; missing or extra names are rejected first.
TOOL_ARGUMENTS = {
    "open_application": frozenset({"name"}),
    "control_window": frozenset({"application", "action"}),
    "write_text": frozenset({"application", "text", "mode"}),
}

TOOL_ARGUMENT_TYPES = {
    "open_application": {"name": str},
    "control_window": {"application": str, "action": str},
    "write_text": {"application": str, "text": str, "mode": str},
}

# Tool schemas: a JSON description of each tool, sent to Ollama so the
# model knows which tools exist, what they do, and what arguments they take.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": (
                "Return the current local system time as a string. "
                "Takes no arguments."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": (
                "Open one approved Windows application by name. "
                "Approved names: notepad, calculator, word, file_explorer. "
                "Takes a single string argument: name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "The approved application name, "
                            "e.g. 'notepad'."
                        ),
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_window",
            "description": (
                "Minimize, restore, focus, or gracefully close the visible "
                "top-level window of one approved Windows application. "
                "Approved applications: notepad, calculator, word, "
                "file_explorer. Approved actions: minimize, restore, focus, "
                "close."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "application": {"type": "string"},
                    "action": {"type": "string"},
                },
                "required": ["application", "action"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_text",
            "description": (
                "Write plain text to the editable document of an already-"
                "running Notepad. Use append for normal writing, or new_line "
                "to add exactly one line break before the text when the "
                "document is non-empty. This tool does not open, read, or "
                "save the application."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "application": {"type": "string"},
                    "text": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["append", "new_line"],
                    },
                },
                "required": ["application", "text", "mode"],
                "additionalProperties": False,
            },
        },
    },
]


def _bad_arguments(name, reason):
    return (
        f"Error: bad arguments for {name} ({reason}). "
        "Nothing was executed."
    )


def run_tool_call(tool_call):
    """Validate one tool call from the model, then run it if allowed.

    Returns (tool_name, result_text). Only functions explicitly present
    in TOOL_REGISTRY may run; anything else is rejected safely.
    """
    name = ""
    arguments = None
    if isinstance(tool_call, dict):
        function = tool_call.get("function")
        if isinstance(function, dict):
            name = function.get("name") or ""
            arguments = function.get("arguments")

    if name not in TOOL_REGISTRY:
        return name, (
            f"Error: '{name}' is not a registered tool. "
            "Nothing was executed."
        )

    if name not in TOOL_ARGUMENTS:
        # Every other tool takes no arguments; reject anything else.
        if isinstance(arguments, str):
            arguments = arguments.strip()
        if arguments not in (None, {}, "", "{}"):
            return name, (
                f"Error: {name} takes no arguments. Nothing was executed."
            )
        try:
            return name, str(TOOL_REGISTRY[name]())
        except Exception as exc:
            return name, f"Error: tool {name} failed ({exc})."

    # Argument-taking tool: arguments must be a single JSON object.
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            return name, _bad_arguments(name, "arguments must be a JSON object")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return name, _bad_arguments(name, "arguments must be a JSON object")

    expected = TOOL_ARGUMENTS[name]
    supplied = frozenset(arguments)
    missing = sorted(expected - supplied)
    extra = sorted(supplied - expected, key=str)
    if missing:
        return name, _bad_arguments(
            name, "missing required arguments: " + ", ".join(missing)
        )
    if extra:
        return name, _bad_arguments(
            name, "unexpected arguments: " + ", ".join(map(str, extra))
        )

    for argument, expected_type in TOOL_ARGUMENT_TYPES[name].items():
        if not isinstance(arguments[argument], expected_type):
            return name, _bad_arguments(
                name, f"argument '{argument}' must be a string"
            )

    if (
        name == "write_text"
        and normalize_name(arguments["application"]) != "notepad"
    ):
        return name, _bad_arguments(
            name, "write_text supports only the notepad application"
        )

    if name == "write_text" and arguments["mode"] not in APPROVED_MODES:
        return name, _bad_arguments(
            name, "mode must be one of: " + ", ".join(APPROVED_MODES)
        )

    try:
        return name, str(TOOL_REGISTRY[name](**arguments))
    except TypeError as exc:
        return name, _bad_arguments(name, str(exc))
    except Exception as exc:
        return name, f"Error: tool {name} failed ({exc})."
