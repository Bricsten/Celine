"""Fixed, explicit whitelist of tools Celine is allowed to run.

No eval, no dynamic imports, no shell execution. The model can only ask
for a tool by name; nothing outside TOOL_REGISTRY will ever run.
"""

import json

from celine.tools.system_time import get_current_time
from celine.tools.text_input import APPROVED_MODES, write_text
from celine.tools.window_control import control_window
from celine.tools.windows_apps import normalize_name, open_application
from celine.tools.word import (
    add_word_block,
    create_word_document,
    save_word_document,
    write_word_text,
)
from celine.tools.word.adapter import (
    APPROVED_WORD_ALIGNMENTS,
    APPROVED_WORD_MODES,
    APPROVED_WORD_STYLES,
)
from celine.tools.word.folders import APPROVED_SAVE_FOLDERS

# Tool registry: the ONLY functions Celine is ever allowed to run.
# The model asks for a tool by name; nothing not listed here can execute.
TOOL_REGISTRY = {
    "get_current_time": get_current_time,
    "open_application": open_application,
    "control_window": control_window,
    "write_text": write_text,
    "write_word_text": write_word_text,
    "create_word_document": create_word_document,
    "save_word_document": save_word_document,
    "add_word_block": add_word_block,
}

# Tools that accept a JSON object of arguments. Every other tool must be
# called with no arguments. Arguments are passed as keyword arguments only
# after structural validation, so a tool only ever sees exactly the
# keywords declared here; missing or extra names are rejected first.
TOOL_ARGUMENTS = {
    "open_application": frozenset({"name"}),
    "control_window": frozenset({"application", "action"}),
    "write_text": frozenset({"application", "text", "mode"}),
    "write_word_text": frozenset({"text", "mode"}),
    "save_word_document": frozenset({"filename", "folder"}),
    "add_word_block": frozenset({"text", "style", "alignment"}),
}

TOOL_ARGUMENT_TYPES = {
    "open_application": {"name": str},
    "control_window": {"application": str, "action": str},
    "write_text": {"application": str, "text": str, "mode": str},
    "write_word_text": {"text": str, "mode": str},
    "save_word_document": {"filename": str, "folder": str},
    "add_word_block": {"text": str, "style": str, "alignment": str},
}

# Tool schemas: a JSON description of each tool, sent to Ollama so the
# model knows which tools exist, what they do, and what arguments they take.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Return the current local system time.",
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
                "Use only to launch an approved app: notepad, calculator, "
                "word, or file_explorer. If the user only asked to act inside "
                "an app, do not use it. Launching Word creates no document."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Approved app name, e.g. 'notepad'.",
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
                "Use for window actions only; do not launch an application "
                "first unless explicitly requested. Safely minimize, restore, "
                "focus, or close one approved app window."
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
                "Use directly for Notepad writing; do not launch Notepad first "
                "unless requested. Modes: append or new_line. Does not read "
                "or save."
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
    {
        "type": "function",
        "function": {
            "name": "write_word_text",
            "description": (
                "Use directly for plain text in one safe editable Word "
                "document. Modes: append or new_paragraph. It refuses if no "
                "document is open and does not launch Word, create, read, "
                "format, or save."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["append", "new_paragraph"],
                    },
                },
                "required": ["text", "mode"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_word_document",
            "description": (
                "Create one blank unsaved document in safe running Word only "
                "when none is open. Does not launch Word or save."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_word_block",
            "description": (
                "Add one new fixed-style/aligned block to one safe editable "
                "Word document. Use for new headings, titles, or formatted "
                "paragraphs. Does not reformat existing text, launch, create, "
                "or save."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "style": {
                        "type": "string",
                        "enum": ["normal", "heading_1", "heading_2", "title"],
                    },
                    "alignment": {
                        "type": "string",
                        "enum": ["left", "center", "right", "justify"],
                    },
                },
                "required": ["text", "style", "alignment"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_word_document",
            "description": (
                "Use directly for save/save-as. Save one safe already-open Word "
                "document as DOCX in documents, desktop, or downloads. It may "
                "predate Celine. Do not create/write first or ask whether Word "
                "is open; this tool checks. Never overwrites."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "folder": {
                        "type": "string",
                        "enum": ["documents", "desktop", "downloads"],
                    },
                },
                "required": ["filename", "folder"],
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

    if (
        name == "write_word_text"
        and arguments["mode"] not in APPROVED_WORD_MODES
    ):
        return name, _bad_arguments(
            name, "mode must be one of: " + ", ".join(APPROVED_WORD_MODES)
        )

    if (
        name == "save_word_document"
        and arguments["folder"] not in APPROVED_SAVE_FOLDERS
    ):
        return name, _bad_arguments(
            name,
            "folder must be one of: " + ", ".join(APPROVED_SAVE_FOLDERS),
        )

    if (
        name == "add_word_block"
        and arguments["style"] not in APPROVED_WORD_STYLES
    ):
        return name, _bad_arguments(
            name,
            "style must be one of: " + ", ".join(APPROVED_WORD_STYLES),
        )

    if (
        name == "add_word_block"
        and arguments["alignment"] not in APPROVED_WORD_ALIGNMENTS
    ):
        return name, _bad_arguments(
            name,
            "alignment must be one of: "
            + ", ".join(APPROVED_WORD_ALIGNMENTS),
        )

    try:
        return name, str(TOOL_REGISTRY[name](**arguments))
    except TypeError as exc:
        return name, _bad_arguments(name, str(exc))
    except Exception as exc:
        return name, f"Error: tool {name} failed ({exc})."
