"""Private, fixed-operation Microsoft Word COM adapter."""

import time
from typing import Protocol

import pythoncom
import pywintypes
from pywinauto.controls.hwndwrapper import HwndWrapper
from win32com.client import GetActiveObject

from celine.tools.window_control import WINDOW_TARGETS, _find_windows, _matches


WORD_PROGID = "Word.Application"
APPROVED_WORD_MODES = ("append", "new_paragraph")
APPROVED_WORD_STYLES = ("normal", "heading_1", "heading_2", "title")
APPROVED_WORD_ALIGNMENTS = ("left", "center", "right", "justify")
WORD_STYLE_PRESETS = {
    "normal": (12, 0),
    "heading_1": (18, -1),
    "heading_2": (14, -1),
    "title": (22, -1),
}
WORD_ALIGNMENT_VALUES = {
    "left": 0,
    "center": 1,
    "right": 2,
    "justify": 3,
}
WORD_FONT_NAME = "Aptos"
NO_PROTECTION = -1
WD_FORMAT_DOCUMENT_DEFAULT = 16
READINESS_TIMEOUT_SECONDS = 3.0
READINESS_POLL_SECONDS = 0.1
VALIDATION_REJECTED = "validation_rejected"
ATTACHMENT_FAILED = "attachment_failed"
WRITE_FAILED = "write_failed"
WRITE_SUCCEEDED = "write_succeeded"
BLOCK_INSERT_FAILED = "block_insert_failed"
BLOCK_FORMAT_FAILED = "block_format_failed"
BLOCK_SUCCEEDED = "block_succeeded"
CREATION_FAILED = "creation_failed"
CREATION_UNCONFIRMED = "creation_unconfirmed"
CREATION_ACTIVATION_FAILED = "creation_activation_failed"
CREATION_SUCCEEDED = "creation_succeeded"
SAVE_FAILED = "save_failed"
TARGET_REJECTED = "target_rejected"
FILE_EXISTS = "file_exists"
SAVE_UNCONFIRMED = "save_unconfirmed"
SAVE_SUCCEEDED = "save_succeeded"


class WordAdapter(Protocol):
    """Boundary used by the public tool and replaced by fakes in tests."""

    def write_text(self, text: str, mode: str) -> None:
        """Perform one validated Word write operation."""

    def create_document(self) -> None:
        """Create and confirm one blank document in a safe Word instance."""

    def save_document(self, trusted_path: str) -> None:
        """Save the safely targeted document to one trusted DOCX path."""

    def add_block(self, text: str, style: str, alignment: str) -> None:
        """Insert and format one validated, isolated Word block."""


class WordAdapterError(RuntimeError):
    """A safe, classified Word automation failure."""

    def __init__(
        self,
        reason: str,
        user_message: str,
        *,
        outcome: str = VALIDATION_REJECTED,
    ):
        super().__init__(user_message)
        self.reason = reason
        self.user_message = user_message
        self.outcome = outcome


def _trusted_word_handles():
    """Return visible top-level HWNDs matching the fixed Word rule."""
    rule = WINDOW_TARGETS["word"]
    handles = {
        getattr(element, "handle", None)
        for element in _find_windows()
        if _matches(element, rule)
    }
    return sorted(handle for handle in handles if handle is not None)


