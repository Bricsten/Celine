"""Offline microphone capture through the ``sounddevice`` PortAudio bindings.

The recorder opens the system input device for one short, bounded clip and
returns raw 16-bit *mono* PCM at the recogniser rate. It never listens in the
background, never writes audio to disk, and always releases the device when the
clip ends. The device and timing come from trusted local configuration, never
from the model.

Capture is negotiated against the device: the recogniser rate is used when the
device accepts it, otherwise the device's native rate is captured and properly
resampled (never merely relabelled). Multi-channel devices are downmixed to
mono. If ``sounddevice`` (or an input device) is unavailable, ``available()``
returns ``False`` and the caller stays silent rather than pretending to listen.
"""

import time

from celine.core import config
from celine.voice.input import InputError, Recording
from celine.voice.input import audio

try:  # sounddevice is an optional dependency, bundled PortAudio on Windows
    import sounddevice as _sd

    _SD_IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - any import failure disables capture
    _sd = None
    _SD_IMPORT_ERROR = exc


def list_input_devices():
    """Return the available input devices as plain dicts (safe metadata)."""
    if _sd is None:
        return []
    try:
        devices = _sd.query_devices()
    except Exception:  # noqa: BLE001 - never let enumeration crash Celine
        return []
    result = []
    for index, info in enumerate(devices):
        try:
            channels = int(info.get("max_input_channels") or 0)
        except (TypeError, ValueError):
            channels = 0
        if channels <= 0:
            continue
        result.append(
            {
                "index": index,
                "name": str(info.get("name") or "unknown"),
                "channels": channels,
                "default_samplerate": int(
                    round(float(info.get("default_samplerate") or 0))
                ),
            }
        )
    return result


def _should_stop(stop):
    """Accept a threading.Event, a callable, or a plain truthy value."""
    if stop is None:
        return False
    is_set = getattr(stop, "is_set", None)
    if callable(is_set):
        return bool(is_set())
    if callable(stop):
        return bool(stop())
    return bool(stop)


