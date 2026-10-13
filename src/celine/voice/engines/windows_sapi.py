"""Offline text-to-speech through the Windows SAPI voice (via pywin32/COM).

This engine only ever creates the fixed ``SAPI.SpVoice`` COM object and calls
its documented voice/rate/volume/Speak methods. It never executes a shell
command and never accepts an executable path or arbitrary COM ProgID from the
model. Everything runs locally with voices already installed on the machine.
"""

from typing import Optional

from celine.voice.engines import VoiceError, VoiceInfo

try:  # pragma: no cover - import behaviour is platform dependent
    import pythoncom
    import win32com.client
    _COM_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # noqa: BLE001 - any import failure disables the engine
    pythoncom = None
    win32com = None
    _COM_IMPORT_ERROR = exc


SAPI_PROGID = "SAPI.SpVoice"

# Windows language identifiers (LCIDs) for the English locales we care about.
# SAPI reports the language as a hexadecimal string such as "409" (en-US).
_LANGUAGE_LOCALES = {
    0x0409: "en-US",
    0x0809: "en-GB",
    0x0C09: "en-AU",
    0x1009: "en-CA",
    0x1809: "en-IE",
    0x2009: "en-IN",
    0x2809: "en-NZ",
    0x2C09: "en-ZA",
    0x3C09: "en-SG",
}


def locale_from_language(value):
    """Map a SAPI language attribute to a locale, honestly marking unknowns."""
    if value in (None, ""):
        return "unknown"
    try:
        lcid = int(str(value).strip(), 16)
    except (TypeError, ValueError):
        return "unknown"
    return _LANGUAGE_LOCALES.get(lcid, f"lcid-0x{lcid:04x}")


def _attribute(token, name):
    try:
        return token.GetAttribute(name)
    except Exception:
        return None


class WindowsSapiEngine:
    """Synchronous SAPI playback with strict, fixed COM usage."""

    name = "windows_sapi"

    def __init__(self, *, dispatch=None):
        self._dispatch = dispatch
        self._value = None
        self._tokens = {}
        self._initialized = False
        self._com_import_error = _COM_IMPORT_ERROR

    def available(self):
        if self._com_import_error is not None:
            return False
        try:
            self._ensure_value()
            return True
        except Exception:
            return False

    def _ensure_value(self):
        if self._value is not None:
            return
        if pythoncom is not None:
            pythoncom.CoInitialize()
            self._initialized = True
        dispatch = self._dispatch or win32com.client.Dispatch
        self._value = dispatch(SAPI_PROGID)

    def list_voices(self):
        self._ensure_value()
        voices = []
        self._tokens = {}
        try:
            collection = self._value.GetVoices()
        except Exception as exc:
            raise VoiceError(f"could not list SAPI voices: {exc}") from exc

        for token in collection:
            description = self._token_description(token)
            name = str(_attribute(token, "Name") or description)
            gender = str(_attribute(token, "Gender") or "unknown")
            locale = locale_from_language(_attribute(token, "Language"))
            voice_id = self._token_id(token, name)
            self._tokens[voice_id] = token
            voices.append(
                VoiceInfo(
                    name=name,
                    locale=locale,
                    gender=gender,
                    engine_voice_id=voice_id,
                )
            )
        return voices

    @staticmethod
    def _token_description(token):
        try:
            return str(token.GetDescription())
        except Exception:
            return "unknown"

    @staticmethod
    def _token_id(token, fallback):
        try:
            return str(token.Id)
        except Exception:
            return fallback

    def speak(self, text, *, rate=0, volume=100, voice_id=None):
        self._ensure_value()
        if voice_id is not None:
            token = self._tokens.get(voice_id)
            if token is not None:
                try:
                    self._value.Voice = token
                except Exception as exc:
                    raise VoiceError(
                        f"could not select the chosen voice: {exc}"
                    ) from exc
        try:
            self._value.Rate = int(rate)
            self._value.Volume = int(volume)
        except Exception as exc:
            raise VoiceError(f"could not configure playback: {exc}") from exc
        try:
            # Flags=0 is synchronous: Speak returns after playback finishes.
            self._value.Speak(str(text))
        except Exception as exc:
            raise VoiceError(f"playback failed: {exc}") from exc

    def stop(self):
        if self._value is None:
            return
        try:
            self._value.Speak("", 3)  # SVSFPurgeBeforeSpeak
        except Exception:
            pass

    def shutdown(self):
        self._tokens = {}
        if self._value is not None:
            try:
                self._value.Stop()
            except Exception:
                pass
            self._value = None
        if self._initialized and pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
            self._initialized = False