class ComWordAdapter:
    """Ephemeral Word COM client with strict target validation."""

    def __init__(
        self,
        *,
        find_handles=None,
        wrap_window=None,
        get_active_object=None,
        com_runtime=None,
        com_error_type=None,
        clock=None,
        sleep=None,
        readiness_timeout=READINESS_TIMEOUT_SECONDS,
        poll_interval=READINESS_POLL_SECONDS,
    ):
        self._find_handles = find_handles or _trusted_word_handles
        self._wrap_window = wrap_window or HwndWrapper
        self._get_active_object = get_active_object or GetActiveObject
        self._com_runtime = com_runtime or pythoncom
        self._com_error_type = com_error_type or pywintypes.com_error
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._readiness_timeout = readiness_timeout
        self._poll_interval = poll_interval

    def write_text(self, text: str, mode: str) -> None:
        """Attach, validate one document, and perform one fixed write."""
        if mode not in APPROVED_WORD_MODES:
            raise WordAdapterError(
                "invalid_mode",
                "The requested Microsoft Word text mode is not allowed.",
            )

        initialized = False
        document = None
        content = None
        try:
            try:
                self._com_runtime.CoInitialize()
                initialized = True
                document = self._wait_for_target(
                    self._attach_and_validate_document,
                    retry_reasons={"no_document"},
                )
            except WordAdapterError:
                raise
            except Exception as exc:
                raise WordAdapterError(
                    "attachment_error",
                    "Microsoft Word could not be safely attached. "
                    "No write was attempted.",
                    outcome=ATTACHMENT_FAILED,
                ) from exc

            try:
                content, payload = self._prepare_write(document, text, mode)
            except WordAdapterError:
                raise
            except Exception as exc:
                raise WordAdapterError(
                    "range_metadata_unavailable",
                    "Microsoft Word could not be safely targeted. "
                    "No write was attempted.",
                ) from exc

            try:
                content.InsertAfter(payload)
            except Exception as exc:
                raise WordAdapterError(
                    "write_error",
                    "The Word write operation could not be confirmed.",
                    outcome=WRITE_FAILED,
                ) from exc
        finally:
            content = None
            document = None
            if initialized:
                self._com_runtime.CoUninitialize()

    def create_document(self) -> None:
        """Create exactly one document, then validate it without rollback."""
        initialized = False
        application = None
        document = None
        document_window = None
        trusted_hwnd = None
        try:
            try:
                self._com_runtime.CoInitialize()
                initialized = True
                application, trusted_hwnd = self._wait_for_target(
                    self._attach_and_validate_empty_application,
                )
            except WordAdapterError:
                raise
            except Exception as exc:
                raise WordAdapterError(
                    "attachment_error",
                    "Microsoft Word could not be safely attached. "
                    "No document creation was attempted.",
                    outcome=ATTACHMENT_FAILED,
                ) from exc

            try:
                document = application.Documents.Add()
            except Exception as exc:
                raise WordAdapterError(
                    "creation_error",
                    "The Word document creation operation could not be "
                    "confirmed.",
                    outcome=CREATION_FAILED,
                ) from exc

            try:
                document_window = self._validate_created_document(
                    application,
                    document,
                    trusted_hwnd,
                )
            except Exception as exc:
                raise WordAdapterError(
                    "post_creation_validation_failed",
                    "A Word document may have been created, but the result "
                    "could not be safely confirmed.",
                    outcome=CREATION_UNCONFIRMED,
                ) from exc

            try:
                document_window.Activate()
            except Exception as exc:
                raise WordAdapterError(
                    "document_window_activation_failed",
                    "A blank Word document was created, but its window could "
                    "not be brought to the foreground.",
                    outcome=CREATION_ACTIVATION_FAILED,
                ) from exc
        finally:
            document_window = None
            document = None
            application = None
            if initialized:
                self._com_runtime.CoUninitialize()

    def save_document(self, trusted_path: str) -> None:
        """Validate the existing document and perform one fixed DOCX save."""
        initialized = False
        document = None
        try:
            try:
                self._com_runtime.CoInitialize()
                initialized = True
                document = self._wait_for_target(
                    self._attach_and_validate_document,
                )
            except WordAdapterError:
                raise
            except Exception as exc:
                raise WordAdapterError(
                    "save_attachment_error",
                    "Microsoft Word could not be safely attached. "
                    "No save was attempted.",
                    outcome=ATTACHMENT_FAILED,
                ) from exc

            try:
                document.SaveAs2(trusted_path, WD_FORMAT_DOCUMENT_DEFAULT)
            except Exception as exc:
                raise WordAdapterError(
                    "save_error",
                    "The Word save operation could not be confirmed.",
                    outcome=SAVE_FAILED,
                ) from exc
        finally:
            document = None
            if initialized:
                self._com_runtime.CoUninitialize()

    def add_block(self, text: str, style: str, alignment: str) -> None:
        """Insert one isolated block and apply fixed formatting presets."""
        if style not in APPROVED_WORD_STYLES:
            raise WordAdapterError(
                "invalid_style",
                "The requested Microsoft Word style is not allowed.",
            )
        if alignment not in APPROVED_WORD_ALIGNMENTS:
            raise WordAdapterError(
                "invalid_alignment",
                "The requested Microsoft Word alignment is not allowed.",
            )

        initialized = False
        document = None
        insertion_range = None
        block_range = None
        trailing_range = None
        try:
            try:
                self._com_runtime.CoInitialize()
                initialized = True
                document = self._wait_for_target(
                    self._attach_and_validate_document,
                )
            except WordAdapterError:
                raise
            except Exception as exc:
                raise WordAdapterError(
                    "block_attachment_error",
                    "Microsoft Word could not be safely attached. "
                    "No text was inserted.",
                    outcome=ATTACHMENT_FAILED,
                ) from exc

            try:
                insertion_start, prefix = self._block_insertion_boundary(document)
                insertion_range = document.Range(insertion_start, insertion_start)
            except WordAdapterError:
                raise
            except Exception as exc:
                raise WordAdapterError(
                    "block_range_metadata_unavailable",
                    "Microsoft Word could not be safely targeted. "
                    "No text was inserted.",
                ) from exc

            payload = prefix + text + "\r"
            block_start = insertion_start + len(prefix)
            block_end = block_start + len(text)
            try:
                insertion_range.InsertAfter(payload)
            except Exception as exc:
                raise WordAdapterError(
                    "block_insert_error",
                    "The Word block insertion could not be confirmed.",
                    outcome=BLOCK_INSERT_FAILED,
                ) from exc

            try:
                block_range = document.Range(block_start, block_end)
                trailing_start = block_end + 1
                trailing_range = document.Range(trailing_start, trailing_start + 1)
                self._apply_block_format(block_range, style, alignment)
                self._apply_block_format(trailing_range, "normal", "left")
            except Exception as exc:
                raise WordAdapterError(
                    "block_format_error",
                    "The text was inserted in Microsoft Word, but its "
                    "formatting could not be confirmed.",
                    outcome=BLOCK_FORMAT_FAILED,
                ) from exc
        finally:
            trailing_range = None
            block_range = None
            insertion_range = None
            document = None
            if initialized:
                self._com_runtime.CoUninitialize()

    def _wait_for_target(self, validator, *, retry_reasons=frozenset()):
        """Poll only native/COM readiness, never a mutating operation."""
        deadline = self._clock() + self._readiness_timeout
        last_error = WordAdapterError(
            "word_not_open",
            "Microsoft Word is not currently open.",
        )

        while True:
            try:
                handles = self._find_handles()
            except Exception as exc:
                raise WordAdapterError(
                    "window_discovery_error",
                    "Microsoft Word could not be safely identified. "
                    "No write was attempted.",
                ) from exc

            if len(handles) > 1:
                raise WordAdapterError(
                    "ambiguous_word_target",
                    "Multiple Microsoft Word windows are open. "
                    "No write was attempted.",
                )

            if len(handles) == 1:
                try:
                    return validator(handles[0])
                except WordAdapterError as exc:
                    if exc.reason not in retry_reasons:
                        raise
                    last_error = exc
                except self._com_error_type:
                    last_error = WordAdapterError(
                        "word_not_ready",
                        "Microsoft Word is not automation-ready. "
                        "No write was attempted.",
                        outcome=ATTACHMENT_FAILED,
                    )
            else:
                last_error = WordAdapterError(
                    "word_not_open",
                    "Microsoft Word is not currently open.",
                )

            remaining = deadline - self._clock()
            if remaining <= 0:
                raise last_error
            self._sleep(min(self._poll_interval, remaining))

    def _attach_base(self, trusted_hwnd):
        """Attach to one enabled native target and reject Protected View."""
        window = self._wrap_window(trusted_hwnd)
        if not window.is_enabled():
            raise WordAdapterError(
                "disabled_or_modal",
                "Microsoft Word is disabled or showing a modal dialog. "
                "No operation was attempted.",
            )

        application = self._get_active_object(WORD_PROGID)
        if int(application.ProtectedViewWindows.Count) != 0:
            raise WordAdapterError(
                "protected_view",
                "Microsoft Word is displaying a protected document. "
                "No operation was attempted.",
            )
        return application

    def _attach_and_validate_document(self, trusted_hwnd):
        """Attach to the fixed ProgID and prove the target is unambiguous."""
        application = self._attach_base(trusted_hwnd)

        document_count = int(application.Documents.Count)
        if document_count == 0:
            raise WordAdapterError(
                "no_document",
                "Microsoft Word is running, but no document is open. "
                "No write was attempted.",
            )
        if document_count != 1:
            raise WordAdapterError(
                "ambiguous_documents",
                "Multiple Microsoft Word documents are open. "
                "No write was attempted.",
            )

        if int(application.Windows.Count) != 1:
            raise WordAdapterError(
                "ambiguous_document_windows",
                "Microsoft Word has multiple document windows. "
                "No write was attempted.",
            )
        self._require_matching_window(
            application.Windows,
            trusted_hwnd,
            "application_window_hwnd",
        )

        document = application.Documents.Item(1)
        if int(document.Windows.Count) != 1:
            raise WordAdapterError(
                "ambiguous_document_windows",
                "The Microsoft Word document has multiple windows. "
                "No write was attempted.",
            )
        self._require_matching_window(
            document.Windows,
            trusted_hwnd,
            "document_window_hwnd",
        )
        if bool(document.ReadOnly):
            raise WordAdapterError(
                "read_only_document",
                "The Microsoft Word document is read-only. "
                "No write was attempted.",
            )
        if int(document.ProtectionType) != NO_PROTECTION:
            raise WordAdapterError(
                "protected_document",
                "The Microsoft Word document is protected. "
                "No write was attempted.",
            )
        return document

    def _attach_and_validate_empty_application(self, trusted_hwnd):
        """Attach to one safe Word instance that has no open documents."""
        application = self._attach_base(trusted_hwnd)
        if int(application.Documents.Count) != 0:
            raise WordAdapterError(
                "document_already_open",
                "Microsoft Word already has an open document. "
                "No new document was created.",
            )
        if int(application.Windows.Count) != 0:
            raise WordAdapterError(
                "ambiguous_pre_creation_windows",
                "Microsoft Word could not be safely targeted. "
                "No document creation was attempted.",
            )
        return application, int(trusted_hwnd)

    def _validate_created_document(
        self,
        application,
        document,
        trusted_hwnd,
    ):
        """Confirm the one returned document owns the trusted native HWND."""
        if int(application.Documents.Count) != 1:
            raise WordAdapterError(
                "post_creation_document_count",
                "Created document count could not be confirmed.",
            )
        if int(application.Windows.Count) != 1:
            raise WordAdapterError(
                "post_creation_application_windows",
                "Created application window could not be confirmed.",
            )
        self._require_matching_window(
            application.Windows,
            trusted_hwnd,
            "post_creation_application_window_hwnd",
        )
        if int(document.Windows.Count) != 1:
            raise WordAdapterError(
                "post_creation_document_windows",
                "Created document window could not be confirmed.",
            )
        document_window = self._require_matching_window(
            document.Windows,
            trusted_hwnd,
            "post_creation_document_window_hwnd",
        )
        if bool(document.ReadOnly):
            raise WordAdapterError(
                "post_creation_read_only",
                "Created document is read-only.",
            )
        if int(document.ProtectionType) != NO_PROTECTION:
            raise WordAdapterError(
                "post_creation_protected",
                "Created document is protected.",
            )
        return document_window

    @staticmethod
    def _require_matching_window(windows, trusted_hwnd, source):
        """Require the sole fixed Word window to match the native HWND."""
        try:
            window = windows.Item(1)
            com_hwnd = int(window.Hwnd)
        except Exception as exc:
            raise WordAdapterError(
                f"{source}_unavailable",
                "Microsoft Word could not be safely targeted. "
                "No write was attempted.",
            ) from exc
        if com_hwnd != int(trusted_hwnd):
            raise WordAdapterError(
                f"{source}_mismatch",
                "Microsoft Word could not be safely targeted. "
                "No write was attempted.",
            )
        return window

    @staticmethod
    def _prepare_write(document, text, mode):
        """Obtain range metadata and prepare one fixed write payload."""
        content = document.Content
        is_empty = int(content.End) <= int(content.Start) + 1
        if mode == "append":
            payload = text
        elif mode == "new_paragraph":
            payload = text if is_empty else "\r" + text
        else:
            raise WordAdapterError(
                "invalid_mode",
                "The requested Microsoft Word text mode is not allowed.",
            )
        return content, payload

    @staticmethod
    def _block_insertion_boundary(document):
        """Choose the terminal insertion point using position metadata only."""
        content = document.Content
        content_start = int(content.Start)
        content_end = int(content.End)
        if content_end <= content_start:
            raise WordAdapterError(
                "invalid_content_range",
                "Microsoft Word could not be safely targeted. "
                "No text was inserted.",
            )

        paragraphs = document.Paragraphs
        paragraph_count = int(paragraphs.Count)
        if paragraph_count < 1:
            raise WordAdapterError(
                "missing_terminal_paragraph",
                "Microsoft Word could not be safely targeted. "
                "No text was inserted.",
            )
        last_range = paragraphs.Item(paragraph_count).Range
        last_start = int(last_range.Start)
        last_end = int(last_range.End)
        if not (
            content_start <= last_start < last_end <= content_end
        ):
            raise WordAdapterError(
                "invalid_terminal_paragraph",
                "Microsoft Word could not be safely targeted. "
                "No text was inserted.",
            )

        if last_end <= last_start + 1:
            return last_start, ""
        return content_end - 1, "\r"

    @staticmethod
    def _apply_block_format(target_range, style, alignment):
        """Apply one code-owned font and paragraph preset to a fixed range."""
        size, bold = WORD_STYLE_PRESETS[style]
        target_range.Font.Name = WORD_FONT_NAME
        target_range.Font.Size = size
        target_range.Font.Bold = bold
        target_range.ParagraphFormat.Alignment = WORD_ALIGNMENT_VALUES[alignment]