class Microphone:
    """One bounded recording from the default (or configured) input device."""

    name = "sounddevice"

    def __init__(
        self,
        *,
        samplerate=None,
        channels=None,
        device=None,
        block_seconds=0.1,
        stream_factory=None,
        warmup_seconds=None,
    ):
        self._samplerate = int(
            config.MICROPHONE_SAMPLE_RATE if samplerate is None else samplerate
        )
        self._channels = int(
            config.MICROPHONE_CHANNELS if channels is None else channels
        )
        self._device = config.MICROPHONE_DEVICE if device is None else device
        self._block_seconds = max(0.01, float(block_seconds))
        self._warmup_seconds = max(
            0.0,
            float(
                config.MICROPHONE_WARMUP_SECONDS
                if warmup_seconds is None
                else warmup_seconds
            ),
        )
        # Injectable seam: tests supply a fake stream and never open hardware.
        self._stream_factory = stream_factory
        self._closed = False
        # Filled in per recording for honest diagnostics.
        self._last_source_rate = self._samplerate
        self._last_channels = self._channels

    def available(self):
        """True when a capture backend and an input device are usable."""
        if self._stream_factory is not None:
            return True
        if _SD_IMPORT_ERROR is not None or _sd is None:
            return False
        if self._device is not None:
            try:
                info = _sd.query_devices(self._device, "input")
                return int(info.get("max_input_channels") or 0) > 0
            except Exception:  # noqa: BLE001 - configured device unusable
                return False
        try:
            _sd.query_devices(kind="input")
            return True
        except Exception:  # noqa: BLE001 - no usable input device
            return False

    def device_info(self):
        """Describe the selected device/backend without opening it."""
        return {
            "backend": self.name,
            "device": self._device,
            "channels": self._channels,
            "target_samplerate": self._samplerate,
            "warming_up_seconds": self._warmup_seconds,
        }

    def _resolve_capture_format(self):
        """Negotiate ``(samplerate, channels, needs_resample)`` for this device."""
        if self._stream_factory is not None or _sd is None:
            return self._samplerate, self._channels, False
        try:
            info = _sd.query_devices(self._device, "input")
            device_channels = max(1, int(info.get("max_input_channels") or 1))
            default_rate = int(
                round(float(info.get("default_samplerate") or self._samplerate))
            )
        except Exception:  # noqa: BLE001 - fall back to configured values
            device_channels, default_rate = self._channels, self._samplerate

        candidates = (
            (self._samplerate, self._channels),
            (self._samplerate, device_channels),
            (default_rate, device_channels),
        )
        for rate, channels in candidates:
            if rate <= 0 or channels <= 0:
                continue
            try:
                _sd.check_input_settings(
                    device=self._device,
                    samplerate=rate,
                    channels=channels,
                    dtype="int16",
                )
                return rate, channels, rate != self._samplerate
            except Exception:  # noqa: BLE001 - try the next candidate
                continue
        return default_rate, device_channels, default_rate != self._samplerate

    def _open_stream(self, samplerate, channels):
        if self._stream_factory is not None:
            return self._stream_factory(
                samplerate=samplerate,
                channels=channels,
                dtype="int16",
                device=self._device,
            )
        return _sd.RawInputStream(
            samplerate=samplerate,
            channels=channels,
            dtype="int16",
            device=self._device,
        )

    def record(self, *, max_seconds=None, stop=None):
        """Capture one clip, stopped by ``stop`` or the ``max_seconds`` cap."""
        if self._closed:
            raise InputError("microphone is closed")
        if not self.available():
            raise InputError("no microphone backend is available")

        try:
            limit = float(
                config.MICROPHONE_MAX_SECONDS if max_seconds is None else max_seconds
            )
        except (TypeError, ValueError):
            limit = float(config.MICROPHONE_MAX_SECONDS)
        limit = max(0.1, limit)

        rate, channels, needs_resample = self._resolve_capture_format()
        self._last_source_rate = rate
        self._last_channels = channels
        block_frames = max(1, int(rate * self._block_seconds))
        warmup_frames = (
            int(rate * self._warmup_seconds)
            if self._stream_factory is None
            else 0
        )

        chunks = []
        overflowed = 0
        truncated = False
        started = time.perf_counter()
        try:
            with self._open_stream(rate, channels) as stream:
                warmup_remaining = warmup_frames
                while warmup_remaining > 0:
                    block, _overflow = stream.read(
                        min(block_frames, warmup_remaining)
                    )
                    if not block:
                        break
                    warmup_remaining -= len(block) // (2 * channels)
                while True:
                    if _should_stop(stop):
                        break
                    if time.perf_counter() - started >= limit:
                        truncated = True
                        break
                    block, overflow = stream.read(block_frames)
                    if block:
                        chunks.append(bytes(block))
                    if overflow:
                        overflowed += 1
        except InputError:
            raise
        except Exception as exc:  # noqa: BLE001 - report, do not crash Celine
            raise InputError(f"could not record from the microphone: {exc}") from exc

        elapsed = time.perf_counter() - started
        raw = b"".join(chunks)
        pcm = self._prepare_pcm(raw, rate, channels, needs_resample)
        return Recording(
            pcm=pcm,
            samplerate=self._samplerate,
            seconds=elapsed,
            truncated=truncated,
            channels=1,
            source_samplerate=rate,
            overflowed=overflowed,
        )

    def _prepare_pcm(self, raw, rate, channels, needs_resample):
        """Raw device bytes -> mono 16-bit PCM at the recogniser rate."""
        if not raw:
            return b""
        samples = audio.pcm_to_samples(raw)
        if channels > 1:
            samples = audio.to_mono(samples, channels)
        if needs_resample and rate != self._samplerate:
            samples = audio.resample(samples, rate, self._samplerate)
        return audio.samples_to_pcm(samples)

    def close(self):
        """Nothing is kept open between recordings; this is a safe no-op."""
        self._closed = True
