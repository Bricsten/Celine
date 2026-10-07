"""Safe, control-scoped text insertion for an already-running Notepad.

The model supplies only a logical application name and plain text. Trusted
code finds the approved Notepad top-level window, locates its fixed editable
child control, and appends through messages sent directly to that child HWND.
No focus-based or global keyboard input is used.
"""

import ctypes

from pywinauto import Desktop
from pywinauto.controls.hwndwrapper import HwndWrapper
from pywinauto import win32defines

from celine.core import config
from celine.tools.window_control import _find_window
from celine.tools.windows_apps import normalize_name


MAX_TEXT_LENGTH = 10_000

# Fixed UI Automation identities for the document control. Modern Windows 11
# Notepad exposes RichEditD2DPT as a Document; classic Notepad exposes Edit.
# These values are code-owned and cannot be influenced by model input.
EDIT_TARGETS = (
    {"control_type": "Document", "classes": ("richeditd2dpt",)},
    {"control_type": "Edit", "classes": ("edit",)},
)


def _debug(message):
    if config.TOOL_LOG:
        print(f"[tool] type_text {message}")


def _uia_window(hwnd):
    """Return the UIA wrapper for one trusted top-level window handle."""
    return Desktop(backend="uia").window(handle=hwnd).wrapper_object()


def _control_handle(control):
    """Read a discovered UIA control's native handle."""
    handle = getattr(control, "handle", None)
    if handle:
        return handle
    element_info = getattr(control, "element_info", None)
    return getattr(element_info, "handle", None) if element_info else None


def _find_editable_control(window):
    """Find exactly one visible, enabled control matching a fixed rule."""
    for rule in EDIT_TARGETS:
        matches = []
        for control in window.descendants(control_type=rule["control_type"]):
            element_info = getattr(control, "element_info", None)
            class_name = getattr(element_info, "class_name", "") or ""
            if class_name.lower() not in rule["classes"]:
                continue
            if not _control_handle(control):
                continue
            if not control.is_visible() or not control.is_enabled():
                continue
            matches.append(control)

        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None
    return None


def _append_text(control, text):
    """Append text directly to a verified edit control without global keys."""
    window = HwndWrapper(_control_handle(control))
    window.verify_actionable()
    end = window.send_message(win32defines.WM_GETTEXTLENGTH)
    window.send_message(win32defines.EM_SETSEL, end, end)
    buffer = ctypes.create_unicode_buffer(text, len(text) + 1)
    window.send_message(
        win32defines.EM_REPLACESEL,
        True,
        ctypes.byref(buffer),
    )


def type_text(application, text):
    """Append plain text to the editable control of a running Notepad."""
    chars = len(text) if isinstance(text, str) else "invalid"
    _debug(f"requested application={application} chars={chars}")

    canonical = normalize_name(application)
    if canonical != "notepad":
        _debug("failed reason=unsupported_application")
        return (
            "Text entry is only allowed for notepad. "
            "No text was entered."
        )
    if not isinstance(text, str):
        _debug("failed application=notepad reason=invalid_text_type")
        return "Text must be a string. No text was entered."
    if not text:
        _debug("failed application=notepad reason=empty_text")
        return "Text is empty. No text was entered."
    if len(text) > MAX_TEXT_LENGTH:
        _debug("failed application=notepad reason=text_too_long")
        return (
            f"Text exceeds the {MAX_TEXT_LENGTH:,}-character limit. "
            "No text was entered."
        )

    try:
        hwnd = _find_window("notepad")
        if hwnd is None:
            _debug("failed application=notepad reason=not_open")
            return "Notepad is not currently open. No text was entered."

        control = _find_editable_control(_uia_window(hwnd))
        if control is None:
            _debug("failed application=notepad reason=control_not_found")
            return (
                "Notepad's editable control could not be identified. "
                "No text was entered."
            )

        _append_text(control, text)
    except Exception:
        _debug("failed application=notepad reason=automation_error")
        return (
            "Text could not be entered because Notepad automation failed. "
            "No text was entered."
        )

    _debug(f"success application=notepad chars={len(text)}")
    return f"Text entered successfully in notepad ({len(text)} characters)."
