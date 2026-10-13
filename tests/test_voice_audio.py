"""Tests for the dependency-free audio helpers. All audio is synthetic."""

from array import array

from celine.voice.input import Recording
from celine.voice.input import audio


def make_pcm(values):
    return audio.samples_to_pcm(array("h", values))


def samples_of(signal):
    return audio.pcm_to_samples(make_pcm(signal))


def test_pcm_roundtrip_is_little_endian_signed_16bit():
    values = [0, 1, -1, 32767, -32768, 1234, -4321]
    pcm = audio.samples_to_pcm(array("h", values))
    assert pcm[:2] == b"\x00\x00"
    assert audio.pcm_to_samples(pcm) == array("h", values)


def test_pcm_to_samples_ignores_a_trailing_odd_byte():
    pcm = b"\x01\x00\x02"
    assert audio.pcm_to_samples(pcm) == array("h", [1])


def test_to_mono_averages_stereo_frames():
    stereo = array("h", [100, 200, 300, 400])
    assert audio.to_mono(stereo, 2) == array("h", [150, 350])


def test_to_mono_is_a_copy_for_mono():
    mono = array("h", [10, 20, 30])
    result = audio.to_mono(mono, 1)
    assert result == mono
    assert result is not mono


def test_resample_integer_ratio_decimates_without_relabelling():
    samples = array("h", [300, 300, 300, 600, 600, 600])
    out = audio.resample(samples, 48000, 16000)
    assert list(out) == [300, 600]


def test_resample_non_integer_ratio_changes_length():
    samples = array("h", [1000] * 4410)
    out = audio.resample(samples, 44100, 16000)
    assert len(out) == 1600
    assert set(out) <= {1000}


def test_resample_same_rate_returns_equivalent_samples():
    samples = array("h", [5, 6, 7])
    out = audio.resample(samples, 16000, 16000)
    assert out == samples


def test_resample_empty_and_invalid_rates_are_safe():
    assert audio.resample(array("h"), 48000, 16000) == array("h")
    assert audio.resample(array("h", [1, 2]), 0, 16000) == array("h", [1, 2])


def test_rms_and_peak_of_full_scale_signal():
    samples = array("h", [32767] * 100)
    assert audio.rms(samples) == 1.0
    assert audio.peak(samples) == 1.0


def test_rms_and_peak_of_silence():
    assert audio.rms(array("h", [0] * 10)) == 0.0
    assert audio.peak(array("h", [0] * 10)) == 0.0


def test_silence_and_clipping_ratios():
    samples = array("h", [32767, 32767, 0, 0])
    assert audio.clipping_ratio(samples) == 0.5
    assert audio.silence_ratio(samples) == 0.5
    assert audio.silence_ratio(array("h", [0, 0, 0])) == 1.0


def test_dbfs_handles_zero_and_full_scale():
    assert audio.dbfs(0.0) == float("-inf")
    assert round(audio.dbfs(1.0), 3) == 0.0


def test_analyse_reports_no_signal_for_silence():
    recording = Recording(make_pcm([0] * 1600), 16000, 0.1)
    stats = audio.analyse(recording)
    assert stats.frames_received is True
    assert stats.peak == 0.0
    assert stats.classification.startswith("no signal")


def test_analyse_detects_clipping():
    recording = Recording(make_pcm([32767] * 2000), 16000, 0.125)
    stats = audio.analyse(recording)
    assert stats.clipping_ratio >= 0.99
    assert "clipped" in stats.classification


def test_analyse_detects_mostly_silence():
    signal = [0] * 1600 + [20000] * 10
    recording = Recording(make_pcm(signal), 16000, 0.1)
    stats = audio.analyse(recording)
    assert stats.silence_ratio >= 0.9
    assert "silence" in stats.classification


def test_analyse_reports_valid_audio():
    signal = []
    for _ in range(10):
        signal.extend([8000] * 800)
        signal.extend([0] * 800)
    recording = Recording(make_pcm(signal), 16000, 1.0)
    stats = audio.analyse(recording)
    assert stats.frames_received is True
    assert stats.classification == "valid audio for recognition"


def test_classify_quiet_and_noisy_and_low_signal():
    assert "quiet" in audio.classify(0.008, 0.03, 0.2, 0.0, 20.0)
    assert "noise" in audio.classify(0.2, 0.5, 0.1, 0.0, 3.0)
    assert "no signal" in audio.classify(0.0, 0.0, 1.0, 0.0, float("-inf"))


def test_analyse_reports_safe_lines_without_audio():
    recording = Recording(make_pcm([1000] * 1600), 16000, 0.1)
    stats = audio.analyse(recording)
    joined = "\n".join(stats.report_lines())
    assert "Audio diagnostics" in joined
    assert "assessment" in joined
    assert "rate:" in joined
