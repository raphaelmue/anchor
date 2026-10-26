"""Silence trimming to a fixed margin (design D4).

The voiced span is found with 10 ms RMS windows against a threshold relative to the unit's peak,
then refined to the first/last sample above the threshold. Exactly `margin_sec` is kept on both
sides (zero-padded if the engine gave less). A short de-click ramp is applied only inside the
margin, so voiced samples are never faded.
"""

import numpy as np

from anchor.audio import SAMPLE_RATE

MARGIN_SEC = 0.030
RAMP_SEC = 0.005
WINDOW_SEC = 0.010
THRESHOLD_DB = -45.0


def voiced_span(audio: np.ndarray, *, sample_rate: int = SAMPLE_RATE,
                threshold_db: float = THRESHOLD_DB) -> tuple[int, int] | None:
    """[start, end) of the voiced part, or None if the unit is silent."""
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak == 0.0:
        return None
    thr = peak * 10 ** (threshold_db / 20)
    win = max(1, int(WINDOW_SEC * sample_rate))
    n_win = int(np.ceil(audio.size / win))
    padded = np.zeros(n_win * win, dtype=np.float64)
    padded[: audio.size] = audio
    rms = np.sqrt(np.mean(padded.reshape(n_win, win) ** 2, axis=1))
    active = np.flatnonzero(rms >= thr)
    if active.size == 0:
        # Only isolated samples exceed the threshold; fall back to the sample-level span.
        active_samples = np.flatnonzero(np.abs(audio) >= thr)
        return int(active_samples[0]), int(active_samples[-1]) + 1
    first_win, last_win = int(active[0]), int(active[-1])
    lo, hi = first_win * win, min(audio.size, (last_win + 1) * win)
    above = np.flatnonzero(np.abs(audio[lo:hi]) >= thr)
    return lo + int(above[0]), lo + int(above[-1]) + 1


def trim(audio: np.ndarray, *, sample_rate: int = SAMPLE_RATE, margin_sec: float = MARGIN_SEC,
         ramp_sec: float = RAMP_SEC) -> np.ndarray:
    """Return the voiced part with exactly `margin_sec` before and after it."""
    span = voiced_span(audio, sample_rate=sample_rate)
    margin = round(margin_sec * sample_rate)
    if span is None:
        return np.zeros(2 * margin, dtype=np.float32)
    start, end = span
    out = np.zeros(margin + (end - start) + margin, dtype=np.float32)
    src_lo = max(0, start - margin)
    src_hi = min(audio.size, end + margin)
    dst_lo = margin - (start - src_lo)
    out[dst_lo : dst_lo + (src_hi - src_lo)] = audio[src_lo:src_hi]
    ramp = min(round(ramp_sec * sample_rate), margin)
    if ramp:
        fade = np.linspace(0.0, 1.0, ramp, endpoint=False, dtype=np.float32)
        out[:ramp] *= fade
        out[-ramp:] *= fade[::-1]
    return out
