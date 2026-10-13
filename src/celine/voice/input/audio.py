"""Lightweight, dependency-free audio helpers for Celine's input layer.

Everything here works on signed 16-bit little-endian PCM, which is the format
Vosk expects. The helpers convert channels, resample to the recogniser's rate,
and compute *safe* level statistics (RMS, peak, silence, clipping, estimated
noise floor). They never write audio to disk and never keep recordings.

The statistics are deliberately coarse: they are meant to tell "no signal",
"quiet", "noisy", or "clipped" apart so a human can fix the microphone setup,
not to rate speech content.
"""

import math
import sys
from array import array
from dataclasses import dataclass

_INT16_FULL_SCALE = 32767.0

# Coarse, documented heuristics (fractions of full scale unless noted).
_SILENCE_FRACTION = 0.005  # |sample| below this counts as silence (~-46 dBFS)
_CLIP_FRACTION = 0.99      # |sample| at/above this counts as clipped
_NO_SIGNAL_RMS_DBFS = -60.0
_QUIET_RMS_DBFS = -40.0
_SILENCE_RATIO = 0.90
_CLIP_RATIO = 0.01
_MIN_SNR_DB = 8.0


def pcm_to_samples(pcm):
    """Bytes -> ``array('h')`` of signed 16-bit samples (host-endian)."""
    usable = len(pcm) - (len(pcm) % 2)
    samples = array("h")
    samples.frombytes(pcm[:usable])
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def samples_to_pcm(samples):
    """``array('h')`` -> little-endian signed 16-bit bytes."""
    data = array("h", samples)
    if sys.byteorder == "big":
        data.byteswap()
    return data.tobytes()


def to_mono(samples, channels):
    """Downmix interleaved samples to mono by averaging each frame."""
    if channels <= 1:
        return array("h", samples)
    frames = len(samples) // channels
    out = array("h", [0]) * frames
    for i in range(frames):
        base = i * channels
        total = 0
        for c in range(channels):
            total += samples[base + c]
        out[i] = int(total / channels)
    return out


def _decimate(samples, factor):
    """Anti-aliased integer decimation: average each ``factor`` samples."""
    frames = len(samples) // factor
    out = array("h", [0]) * frames
    for i in range(frames):
        base = i * factor
        total = 0
        for j in range(factor):
            total += samples[base + j]
        out[i] = int(total / factor)
    return out


def _resample_linear(samples, src_rate, dst_rate):
    if not samples:
        return array("h")
    ratio = dst_rate / float(src_rate)
    out_len = int(len(samples) * ratio)
    if out_len <= 0:
        return array("h")
    last = len(samples) - 1
    out = array("h", [0]) * out_len
    for i in range(out_len):
        pos = i / ratio
        idx = int(pos)
        if idx >= last:
            out[i] = samples[last]
            continue
        frac = pos - idx
        a = samples[idx]
        b = samples[idx + 1]
        out[i] = int(a + (b - a) * frac)
    return out


