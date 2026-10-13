"""Trusted Windows Known Folder resolution for Word saves."""

import ctypes
import uuid
from pathlib import Path


APPROVED_SAVE_FOLDERS = ("documents", "desktop", "downloads")
_KNOWN_FOLDER_IDS = {
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
}


class _Guid(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    ]


def _guid(value):
    raw = uuid.UUID(value).bytes_le
    return _Guid.from_buffer_copy(raw)


def _known_folder_path(folder_id):
    """Resolve one fixed known-folder GUID with the Windows Shell API."""
    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(_Guid),
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]

    known_folder = _guid(folder_id)
    result = ctypes.c_wchar_p()
    status = shell32.SHGetKnownFolderPath(
        ctypes.byref(known_folder),
        0,
        None,
        ctypes.byref(result),
    )
    if status != 0:
        raise OSError(status, "Windows Known Folder resolution failed")
    try:
        return Path(result.value)
    finally:
        ole32.CoTaskMemFree(ctypes.cast(result, ctypes.c_void_p))


def resolve_save_folder(folder, *, resolver=None):
    """Resolve one approved logical folder; never accept a filesystem path."""
    if not isinstance(folder, str):
        raise ValueError("folder must be a string")
    logical_name = folder.strip().lower()
    if logical_name not in _KNOWN_FOLDER_IDS:
        raise ValueError("folder is not approved")
    known_folder_resolver = resolver or _known_folder_path
    path = known_folder_resolver(_KNOWN_FOLDER_IDS[logical_name])
    if not path:
        raise OSError("Windows Known Folder returned no path")
    return logical_name, Path(path)
