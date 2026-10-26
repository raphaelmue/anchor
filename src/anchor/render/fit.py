"""Elastic duration fitting (design D7, FR-52)."""

from dataclasses import dataclass

from anchor.render.errors import RenderError
from anchor.render.layout import Layout

TOLERANCE = 0.10


@dataclass(frozen=True)
class FittedPause:
    segment_index: int
    seconds: float
    fitted_sec: float
    elastic: tuple[float, float]


def fit(layout: Layout, target_sec: float) -> list[FittedPause]:
    """Stretch or shrink Elastic Pauses in place, proportionally to their flexibility, aiming at
    the exact target; fail if the result is still outside ±10 % of the target."""
    sr = layout.sample_rate
    elastic = [b for b in layout.blocks if b.is_elastic]
    fixed = layout.total_sec - sum(b.samples for b in elastic) / sr
    delta = target_sec - layout.total_sec

    if delta > 0:
        room = sum(b.elastic[1] - b.samples / sr for b in elastic)
        frac = min(1.0, delta / room) if room > 0 else 0.0
        for b in elastic:
            current = b.samples / sr
            b.samples = round((current + frac * (b.elastic[1] - current)) * sr)
    elif delta < 0:
        room = sum(b.samples / sr - b.elastic[0] for b in elastic)
        frac = min(1.0, -delta / room) if room > 0 else 0.0
        for b in elastic:
            current = b.samples / sr
            b.samples = round((current - frac * (current - b.elastic[0])) * sr)

    if abs(layout.total_sec - target_sec) > TOLERANCE * target_sec:
        lo = fixed + sum(b.elastic[0] for b in elastic)
        hi = fixed + sum(b.elastic[1] for b in elastic)
        raise RenderError(
            f"cannot fit target duration {target_sec:.0f} s (±10 %: "
            f"{target_sec * (1 - TOLERANCE):.0f}–{target_sec * (1 + TOLERANCE):.0f} s): "
            f"achievable range is {lo:.1f}–{hi:.1f} s "
            f"({len(elastic)} Elastic Pause(s), {fixed:.1f} s fixed)")

    return [FittedPause(b.segment_index, b.seconds, b.samples / sr, b.elastic) for b in elastic]