def resample(samples, src_rate, dst_rate):
    """Resample mono samples; never merely relabels the sample rate.

    Integer ratios use an averaging (box) decimator for a little
    anti-aliasing; other ratios use linear interpolation.
    """
    src_rate = int(src_rate or 0)
    dst_rate = int(dst_rate or 0)
    if not samples or src_rate <= 0 or dst_rate <= 0 or src_rate == dst_rate:
        return array("h", samples)
    if src_rate % dst_rate == 0:
        return _decimate(samples, src_rate // dst_rate)
    return _resample_linear(samples, src_rate, dst_rate)


def rms(samples):
    if not samples:
        return 0.0
    total = 0.0
    for sample in samples:
        total += float(sample) * float(sample)
    return math.sqrt(total / len(samples)) / _INT16_FULL_SCALE


def peak(samples):
    if not samples:
        return 0.0
    return max(abs(sample) for sample in samples) / _INT16_FULL_SCALE


def silence_ratio(samples, threshold=_SILENCE_FRACTION):
    if not samples:
        return 1.0
    limit = threshold * _INT16_FULL_SCALE
    silent = sum(1 for sample in samples if abs(sample) < limit)
    return silent / len(samples)


def clipping_ratio(samples, threshold=_CLIP_FRACTION):
    if not samples:
        return 0.0
    limit = threshold * _INT16_FULL_SCALE
    clipped = sum(1 for sample in samples if abs(sample) >= limit)
    return clipped / len(samples)


def dbfs(fraction):
    """Amplitude fraction -> dBFS (``-inf`` for silence)."""
    if fraction <= 0:
        return float("-inf")
    return 20.0 * math.log10(fraction)


@dataclass(frozen=True)
class AudioStats:
    """Safe, aggregate audio measurements. Contains no speech content."""

    seconds: float
    samplerate: int
    source_samplerate: int | None
    channels: int
    sample_count: int
    rms: float
    peak: float
    silence_ratio: float
    clipping_ratio: float
    noise_floor: float
    snr_db: float
    frames_received: bool
    overflowed: int
    truncated: bool
    classification: str

    @property
    def rms_dbfs(self):
        return dbfs(self.rms)

    @property
    def peak_dbfs(self):
        return dbfs(self.peak)

    def report_lines(self):
        """Human-readable, privacy-safe lines for the ``/mic-test`` output."""
        source = self.source_samplerate or self.samplerate
        conversion = (
            f"{source} Hz -> {self.samplerate} Hz"
            if source != self.samplerate
            else f"{self.samplerate} Hz"
        )
        snr = "n/a" if math.isinf(self.snr_db) and self.snr_db < 0 else f"{self.snr_db:.1f} dB"
        return [
            "[mic] Audio diagnostics:",
            f"[mic]   duration: {self.seconds:.2f}s  samples: {self.sample_count}"
            f"  rate: {conversion}  channels: {self.channels}",
            f"[mic]   level: RMS {self.rms_dbfs:.1f} dBFS  peak {self.peak_dbfs:.1f} dBFS",
            f"[mic]   silence: {self.silence_ratio * 100:.0f}%  "
            f"clipping: {self.clipping_ratio * 100:.1f}%  est. SNR: {snr}",
            f"[mic]   frames received: {self.frames_received}  "
            f"overflowed: {self.overflowed}",
            f"[mic]   assessment: {self.classification}",
        ]


def _frame_rms_extremes(samples, samplerate):
    """Min/max RMS over ~50 ms frames, an estimate of the noise floor."""
    if not samples:
        return 0.0, 0.0
    frame_len = max(1, int(samplerate * 0.05)) if samplerate else 800
    lowest = None
    highest = 0.0
    for start in range(0, len(samples), frame_len):
        frame = samples[start:start + frame_len]
        if not frame:
            continue
        value = rms(frame)
        lowest = value if lowest is None else min(lowest, value)
        highest = max(highest, value)
    return (lowest or 0.0), highest


def classify(rms_value, peak_value, silence_value, clipping_value, snr_db):
    """Return a short, honest assessment of the captured signal."""
    if peak_value <= 0 or dbfs(rms_value) < _NO_SIGNAL_RMS_DBFS:
        return "no signal (the microphone produced silence)"
    if clipping_value >= _CLIP_RATIO:
        return "clipped or distorted (lower the Windows input level)"
    if silence_value >= _SILENCE_RATIO:
        return "mostly silence (microphone may be muted or too quiet)"
    if math.isfinite(snr_db) and snr_db < _MIN_SNR_DB:
        return "high background noise (move closer or reduce noise)"
    if dbfs(rms_value) < _QUIET_RMS_DBFS:
        return "quiet but present (speak closer or raise the Windows input level)"
    return "valid audio for recognition"


def analyse(recording):
    """Build :class:`AudioStats` from one :class:`Recording`. Never raises."""
    samples = pcm_to_samples(recording.pcm)
    if getattr(recording, "channels", 1) and recording.channels > 1:
        samples = to_mono(samples, recording.channels)
    rate = recording.samplerate or 0
    rms_value = rms(samples)
    peak_value = peak(samples)
    silence_value = silence_ratio(samples)
    clipping_value = clipping_ratio(samples)
    noise_floor, _loudest = _frame_rms_extremes(samples, rate)
    if noise_floor > 0 and peak_value > 0:
        snr_db = max(0.0, dbfs(rms(samples)) - dbfs(noise_floor))
    else:
        snr_db = float("-inf")
    return AudioStats(
        seconds=recording.seconds,
        samplerate=rate,
        source_samplerate=getattr(recording, "source_samplerate", None),
        channels=getattr(recording, "channels", 1),
        sample_count=len(samples),
        rms=rms_value,
        peak=peak_value,
        silence_ratio=silence_value,
        clipping_ratio=clipping_value,
        noise_floor=noise_floor,
        snr_db=snr_db,
        frames_received=len(samples) > 0,
        overflowed=getattr(recording, "overflowed", 0),
        truncated=getattr(recording, "truncated", False),
        classification=classify(
            rms_value, peak_value, silence_value, clipping_value, snr_db
        ),
    )
