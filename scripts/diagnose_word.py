"""Read-only diagnostics for Celine's Microsoft Word integration.

This developer script inspects native window and COM metadata only. It does
not call Celine's public Word tool and does not invoke any content mutation.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pythoncom  # noqa: E402
import pywintypes  # noqa: E402
from pywinauto.controls.hwndwrapper import HwndWrapper  # noqa: E402
from win32com.client import GetActiveObject  # noqa: E402

from celine.tools.window_control import (  # noqa: E402
    WINDOW_TARGETS,
    _find_window,
    _find_windows,
    _matches,
    _process_name,
    _title,
)


WORD_PROGID = "Word.Application"
WORD_TYPELIB = pywintypes.IID("{00020905-0000-0000-C000-000000000046}")
WORD_TYPELIB_MAJOR = 8
WORD_TYPELIB_MINOR = 7
GA_ROOT = 2


def show_exception(label, exc):
    print(f"{label}: FAIL")
    print(f"  exception_class={type(exc).__module__}.{type(exc).__name__}")
    print(f"  message={exc}")
    print(f"  hresult={getattr(exc, 'hresult', None)!r}")
    print(f"  excepinfo={getattr(exc, 'excepinfo', None)!r}")
    print(f"  argerror={getattr(exc, 'argerror', None)!r}")


def protection_constants():
    """Read WdProtectionType values from the registered Word type library."""
    values = {}
    type_library = pythoncom.LoadRegTypeLib(
        WORD_TYPELIB,
        WORD_TYPELIB_MAJOR,
        WORD_TYPELIB_MINOR,
        0,
    )
    for index in range(type_library.GetTypeInfoCount()):
        if type_library.GetDocumentation(index)[0] != "WdProtectionType":
            continue
        type_info = type_library.GetTypeInfo(index)
        attributes = type_info.GetTypeAttr()
        for variable_index in range(attributes.cVars):
            variable = type_info.GetVarDesc(variable_index)
            name = type_info.GetNames(variable.memid)[0]
            values[name] = int(variable.value)
        break
    return values


def hwnd_member_owners():
    """Return Word type-library interfaces that actually expose Hwnd."""
    owners = []
    type_library = pythoncom.LoadRegTypeLib(
        WORD_TYPELIB,
        WORD_TYPELIB_MAJOR,
        WORD_TYPELIB_MINOR,
        0,
    )
    for index in range(type_library.GetTypeInfoCount()):
        type_info = type_library.GetTypeInfo(index)
        attributes = type_info.GetTypeAttr()
        owner = type_library.GetDocumentation(index)[0]
        for function_index in range(attributes.cFuncs):
            descriptor = type_info.GetFuncDesc(function_index)
            names = type_info.GetNames(descriptor.memid)
            if names and names[0].lower() == "hwnd":
                owners.append(f"{owner}.{names[0]}")
    return owners


def native_diagnostics():
    print("=== Native Word window diagnostics ===")
    rule = WINDOW_TARGETS["word"]
    all_windows = _find_windows()
    candidates = [item for item in all_windows if _matches(item, rule)]
    handles = sorted({int(item.handle) for item in candidates})
    print(f"visible_top_level_windows={len(all_windows)}")
    print(f"trusted_word_targets={len(handles)}")
    for index, item in enumerate(candidates, start=1):
        hwnd = int(item.handle)
        pid = int(getattr(item, "process_id", 0) or 0)
        class_name = getattr(item, "class_name", "") or ""
        try:
            enabled = bool(HwndWrapper(hwnd).is_enabled())
        except Exception as exc:
            enabled = f"ERROR: {type(exc).__name__}: {exc}"
        print(f"candidate[{index}].hwnd={hwnd}")
        print(f"candidate[{index}].process={_process_name(pid)}")
        print(f"candidate[{index}].class={class_name}")
        print(f"candidate[{index}].title={_title(item)}")
        print(f"candidate[{index}].enabled={enabled}")

    try:
        production_handle = _find_window("word")
        print(f"production__find_window_result={production_handle!r}")
        print(
            "production__find_window_ambiguity_note="
            "returns the first match and does not itself detect ambiguity"
        )
    except Exception as exc:
        show_exception("production__find_window", exc)
        production_handle = None
    return handles, production_handle


def main():
    print("READ-ONLY WORD DIAGNOSTIC; NO WRITE OPERATION WILL BE CALLED")
    checkpoints = {letter: (False, "not reached") for letter in "ABCDEFGHIJKL"}

    try:
        handles, first_handle = native_diagnostics()
    except Exception as exc:
        show_exception("native_window_discovery", exc)
        handles, first_handle = [], None

    checkpoints["A"] = (
        len(handles) == 1,
        f"trusted target count={len(handles)}",
    )
    trusted_hwnd = handles[0] if len(handles) == 1 else None

    enabled = None
    if trusted_hwnd is not None:
        try:
            enabled = bool(HwndWrapper(trusted_hwnd).is_enabled())
            checkpoints["B"] = (enabled, f"is_enabled={enabled}")
        except Exception as exc:
            checkpoints["B"] = (False, f"{type(exc).__name__}: {exc}")

    print("\n=== COM attachment diagnostics ===")
    application = None
    document = None
    content = None
    com_values = {}
    pythoncom.CoInitialize()
    try:
        try:
            application = GetActiveObject(WORD_PROGID)
            checkpoints["C"] = (True, "GetActiveObject succeeded")
            print("attachment=SUCCEEDED")
        except Exception as exc:
            checkpoints["C"] = (False, f"{type(exc).__name__}: {exc}")
            show_exception("GetActiveObject", exc)

        if application is not None:
            fields = (
                ("Application.Hwnd", lambda: int(application.Hwnd)),
                ("Application.Visible", lambda: bool(application.Visible)),
                ("Documents.Count", lambda: int(application.Documents.Count)),
                ("Application.Windows.Count", lambda: int(application.Windows.Count)),
                (
                    "ProtectedViewWindows.Count",
                    lambda: int(application.ProtectedViewWindows.Count),
                ),
            )
            for label, getter in fields:
                try:
                    com_values[label] = getter()
                    print(f"{label}={com_values[label]!r}")
                except Exception as exc:
                    show_exception(label, exc)
            try:
                print(f"Word_type_library.Hwnd_members={hwnd_member_owners()!r}")
            except Exception as exc:
                show_exception("Word type-library Hwnd lookup", exc)

            com_hwnd = com_values.get("Application.Hwnd")
            hwnd_equal = trusted_hwnd is not None and com_hwnd == trusted_hwnd
            checkpoints["D"] = (
                hwnd_equal,
                f"native={trusted_hwnd!r}, COM={com_hwnd!r}",
            )
            checkpoints["E"] = (
                com_values.get("ProtectedViewWindows.Count") == 0,
                f"count={com_values.get('ProtectedViewWindows.Count')!r}",
            )
            checkpoints["F"] = (
                com_values.get("Documents.Count") == 1,
                f"count={com_values.get('Documents.Count')!r}",
            )
            checkpoints["G"] = (
                com_values.get("Application.Windows.Count") == 1,
                f"count={com_values.get('Application.Windows.Count')!r}",
            )

            print("\n=== Native HWND vs COM HWND ===")
            print(f"native_trusted_hwnd={trusted_hwnd!r}")
            print(f"com_application_hwnd={com_hwnd!r}")
            print(f"exact_equality={hwnd_equal}")
            if com_hwnd is not None:
                user32 = ctypes.windll.user32
                com_root = int(user32.GetAncestor(int(com_hwnd), GA_ROOT) or 0)
                com_parent = int(user32.GetParent(int(com_hwnd)) or 0)
                print(f"com_hwnd_parent={com_parent}")
                print(f"com_hwnd_root={com_root}")
                if trusted_hwnd is not None:
                    native_root = int(
                        user32.GetAncestor(int(trusted_hwnd), GA_ROOT) or 0
                    )
                    native_parent = int(user32.GetParent(int(trusted_hwnd)) or 0)
                    print(f"native_hwnd_parent={native_parent}")
                    print(f"native_hwnd_root={native_root}")
                    print(f"same_root={com_root == native_root}")

            if com_values.get("Documents.Count") == 1:
                print("\n=== Document metadata diagnostics ===")
                try:
                    document = application.Documents.Item(1)
                    document_values = {
                        "document.Name": document.Name,
                        "document.ReadOnly": bool(document.ReadOnly),
                        "document.ProtectionType": int(document.ProtectionType),
                        "document.Windows.Count": int(document.Windows.Count),
                        "Application.Windows.Item(1).Hwnd": int(
                            application.Windows.Item(1).Hwnd
                        ),
                        "Document.Windows.Item(1).Hwnd": int(
                            document.Windows.Item(1).Hwnd
                        ),
                    }
                    content = document.Content
                    document_values["document.Content.Start"] = int(content.Start)
                    document_values["document.Content.End"] = int(content.End)
                    for label, value in document_values.items():
                        print(f"{label}={value!r}")
                    print(
                        "Application.Windows.Item(1).Hwnd_matches_native="
                        f"{document_values['Application.Windows.Item(1).Hwnd'] == trusted_hwnd}"
                    )
                    print(
                        "Document.Windows.Item(1).Hwnd_matches_native="
                        f"{document_values['Document.Windows.Item(1).Hwnd'] == trusted_hwnd}"
                    )

                    checkpoints["H"] = (
                        document_values["document.Windows.Count"] == 1,
                        f"count={document_values['document.Windows.Count']}",
                    )
                    checkpoints["I"] = (
                        document_values["document.ReadOnly"] is False,
                        f"ReadOnly={document_values['document.ReadOnly']}",
                    )
                    try:
                        constants = protection_constants()
                        print(f"WdProtectionType.constants={constants!r}")
                        no_protection = constants.get("wdNoProtection")
                    except Exception as exc:
                        show_exception("WdProtectionType type-library lookup", exc)
                        no_protection = -1
                    checkpoints["J"] = (
                        document_values["document.ProtectionType"]
                        == no_protection,
                        "ProtectionType="
                        f"{document_values['document.ProtectionType']}, "
                        f"wdNoProtection={no_protection}",
                    )
                    editable = (
                        checkpoints["B"][0]
                        and checkpoints["E"][0]
                        and checkpoints["I"][0]
                        and checkpoints["J"][0]
                    )
                    checkpoints["K"] = (
                        editable,
                        "enabled, not Protected View, not read-only, "
                        "and wdNoProtection",
                    )
                    checkpoints["L"] = (
                        True,
                        "Content.Start and Content.End obtained without Text",
                    )
                except Exception as exc:
                    show_exception("document_metadata", exc)

    finally:
        content = None
        document = None
        application = None
        pythoncom.CoUninitialize()

    print("\n=== Production pre-write checkpoints ===")
    labels = {
        "A": "exactly one trusted Word target",
        "B": "trusted HWND enabled",
        "C": "GetActiveObject succeeds",
        "D": "COM HWND matches trusted HWND",
        "E": "ProtectedViewWindows.Count == 0",
        "F": "Documents.Count == 1",
        "G": "Application.Windows.Count == 1",
        "H": "Document.Windows.Count == 1",
        "I": "Document.ReadOnly == False",
        "J": "Document.ProtectionType is wdNoProtection",
        "K": "document metadata indicates editable",
        "L": "range metadata can be obtained",
    }
    for letter in "ABCDEFGHIJKL":
        passed, detail = checkpoints[letter]
        print(f"{letter}. {'PASS' if passed else 'FAIL'} - {labels[letter]} ({detail})")

    first_failure = next(
        (letter for letter in "ABCDEFGHIJKL" if not checkpoints[letter][0]),
        None,
    )
    print(f"\nfirst_failing_checkpoint={first_failure or 'NONE'}")
    print("write_attempted=False")


if __name__ == "__main__":
    main()
