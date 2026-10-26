"""Integration test against a running Speaches backend (`docker compose up -d speaches`).

Run with `uv run pytest -m speaches -s`; skipped automatically when the backend is unreachable.
"""

import io
import statistics

import numpy as np
import pytest
import soundfile as sf

from anchor.config import load_settings
from anchor.tts.factory import build_adapter

pytestmark = pytest.mark.speaches

SENTENCE = "Mach es dir bequem und atme ruhig ein und wieder aus."
# Piper randomizes phoneme durations (noise_w), so one clip varies by up to ~10 %;
# compare medians of several syntheses.
SAMPLES = 7


@pytest.fixture(scope="module")
def adapter():
    adapter = build_adapter(load_settings().tts)
    status = adapter.health()
    if not status.ok:
        pytest.skip(f"Speaches backend not available: {status.detail or 'unreachable'}")
    return adapter


def duration(result) -> float:
    """Voiced span (engine padding excluded): first to last sample above -40 dB of peak."""
    audio, sr = sf.read(io.BytesIO(result.wav))
    loud = np.flatnonzero(np.abs(audio) > np.abs(audio).max() * 10 ** (-40 / 20))
    return (loud[-1] - loud[0]) / sr


def test_german_sentence_and_speed(adapter, record_property):
    normal = [adapter.synthesize(SENTENCE, language="de-DE", speed=1.0) for _ in range(SAMPLES)]
    slow = [adapter.synthesize(SENTENCE, language="de-DE", speed=0.85) for _ in range(SAMPLES)]

    assert all(r.sample_rate == adapter.sample_rate for r in normal + slow)
    d_normal = statistics.median(map(duration, normal))
    d_slow = statistics.median(map(duration, slow))
    assert d_normal > 1.0

    ratio = d_slow / d_normal
    # Nominal 1/0.85 ≈ 1.18; Piper's length_scale stretches the voiced span by only ~1.07–1.12
    # (measured Oct 2026, thorsten-medium). Medians at equal speed agree within ~2 %.
    honored = ratio > 1.03
    record_property("speed_ratio", round(ratio, 3))
    record_property("speed_honored", honored)
    print(f"\nspeed 1.0: {d_normal:.2f}s, speed 0.85: {d_slow:.2f}s, "
          f"ratio {ratio:.3f} -> speed {'honored' if honored else 'IGNORED'}")
    assert honored, "backend ignores `speed`; pick a slower Voice instead of time-stretching"
