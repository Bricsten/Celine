"""Public, validated Microsoft Word text-writing tool."""

import unicodedata
from pathlib import Path

from celine.core import config
from celine.tools.word.adapter import (
    APPROVED_WORD_ALIGNMENTS,
    APPROVED_WORD_MODES,
    APPROVED_WORD_STYLES,
    ATTACHMENT_FAILED,
    BLOCK_FORMAT_FAILED,
    BLOCK_INSERT_FAILED,
    BLOCK_SUCCEEDED,
    CREATION_ACTIVATION_FAILED,
    CREATION_FAILED,
    CREATION_SUCCEEDED,
    CREATION_UNCONFIRMED,
    ComWordAdapter,
    FILE_EXISTS,
    SAVE_FAILED,
    SAVE_SUCCEEDED,
    SAVE_UNCONFIRMED,
    TARGET_REJECTED,
    VALIDATION_REJECTED,
    WordAdapterError,
    WRITE_FAILED,
    WRITE_SUCCEEDED,
)
from celine.tools.word.folders import (
    APPROVED_SAVE_FOLDERS,
    resolve_save_folder,
)


MAX_WORD_TEXT_LENGTH = 10_000
MAX_WORD_FILENAME_LENGTH = 120
_ILLEGAL_FILENAME_CHARACTERS = frozenset('<>:"/\\|?*')
_RESERVED_FILENAME_BASES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)
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
SAVE_FAILURE_RESULTS = {
    VALIDATION_REJECTED: "The Word save request was rejected. No save was attempted.",
    ATTACHMENT_FAILED: (
        "Microsoft Word could not be safely attached. No save was attempted."
    ),
    SAVE_FAILED: "The Word save operation could not be confirmed.",
}
BLOCK_FAILURE_RESULTS = {
    VALIDATION_REJECTED: (
        "Microsoft Word could not be safely targeted. "
        "No text was inserted."
    ),
    ATTACHMENT_FAILED: (
        "Microsoft Word could not be safely attached. "
        "No text was inserted."
    ),
    BLOCK_INSERT_FAILED: "The Word block insertion could not be confirmed.",
    BLOCK_FORMAT_FAILED: (
        "The text was inserted in Microsoft Word, but its formatting could "
        "not be confirmed."
    ),
}


def _debug(tool_name, message):
    if config.TOOL_LOG:
        print(f"[tool] {tool_name} {message}")


def _adapter_factory():
    return ComWordAdapter()


def _folder_resolver(folder):
    return resolve_save_folder(folder)


def _path_exists(path):
    return path.exists()


def _validated_docx_filename(filename):
    """Return a safe filename-only DOCX name, or a concise rejection."""
    if not isinstance(filename, str):
        return None, "Filename must be a string. No save was attempted."
    if any(unicodedata.category(character) == "Cc" for character in filename):
        return None, (
            "Filename contains control characters. No save was attempted."
        )
    if filename.endswith((".", " ")):
        return None, (
            "Filename cannot end with a dot or space. No save was attempted."
        )
    normalized = filename.strip()
    if not normalized:
        return None, "Filename is empty. No save was attempted."
    if normalized in {".", ".."}:
        return None, "Filename is not allowed. No save was attempted."
    if any(character in _ILLEGAL_FILENAME_CHARACTERS for character in normalized):
        return None, (
            "Filename contains characters that Windows does not allow. "
            "No save was attempted."
        )

    dot_index = normalized.rfind(".")
    if dot_index == -1:
        normalized += ".docx"
        stem = normalized[:-5]
    else:
        extension = normalized[dot_index:]
        if extension.lower() != ".docx":
            return None, "Only DOCX filenames are allowed. No save was attempted."
        stem = normalized[:dot_index]
    if not stem:
        return None, "Filename is not allowed. No save was attempted."
    if stem.endswith((".", " ")):
        return None, (
            "Filename cannot contain a name ending with a dot or space. "
            "No save was attempted."
        )
    reserved_base = stem.split(".", 1)[0].upper()
    if reserved_base in _RESERVED_FILENAME_BASES:
        return None, "Filename is reserved by Windows. No save was attempted."
    if len(normalized) > MAX_WORD_FILENAME_LENGTH:
        return None, (
            f"Filename exceeds the {MAX_WORD_FILENAME_LENGTH}-character limit. "
            "No save was attempted."
        )
    return normalized, None


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


