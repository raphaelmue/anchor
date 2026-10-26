import io

import numpy as np
import pytest
import soundfile as sf

from anchor.audio import SAMPLE_RATE
from anchor.audio.decode import decode
from anchor.audio.loudness import integrated_loudness, normalize, short_term_loudness
from anchor.audio.trim import MARGIN_SEC, trim, voiced_span
from anchor.tts.fake import FakeTTSAdapter

SR = SAMPLE_RATE


def fake_unit(text="Atme ruhig ein und wieder aus.", **kw) -> np.ndarray:
    return decode(FakeTTSAdapter(**kw).synthesize(text, language="de-DE").wav)


# -- 5.1 decode --------------------------------------------------------------------------------


def test_decode_resamples_22050_to_48000():
    buf = io.BytesIO()
    sf.write(buf, np.sin(np.arange(22050) / 10).astype(np.float32) * 0.5, 22050, format="WAV")
    audio = decode(buf.getvalue())
    assert audio.dtype == np.float32 and audio.ndim == 1
    assert audio.size == pytest.approx(48000, abs=2)


def test_decode_downmixes_stereo():
    buf = io.BytesIO()
    sf.write(buf, np.zeros((44100, 2), dtype=np.float32), 44100, format="WAV")
    assert decode(buf.getvalue()).size == pytest.approx(48000, abs=2)


def test_decode_rejects_garbage():
    from anchor.ffmpeg import FFmpegError

    with pytest.raises(FFmpegError):
        decode(b"definitely not audio")


# -- 5.3 trimming ------------------------------------------------------------------------------


def margins(unit: np.ndarray) -> tuple[int, int]:
    start, end = voiced_span(unit)
    return start, unit.size - end


def test_trailing_padding_differences_end_up_identical():
    short = trim(fake_unit(trail_silence_sec=0.05))
    long = trim(fake_unit(trail_silence_sec=0.4))
    expected = round(MARGIN_SEC * SR)
    assert margins(short) == margins(long)
    assert margins(short)[1] == pytest.approx(expected, abs=1)
    assert short.size == long.size


def test_engine_margin_shorter_than_target_is_padded():
    unit = trim(fake_unit(lead_silence_sec=0.0, trail_silence_sec=0.0))
    assert margins(unit) == pytest.approx((int(MARGIN_SEC * SR), int(MARGIN_SEC * SR)), abs=1)


def test_voiced_samples_unchanged():
    raw = fake_unit()
    start, end = voiced_span(raw)
    trimmed = trim(raw)
    margin, ramp = round(MARGIN_SEC * SR), round(0.005 * SR)
    # Voiced part sits exactly after the margin, bit-identical; only the outer ramps differ.
    np.testing.assert_array_equal(trimmed[margin : margin + end - start], raw[start:end])
    np.testing.assert_array_equal(trimmed[ramp:-ramp],
                                  raw[start - margin + ramp : end + margin - ramp])


def test_ramp_only_inside_margin():
    trimmed = trim(fake_unit(lead_silence_sec=0.3, trail_silence_sec=0.3))
    margin = round(MARGIN_SEC * SR)
    assert trimmed[0] == 0.0 and trimmed[-1] == 0.0
    start, end = voiced_span(trimmed)
    assert start >= margin - 1 and trimmed.size - end >= margin - 1


def test_soft_onset_kept():
    sr = SR
    loud = 0.5 * np.sin(2 * np.pi * 200 * np.arange(sr // 2) / sr)
    soft = 0.01 * np.sin(2 * np.pi * 3000 * np.arange(sr // 10) / sr)  # breathy "h", -34 dB
    unit = np.concatenate([np.zeros(sr // 5), soft, loud, np.zeros(sr // 5)]).astype(np.float32)
    start, _ = voiced_span(unit)
    assert start <= sr // 5 + 5


def test_silent_unit():
    assert not np.any(trim(np.zeros(1000, dtype=np.float32)))


# -- 5.4 loudness ------------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["Atme ruhig ein und wieder aus, ganz langsam.", "Ja."])
def test_units_at_different_levels_match_within_2_lu(text):
    quiet = trim(fake_unit(text, level_dbfs=-35))
    loud = trim(fake_unit(text, level_dbfs=-8))
    a, b = normalize(quiet, -18), normalize(loud, -18)
    assert abs(short_term_loudness(a) - short_term_loudness(b)) <= 2.0
    assert integrated_loudness(a) == pytest.approx(-18, abs=1.0)


def test_short_unit_fallback_is_accurate():
    unit = trim(fake_unit("Ja.", level_dbfs=-20))  # ~0.26 s, shorter than one BS.1770 block
    assert unit.size < 0.4 * SR
    tiled = np.tile(unit, 8)  # same content, long enough for a direct measurement
    assert integrated_loudness(unit) == pytest.approx(integrated_loudness(tiled), abs=1.0)
