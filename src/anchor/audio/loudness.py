"""Per-unit loudness normalization (design D5).

BS.1770 needs at least one 400 ms block. Shorter units are measured on a zero-padded copy, and
the result is corrected by the padding ratio. K-weighted loudness scales with mean square, so
padding n samples to N lowers the reading by 10·log10(N/n).
"""

import numpy as np
import pyloudnorm

from anchor.audio import SAMPLE_RATE

BLOCK_SEC = 0.4
_meters: dict[int, pyloudnorm.Meter] = {}


def _meter(sample_rate: int) -> pyloudnorm.Meter:
    if sample_rate not in _meters:
        _meters[sample_rate] = pyloudnorm.Meter(sample_rate, block_size=BLOCK_SEC)
    return _meters[sample_rate]


def integrated_loudness(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> float:
    block = int(np.ceil(BLOCK_SEC * sample_rate))
    data = audio.astype(np.float64)
    if data.size >= block:
        return float(_meter(sample_rate).integrated_loudness(data))
    if data.size == 0 or not np.any(data):
        return float("-inf")
    padded = np.zeros(block)
    padded[: data.size] = data
    measured = float(_meter(sample_rate).integrated_loudness(padded))
    return measured + 10 * np.log10(block / data.size)


def normalize(audio: np.ndarray, target_lufs: float,
              sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    loudness = integrated_loudness(audio, sample_rate)
    if not np.isfinite(loudness):
        return audio.astype(np.float32)
    gain = 10 ** ((target_lufs - loudness) / 20)
    return (audio * gain).astype(np.float32)


def short_term_loudness(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> float:
    """Loudness of a 3 s window centred on the unit (or the whole unit if shorter)."""
    window = 3 * sample_rate
    if audio.size > window:
        mid = audio.size // 2
        audio = audio[mid - window // 2 : mid + window // 2]
    return integrated_loudness(audio, sample_rate)
