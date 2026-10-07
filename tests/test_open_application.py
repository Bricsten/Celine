"""Tests for the open_application tool. Real apps are never launched."""

import os

from celine.core import config
from celine.tools import registry
from celine.tools import windows_apps


def fake_popen(monkeypatch, error=None):
    """Replace subprocess.Popen so nothing real is ever started."""
    calls = []

    def _fake(argv, **kwargs):
        calls.append((argv, kwargs))
        if error is not None:
            raise error
        return object()

    monkeypatch.setattr(windows_apps.subprocess, "Popen", _fake)
    return calls


def fake_windows(monkeypatch, tmp_path):
    """Point the Windows directory at a temp folder with dummy apps."""
    (tmp_path / "System32").mkdir()
    (tmp_path / "System32" / "notepad.exe").write_bytes(b"")
    (tmp_path / "System32" / "calc.exe").write_bytes(b"")
    (tmp_path / "explorer.exe").write_bytes(b"")
    monkeypatch.setattr(windows_apps, "_windows_dir", lambda: str(tmp_path))
    return tmp_path


class _FakeWinreg:
    """Minimal winreg stand-in returning one configured App Paths value."""

    HKEY_LOCAL_MACHINE = "HKLM"
    HKEY_CURRENT_USER = "HKCU"

    def __init__(self, value):
        self._value = value

    def OpenKey(self, hive, key_path):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def QueryValueEx(self, key, name):
        return (self._value, 1)


def test_notepad_allowed(monkeypatch, tmp_path):
    root = fake_windows(monkeypatch, tmp_path)
    calls = fake_popen(monkeypatch)
    result = windows_apps.open_application("notepad")
    assert "opened successfully" in result
    assert calls == [([str(root / "System32" / "notepad.exe")],
                      {"shell": False})]


def test_calculator_allowed(monkeypatch, tmp_path):
    root = fake_windows(monkeypatch, tmp_path)
    calls = fake_popen(monkeypatch)
    result = windows_apps.open_application("calculator")
    assert "opened successfully" in result
    assert calls == [([str(root / "System32" / "calc.exe")],
                      {"shell": False})]


def test_explicit_path_not_bare_name(monkeypatch, tmp_path):
    """Popen receives an explicit absolute path; PATH/cwd search is not
    used, so a different current directory or PATH cannot change it."""
    root = fake_windows(monkeypatch, tmp_path)
    calls = fake_popen(monkeypatch)
    windows_apps.open_application("notepad")
    argv, kwargs = calls[0]
    assert argv == [str(root / "System32" / "notepad.exe")]
    assert os.path.isabs(argv[0])
    assert argv[0] != "notepad.exe"
    assert kwargs == {"shell": False}


def test_missing_builtin_fails_before_popen(monkeypatch, tmp_path):
    root = fake_windows(monkeypatch, tmp_path)
    (root / "System32" / "notepad.exe").unlink()
    calls = fake_popen(monkeypatch)
    result = windows_apps.open_application("notepad")
    assert "could not be launched or is not installed" in result
    assert calls == []


def test_microsoft_word_alias_resolves_to_word(monkeypatch):
    calls = fake_popen(monkeypatch)
    monkeypatch.setattr(
        windows_apps, "_resolve_word", lambda: r"C:\Fake\WINWORD.EXE"
    )
    assert windows_apps.normalize_name("Microsoft Word") == "word"
    result = windows_apps.open_application("Microsoft Word")
    assert "opened successfully" in result
    assert calls == [([r"C:\Fake\WINWORD.EXE"], {"shell": False})]


def test_file_explorer_alias_resolves(monkeypatch, tmp_path):
    root = fake_windows(monkeypatch, tmp_path)
    calls = fake_popen(monkeypatch)
    assert windows_apps.normalize_name("File Explorer") == "file_explorer"
    result = windows_apps.open_application("File Explorer")
    assert "opened successfully" in result
    assert calls == [([str(root / "explorer.exe")], {"shell": False})]


def test_word_registry_wrong_basename_rejected(monkeypatch):
    wrong = os.path.join(os.environ["SystemRoot"], "System32", "notepad.exe")
    assert os.path.isfile(wrong)
    monkeypatch.setattr(windows_apps, "winreg", _FakeWinreg(wrong))
    monkeypatch.setattr(windows_apps, "WORD_FIXED_PATHS", ())
    assert windows_apps._resolve_word() is None

    calls = fake_popen(monkeypatch)
    result = windows_apps.open_application("word")
    assert "could not be launched or is not installed" in result
    assert calls == []


def test_unknown_application_rejected(monkeypatch):
    calls = fake_popen(monkeypatch)
    result = windows_apps.open_application("spotify")
    assert "not allowed" in result
    assert calls == []


def test_dangerous_input_rejected(monkeypatch):
    calls = fake_popen(monkeypatch)
    result = windows_apps.open_application(
        "powershell -Command Remove-Item C:\\"
    )
    assert "not allowed" in result
    assert calls == []


def test_executable_path_rejected(monkeypatch):
    calls = fake_popen(monkeypatch)
    result = windows_apps.open_application("C:\\Windows\\System32\\cmd.exe")
    assert "not allowed" in result
    assert calls == []


def test_launch_failure_handled_cleanly(monkeypatch, tmp_path):
    fake_windows(monkeypatch, tmp_path)
    fake_popen(monkeypatch, error=FileNotFoundError("missing"))
    result = windows_apps.open_application("notepad")
    assert "could not be launched or is not installed" in result


def test_word_not_installed_reports_clear_failure(monkeypatch):
    calls = fake_popen(monkeypatch)
    monkeypatch.setattr(windows_apps, "_resolve_word", lambda: None)
    result = windows_apps.open_application("word")
    assert "could not be launched or is not installed" in result
    assert calls == []


def test_registry_passes_name_argument(monkeypatch, tmp_path):
    root = fake_windows(monkeypatch, tmp_path)
    calls = fake_popen(monkeypatch)
    name, result = registry.run_tool_call({
        "function": {
            "name": "open_application",
            "arguments": {"name": "notepad"},
        }
    })
    assert name == "open_application"
    assert "opened successfully" in result
    assert calls == [([str(root / "System32" / "notepad.exe")],
                      {"shell": False})]


def test_registry_rejects_extra_arguments(monkeypatch):
    calls = fake_popen(monkeypatch)
    name, result = registry.run_tool_call({
        "function": {
            "name": "open_application",
            "arguments": {"name": "notepad", "path": "C:\\evil.exe"},
        }
    })
    assert name == "open_application"
    assert "Nothing was executed" in result
    assert calls == []


def test_debug_logging_when_enabled(monkeypatch, tmp_path, capsys):
    fake_windows(monkeypatch, tmp_path)
    fake_popen(monkeypatch)
    monkeypatch.setattr(config, "TOOL_LOG", True)
    windows_apps.open_application("notepad")
    out = capsys.readouterr().out
    assert "[tool] open_application requested name=notepad" in out
    assert "[tool] open_application success name=notepad" in out


def test_no_logging_by_default(monkeypatch, tmp_path, capsys):
    fake_windows(monkeypatch, tmp_path)
    fake_popen(monkeypatch)
    windows_apps.open_application("notepad")
    assert capsys.readouterr().out == ""
