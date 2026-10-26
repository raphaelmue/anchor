"""Procedural Noise Floor beds and built-in sounds (design D6).

Beds are shaped noise generated in the frequency domain as a seamless loop (random phases,
fixed seed), then tiled to the render length, so even a 30-minute Session costs one 60 s FFT.
Switching beds crossfades with equal power over `CROSSFADE_SEC`.
"""

from collections.abc import Callable
from functools import cache

import numpy as np

from anchor.audio import SAMPLE_RATE
from anchor.audio.loudness import integrated_loudness

LOOP_SEC = 60.0
CROSSFADE_SEC = 2.0
DEFAULT_BED = "room_tone"
DEFAULT_SEED = 1


def _room_tone_shape(freqs: np.ndarray) -> np.ndarray:
    # Pink (1/f power) with a gentle high-pass at 40 Hz and a roll-off above ~4 kHz.
    f = np.maximum(freqs, 1.0)
    pink = 1 / np.sqrt(f)
    highpass = 1 / np.sqrt(1 + (40 / f) ** 4)
    lowpass = 1 / np.sqrt(1 + (f / 4000) ** 4)
    return pink * highpass * lowpass


def _brown_noise_shape(freqs: np.ndarray) -> np.ndarray:
    # Brown (1/f^2 power), high-passed at 25 Hz so it carries no DC rumble.
    f = np.maximum(freqs, 1.0)
    return (1 / f) / np.sqrt(1 + (25 / f) ** 4)


BEDS: dict[str, Callable[[np.ndarray], np.ndarray]] = {
    "room_tone": _room_tone_shape,
    "brown_noise": _brown_noise_shape,
}


@cache
def _bed_loop(name: str, seed: int, sample_rate: int) -> np.ndarray:
    n = int(LOOP_SEC * sample_rate)
    rng = np.random.default_rng([seed, sorted(BEDS).index(name)])
    freqs = np.fft.rfftfreq(n, 1 / sample_rate)
    spectrum = BEDS[name](freqs) * np.exp(2j * np.pi * rng.random(freqs.size))
    spectrum[0] = 0
    loop = np.fft.irfft(spectrum, n)
    loop /= np.sqrt(np.mean(loop**2))
    loop *= 10 ** ((-20 - integrated_loudness(loop, sample_rate)) / 20)  # -> -20 LUFS reference
    return loop.astype(np.float32)


def bed(name: str, length: int, *, level_lufs: float, seed: int = DEFAULT_SEED,
        offset: int = 0, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """`length` samples of the bed at `level_lufs`, starting `offset` samples into the loop."""
    loop = _bed_loop(name, seed, sample_rate)
    idx = (np.arange(length) + offset) % loop.size
    return loop[idx] * np.float32(10 ** ((level_lufs + 20) / 20))


def bed_track(length: int, switches: list[tuple[int, str]], *, level_lufs: float,
              seed: int = DEFAULT_SEED, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """The full-length Noise Floor: the default bed, then each (position, name) switch,
    crossfaded with equal power over CROSSFADE_SEC starting at the switch position."""
    names = [DEFAULT_BED] + [name for _, name in switches]
    starts = [0] + [pos for pos, _ in switches]
    xfade = int(CROSSFADE_SEC * sample_rate)
    out = np.zeros(length, dtype=np.float32)
    for i, (name, start) in enumerate(zip(names, starts, strict=True)):
        end = starts[i + 1] + xfade if i + 1 < len(starts) else length
        start, end = min(start, length), min(end, length)
        if end <= start:
            continue
        # Same time offset for every bed keeps the track deterministic per position.
        segment = bed(name, end - start, level_lufs=level_lufs, seed=seed, offset=start,
                      sample_rate=sample_rate)
        gain = np.ones(end - start, dtype=np.float32)
        if i > 0:
            n_in = min(xfade, end - start)
            gain[:n_in] = np.sin(np.linspace(0, np.pi / 2, n_in, dtype=np.float32))
        if i + 1 < len(starts):
            n_out = min(xfade, end - starts[i + 1]) if end > starts[i + 1] else 0
            if n_out > 0:
                gain[-n_out:] *= np.cos(np.linspace(0, np.pi / 2, n_out, dtype=np.float32))
        out[start:end] += segment * gain
    return out


# -- sounds ------------------------------------------------------------------------------------


@cache
def _bell_soft(sample_rate: int) -> np.ndarray:
    """A soft singing-bowl-like bell: decaying inharmonic partials, 5 ms attack, 6 s long."""
    duration = 6.0
    t = np.arange(int(duration * sample_rate)) / sample_rate
    fundamental = 432.0
    partials = [(1.0, 1.0, 3.5), (2.71, 0.45, 2.2), (5.15, 0.2, 1.1), (8.4, 0.08, 0.6)]
    tone = sum(
        amp * np.exp(-t / decay) * np.sin(2 * np.pi * fundamental * ratio * t + ratio)
        for ratio, amp, decay in partials
    )
    # Slow beating between two close fundamentals makes it less synthetic.
    tone += 0.25 * np.exp(-t / 3.0) * np.sin(2 * np.pi * (fundamental + 1.3) * t)
    attack = int(0.005 * sample_rate)
    tone[:attack] *= np.linspace(0, 1, attack)
    release = int(0.5 * sample_rate)
    tone[-release:] *= np.linspace(1, 0, release) ** 2
    tone /= np.max(np.abs(tone))
    return tone.astype(np.float32)


SOUNDS: dict[str, Callable[[int], np.ndarray]] = {"bell_soft": _bell_soft}
SOUND_LEVEL_LU = -4.0  # relative to the speech level


def sound(name: str, *, level_lufs: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    raw = SOUNDS[name](sample_rate)
    gain = 10 ** ((level_lufs - integrated_loudness(raw, sample_rate)) / 20)
    return (raw * gain).astype(np.float32)
