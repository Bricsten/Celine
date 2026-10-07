"""Public, validated Microsoft Word text-writing tool."""

from celine.core import config
from celine.tools.word.adapter import (
    APPROVED_WORD_MODES,
    ATTACHMENT_FAILED,
    CREATION_ACTIVATION_FAILED,
    CREATION_FAILED,
    CREATION_SUCCEEDED,
    CREATION_UNCONFIRMED,
    ComWordAdapter,
    VALIDATION_REJECTED,
    WordAdapterError,
    WRITE_FAILED,
    WRITE_SUCCEEDED,
)


MAX_WORD_TEXT_LENGTH = 10_000
FAILURE_RESULTS = {
    VALIDATION_REJECTED: (
        "Microsoft Word could not be safely targeted. "
        "No write was attempted."
    ),
    ATTACHMENT_FAILED: (
        "Microsoft Word could not be safely attached. "
        "No write was attempted."
    ),
    WRITE_FAILED: "The Word write operation could not be confirmed.",
}
CREATION_FAILURE_RESULTS = {
    VALIDATION_REJECTED: (
        "Microsoft Word could not be safely targeted. "
        "No document creation was attempted."
    ),
    ATTACHMENT_FAILED: (
        "Microsoft Word could not be safely attached. "
        "No document creation was attempted."
    ),
    CREATION_FAILED: (
        "The Word document creation operation could not be confirmed."
    ),
    CREATION_UNCONFIRMED: (
        "A Word document may have been created, but the result could not be "
        "safely confirmed."
    ),
    CREATION_ACTIVATION_FAILED: (
        "A blank Word document was created, but its window could not be "
        "brought to the foreground."
    ),
}


def _debug(tool_name, message):
    if config.TOOL_LOG:
        print(f"[tool] {tool_name} {message}")


def _adapter_factory():
    return ComWordAdapter()


def write_word_text(text, mode):
    """Write plain text to one unambiguous editable Word document."""
    chars = len(text) if isinstance(text, str) else "invalid"
    _debug("write_word_text", f"requested mode={mode} chars={chars}")

    if not isinstance(text, str):
        _debug(
            "write_word_text",
            "failed outcome=validation_rejected reason=invalid_text_type",
        )
        return "Text must be a string. No write was attempted."
    if not text:
        _debug(
            "write_word_text",
            "failed outcome=validation_rejected reason=empty_text",
        )
        return "Text is empty. No write was attempted."
    if len(text) > MAX_WORD_TEXT_LENGTH:
        _debug(
            "write_word_text",
            "failed outcome=validation_rejected reason=text_too_long",
        )
        return (
            f"Text exceeds the {MAX_WORD_TEXT_LENGTH:,}-character limit. "
            "No write was attempted."
        )
    if not isinstance(mode, str) or mode not in APPROVED_WORD_MODES:
        _debug(
            "write_word_text",
            "failed outcome=validation_rejected reason=invalid_mode",
        )
        allowed = ", ".join(APPROVED_WORD_MODES)
        return (
            f"Microsoft Word text mode is not allowed: {mode!r}. "
            f"Approved modes: {allowed}. No write was attempted."
        )

    try:
        _adapter_factory().write_text(text, mode)
    except WordAdapterError as exc:
        _debug(
            "write_word_text",
            f"failed outcome={exc.outcome} reason={exc.reason}",
        )
        if exc.reason == "no_document":
            return (
                "Microsoft Word is running, but no document is open. "
                "No write was attempted."
            )
        if exc.reason == "word_not_open":
            return "Microsoft Word is not currently open. No write was attempted."
        return FAILURE_RESULTS.get(exc.outcome, FAILURE_RESULTS[WRITE_FAILED])
    except Exception:
        _debug(
            "write_word_text",
            "failed outcome=write_failed reason=unexpected_error",
        )
        return FAILURE_RESULTS[WRITE_FAILED]

    _debug(
        "write_word_text",
        f"success outcome={WRITE_SUCCEEDED} mode={mode} chars={len(text)}",
    )
    if mode == "new_paragraph":
        return "Paragraph added successfully in Microsoft Word."
    return "Text appended successfully in Microsoft Word."


def create_word_document():
    """Create one blank unsaved document in an already-running Word app."""
    _debug("create_word_document", "requested")
    try:
        _adapter_factory().create_document()
    except WordAdapterError as exc:
        _debug(
            "create_word_document",
            f"failed outcome={exc.outcome} reason={exc.reason}",
        )
        if exc.reason == "document_already_open":
            return (
                "Microsoft Word already has an open document. "
                "No new document was created."
            )
        if exc.reason == "word_not_open":
            return (
                "Microsoft Word is not currently open. "
                "No document creation was attempted."
            )
        return CREATION_FAILURE_RESULTS.get(
            exc.outcome,
            CREATION_FAILURE_RESULTS[CREATION_UNCONFIRMED],
        )
    except Exception:
        _debug(
            "create_word_document",
            "failed outcome=creation_unconfirmed reason=unexpected_error",
        )
        return CREATION_FAILURE_RESULTS[CREATION_UNCONFIRMED]

    _debug(
        "create_word_document",
        f"success outcome={CREATION_SUCCEEDED}",
    )
    return "Blank Microsoft Word document created successfully."