def add_word_block(text, style, alignment):
    """Insert one isolated Word block using fixed formatting presets."""
    chars = len(text) if isinstance(text, str) else "invalid"
    style_label = style if style in APPROVED_WORD_STYLES else "invalid"
    alignment_label = (
        alignment if alignment in APPROVED_WORD_ALIGNMENTS else "invalid"
    )
    _debug(
        "add_word_block",
        f"requested style={style_label} alignment={alignment_label} "
        f"chars={chars}",
    )

    if not isinstance(text, str):
        _debug(
            "add_word_block",
            "failed outcome=validation_rejected reason=invalid_text_type",
        )
        return "Text must be a string. No text was inserted."
    if not text:
        _debug(
            "add_word_block",
            "failed outcome=validation_rejected reason=empty_text",
        )
        return "Text is empty. No text was inserted."
    if len(text) > MAX_WORD_TEXT_LENGTH:
        _debug(
            "add_word_block",
            "failed outcome=validation_rejected reason=text_too_long",
        )
        return (
            f"Text exceeds the {MAX_WORD_TEXT_LENGTH:,}-character limit. "
            "No text was inserted."
        )
    if not isinstance(style, str) or style not in APPROVED_WORD_STYLES:
        _debug(
            "add_word_block",
            "failed outcome=validation_rejected reason=invalid_style",
        )
        allowed = ", ".join(APPROVED_WORD_STYLES)
        return (
            f"Microsoft Word style is not allowed: {style!r}. "
            f"Approved styles: {allowed}. No text was inserted."
        )
    if (
        not isinstance(alignment, str)
        or alignment not in APPROVED_WORD_ALIGNMENTS
    ):
        _debug(
            "add_word_block",
            "failed outcome=validation_rejected reason=invalid_alignment",
        )
        allowed = ", ".join(APPROVED_WORD_ALIGNMENTS)
        return (
            f"Microsoft Word alignment is not allowed: {alignment!r}. "
            f"Approved alignments: {allowed}. No text was inserted."
        )

    try:
        _adapter_factory().add_block(text, style, alignment)
    except WordAdapterError as exc:
        _debug(
            "add_word_block",
            f"failed outcome={exc.outcome} reason={exc.reason}",
        )
        if exc.reason == "no_document":
            return (
                "Microsoft Word is running, but no document is open. "
                "No text was inserted."
            )
        if exc.reason == "word_not_open":
            return (
                "Microsoft Word is not currently open. "
                "No text was inserted."
            )
        return BLOCK_FAILURE_RESULTS.get(
            exc.outcome,
            BLOCK_FAILURE_RESULTS[BLOCK_INSERT_FAILED],
        )
    except Exception:
        _debug(
            "add_word_block",
            "failed outcome=block_insert_failed reason=unexpected_error",
        )
        return BLOCK_FAILURE_RESULTS[BLOCK_INSERT_FAILED]

    _debug(
        "add_word_block",
        f"success outcome={BLOCK_SUCCEEDED} style={style} "
        f"alignment={alignment} chars={len(text)}",
    )
    return "Formatted text block added successfully in Microsoft Word."


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


def save_word_document(filename, folder):
    """Save the safely targeted Word document to one approved folder."""
    chars = len(filename) if isinstance(filename, str) else "invalid"
    folder_label = "invalid"
    if isinstance(folder, str):
        candidate = folder.strip().lower()
        if candidate in APPROVED_SAVE_FOLDERS:
            folder_label = candidate
    _debug(
        "save_word_document",
        f"requested folder={folder_label} filename_chars={chars}",
    )

    safe_filename, error = _validated_docx_filename(filename)
    if error is not None:
        _debug(
            "save_word_document",
            "failed outcome=validation_rejected reason=invalid_filename",
        )
        return error
    if not isinstance(folder, str) or folder_label == "invalid":
        _debug(
            "save_word_document",
            "failed outcome=validation_rejected reason=invalid_folder",
        )
        allowed = ", ".join(APPROVED_SAVE_FOLDERS)
        return (
            f"Save folder is not allowed. Approved folders: {allowed}. "
            "No save was attempted."
        )

    try:
        logical_folder, trusted_folder = _folder_resolver(folder_label)
        trusted_folder = Path(trusted_folder)
        trusted_path = trusted_folder / safe_filename
    except Exception:
        _debug(
            "save_word_document",
            f"failed outcome={TARGET_REJECTED} reason=folder_resolution",
        )
        return "The approved save folder could not be resolved. No save was attempted."

    display_folder = logical_folder.title()
    try:
        destination_exists = _path_exists(trusted_path)
    except Exception:
        _debug(
            "save_word_document",
            f"failed outcome={TARGET_REJECTED} reason=existence_check",
        )
        return (
            "The save destination could not be safely checked. "
            "No save was attempted."
        )
    if destination_exists:
        _debug(
            "save_word_document",
            f"failed outcome={FILE_EXISTS} reason=destination_exists",
        )
        return (
            f"A file named {safe_filename!r} already exists in "
            f"{display_folder}. No file was overwritten."
        )

    try:
        _adapter_factory().save_document(str(trusted_path))
    except WordAdapterError as exc:
        outcome = (
            TARGET_REJECTED
            if exc.outcome == VALIDATION_REJECTED
            else exc.outcome
        )
        _debug(
            "save_word_document",
            f"failed outcome={outcome} reason={exc.reason}",
        )
        if exc.reason == "no_document":
            return (
                "Microsoft Word has no open document. No save was attempted."
            )
        return SAVE_FAILURE_RESULTS.get(
            exc.outcome,
            "Microsoft Word could not be safely targeted. No save was attempted.",
        )
    except Exception:
        _debug(
            "save_word_document",
            "failed outcome=save_failed reason=unexpected_error",
        )
        return SAVE_FAILURE_RESULTS[SAVE_FAILED]

    try:
        saved_file_exists = _path_exists(trusted_path)
    except Exception:
        saved_file_exists = False
    if not saved_file_exists:
        _debug(
            "save_word_document",
            f"failed outcome={SAVE_UNCONFIRMED} reason=file_not_confirmed",
        )
        return (
            "The Word save operation completed, but the saved file could not "
            "be safely confirmed."
        )

    _debug(
        "save_word_document",
        f"success folder={logical_folder} outcome={SAVE_SUCCEEDED}",
    )
    return (
        f"Microsoft Word document saved successfully as {safe_filename!r} "
        f"in {display_folder}."
    )
