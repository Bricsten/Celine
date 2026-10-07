"""open_application: launch a small fixed allowlist of Windows apps.

The model only ever supplies a plain name string. The executable path is
built from APP_ALLOWLIST plus the local Windows directory - never from
model input. Every executable is resolved to an explicit path and checked
for existence before subprocess.Popen([explicit_path], shell=False):
no bare executable names, no PATH/current-directory search, no command
strings, no shell, no eval, no dynamic imports.
"""

import os
import subprocess

from celine.core import config

try:
    import winreg
except ImportError:  # not running on Windows
    winreg = None

# Fixed launch definitions for approved logical names. The model can never
# add to this dictionary or influence what is in it. "relative" locations
# are joined onto the local Windows directory - never onto model input.
APP_ALLOWLIST = {
    "notepad": {"kind": "builtin", "relative": r"System32\notepad.exe"},
    "calculator": {"kind": "builtin", "relative": r"System32\calc.exe"},
    "word": {"kind": "word"},
    "file_explorer": {"kind": "builtin", "relative": r"explorer.exe"},
}

# Human-friendly names mapped to allowlist keys (lowercase, trimmed).
APP_ALIASES = {
    "calc": "calculator",
    "microsoft word": "word",
    "ms word": "word",
    "explorer": "file_explorer",
    "file explorer": "file_explorer",
    "file-explorer": "file_explorer",
    "windows explorer": "file_explorer",
}

# Word is not on PATH: check these fixed, standard locations only.
# This is a short list of explicit paths - never a recursive filesystem
# search.
WORD_EXE_BASENAME = "winword.exe"
WORD_REGISTRY_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE",
)
WORD_FIXED_PATHS = (
    r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
    r"C:\Program Files\Microsoft Office\Office16\WINWORD.EXE",
    r"C:\Program Files (x86)\Microsoft Office\Office16\WINWORD.EXE",
)


def _debug(message):
    if config.TOOL_LOG:
        print(f"[tool] open_application {message}")


def normalize_name(raw):
    """Trim, lowercase and alias-map a requested name.

    Returns an allowlist key, or None if the input is not a usable string.
    """
    if not isinstance(raw, str):
        return None
    name = " ".join(raw.strip().lower().split())
    if not name:
        return None
    return APP_ALIASES.get(name, name)


def _windows_dir():
    """The local Windows directory, from the OS environment only."""
    for variable in ("SystemRoot", "windir"):
        value = os.environ.get(variable)
        if value and os.path.isdir(value):
            return value
    raise FileNotFoundError("Windows directory not found")


def _resolve_builtin(relative):
    """Join a fixed relative location onto the Windows directory.

    The file must exist before it is ever passed to Popen: no PATH, no
    current-directory search, no bare executable names.
    """
    path = os.path.join(_windows_dir(), relative)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{path} not found")
    return path


def _resolve_word():
    """Find WINWORD.EXE in fixed, standard locations only."""
    if winreg is not None:
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for key_path in WORD_REGISTRY_KEYS:
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        value, _ = winreg.QueryValueEx(key, None)
                except OSError:
                    continue
                if isinstance(value, str) and value.strip():
                    path = value.strip().strip('"')
                    if os.path.basename(path).lower() != WORD_EXE_BASENAME:
                        continue
                    if os.path.isfile(path):
                        return path
    for path in WORD_FIXED_PATHS:
        if os.path.isfile(path):
            return path
    return None


def _launch(definition):
    """Launch one allowlist definition with an explicit, trusted path."""
    kind = definition.get("kind")
    if kind == "builtin":
        path = _resolve_builtin(definition["relative"])
        subprocess.Popen([path], shell=False)
    elif kind == "word":
        path = _resolve_word()
        if not path:
            raise FileNotFoundError(
                "WINWORD.EXE not found in registered locations"
            )
        subprocess.Popen([path], shell=False)
    else:
        raise RuntimeError(f"unknown launch kind: {kind!r}")


def open_application(name):
    """Open one approved Windows application. Returns a result string."""
    _debug(f"requested name={name}")

    canonical = normalize_name(name)
    if canonical is None or canonical not in APP_ALLOWLIST:
        _debug(f"failed name={name} reason=not_allowed")
        allowed = ", ".join(sorted(APP_ALLOWLIST))
        return (
            f"Application is not allowed: {name!r}. "
            f"Approved applications: {allowed}."
        )

    try:
        _launch(APP_ALLOWLIST[canonical])
    except Exception as exc:
        _debug(f"failed name={canonical} reason=not_launched")
        return (
            "Application could not be launched or is not installed: "
            f"{canonical} ({exc})."
        )

    _debug(f"success name={canonical}")
    return f"Application opened successfully: {canonical}."
