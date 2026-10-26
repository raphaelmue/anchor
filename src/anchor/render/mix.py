"""Mixing: Noise Floor over the full length, speech and sounds on top, fades (design D3).

Fades apply to the background only: speech and sounds are added after the fades, so voiced
samples are never attenuated.
"""

import numpy as np

from anchor.audio.beds import bed_track
from anchor.render.layout import Layout


def _ramp(n: int) -> np.ndarray:
    """Raised-cosine ramp from 0 to 1 over n samples."""
    return (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n, dtype=np.float64))).astype(np.float32)


def mix(layout: Layout, *, bed_level_lufs: float, fade_in_sec: float,
        seed: int = 1) -> np.ndarray:
    total = layout.total_samples
    positions = layout.positions()
    switches = [(pos, b.name) for b, pos in zip(layout.blocks, positions, strict=True)
                if b.kind == "ambience"]
    out = bed_track(total, switches, level_lufs=bed_level_lufs, seed=seed,
                    sample_rate=layout.sample_rate)

    fade_in = min(round(fade_in_sec * layout.sample_rate), total)
    if fade_in:
        out[:fade_in] *= _ramp(fade_in)
    if layout.tail:
        tail = min(layout.tail, total)
        out[total - tail :] *= _ramp(tail)[::-1]

    for block, pos in zip(layout.blocks, positions, strict=True):
        if block.audio is not None:
            out[pos : pos + block.audio.size] += block.audio
    return out
