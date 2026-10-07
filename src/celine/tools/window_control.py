"""control_window: safe window actions on the approved applications only.

The model supplies exactly two plain strings: a logical application key
and one fixed action. Window matching rules (process name, window class,
title hints) are hardcoded in WINDOW_TARGETS and are never influenced by
model input. No PIDs, handles, titles or regexes come from the model.
No process is ever terminated: pywinauto's close() posts WM_CLOSE only.
"""

import ctypes
import os

from pywinauto import findwindows
from pywinauto.controls.hwndwrapper import HwndWrapper

from celine.core import config
from celine.tools.windows_apps import normalize_name

# Approved actions - fixed in code, never model-defined.
APPROVED_ACTIONS = ("minimize", "restore", "focus", "close")

# Fixed window-matching rules per approved application. Every field is
# written by us; the model may only select one of these four keys.
# - processes:      lowercase executable basenames
# - classes:        lowercase window class names
# - title_contains: lowercase substrings that must ALL appear in the title
WINDOW_TARGETS = {
    "notepad": {
        "processes": ("notepad.exe",),
        "classes": ("notepad",),
        "title_contains": (),
    },
    "calculator": {
        "processes": ("calculatorapp.exe", "applicationframehost.exe"),
        "classes": ("applicationframewindow",),
        "title_contains": ("calculator",),
    },
    "word": {
        "processes": ("winword.exe",),
        "classes": ("opusapp",),
        "title_contains": (),
    },
    "file_explorer": {
        "processes": ("explorer.exe",),
        "classes": ("cabinetwclass", "explorewclass"),
        "title_contains": (),
    },
}

# Fixed Win32 setup for PID -> executable name lookups.
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_KERNEL32 = ctypes.windll.kernel32
_KERNEL32.OpenProcess.restype = ctypes.c_void_p
_KERNEL32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
_KERNEL32.QueryFullProcessImageNameW.restype = ctypes.c_int
_KERNEL32.QueryFullProcessImageNameW.argtypes = [
    ctypes.c_void_p,
    ctypes.c_ulong,
    ctypes.c_wchar_p,
    ctypes.POINTER(ctypes.c_ulong),
]
_KERNEL32.CloseHandle.argtypes = [ctypes.c_void_p]


def _debug(message):
    if config.TOOL_LOG:
        print(f"[tool] control_window {message}")


def _title(element):
    """Window title from a find_elements element ('' if absent)."""
    for attribute in ("name", "text"):
        value = getattr(element, attribute, None)
        if isinstance(value, str):
            return value
    return ""


def _process_name(pid):
    """Lowercase executable basename for a PID ('' if unavailable)."""
    handle = _KERNEL32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not handle:
        return ""
    try:
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        ok = _KERNEL32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        )
        return os.path.basename(buffer.value).lower() if ok else ""
    finally:
        _KERNEL32.CloseHandle(handle)


def _find_windows():
    """All visible top-level windows (read-only pywinauto enumeration)."""
    return findwindows.find_elements(visible_only=True, top_level_only=True)


def _wrap(hwnd):
    """pywinauto window wrapper for one handle."""
    return HwndWrapper(hwnd)


def _matches(element, rule):
    """Does this window satisfy our fixed rules for one application?"""
    class_name = (getattr(element, "class_name", "") or "").lower()
    if class_name not in rule["classes"]:
        return False
    pid = getattr(element, "process_id", 0) or 0
    if _process_name(pid) not in rule["processes"]:
        return False
    title = _title(element).lower()
    return all(hint in title for hint in rule["title_contains"])


def _find_window(canonical):
    """Handle of the first window matching the app's fixed rules, else None."""
    rule = WINDOW_TARGETS[canonical]
    for element in _find_windows():
        if _matches(element, rule):
            handle = getattr(element, "handle", None)
            if handle is not None:
                return handle
    return None


def _perform(window, action):
    """Perform exactly one approved action. close() posts WM_CLOSE only."""
    if action == "minimize":
        window.minimize()
    elif action == "restore":
        window.restore()
    elif action == "focus":
        window.set_focus()
    elif action == "close":
        window.close()


def control_window(application, action):
    """Apply one approved window action to one approved application."""
    _debug(f"requested application={application} action={action}")

    canonical = normalize_name(application)
    if canonical is None or canonical not in WINDOW_TARGETS:
        _debug(f"failed application={application} reason=invalid_application")
        allowed = ", ".join(sorted(WINDOW_TARGETS))
        return (
            f"Application is not allowed: {application!r}. "
            f"Approved applications: {allowed}."
        )

    if (
        not isinstance(action, str)
        or action.strip().lower() not in APPROVED_ACTIONS
    ):
        _debug(f"failed application={canonical} reason=invalid_action")
        allowed = ", ".join(APPROVED_ACTIONS)
        return (
            f"Action is not allowed: {action!r}. "
            f"Approved actions: {allowed}."
        )
    action = action.strip().lower()

    try:
        hwnd = _find_window(canonical)
        if hwnd is None:
            _debug(
                f"failed application={canonical} action={action} "
                "reason=not_open"
            )
            return f"{canonical} is not currently open. No window was changed."
        window = _wrap(hwnd)
        _perform(window, action)
    except Exception as exc:
        _debug(f"failed application={canonical} action={action} reason=error")
        return (
            "Window action '"
            + action
            + f"' could not be completed for {canonical} ({exc})."
        )

    _debug(f"success application={canonical} action={action}")
    return f"Window action '{action}' completed successfully for {canonical}."
