import numpy as np
import pytest

from anchor.audio import SAMPLE_RATE
from anchor.audio.beds import BEDS, CROSSFADE_SEC, bed, bed_track, sound
from anchor.audio.loudness import integrated_loudness

SR = SAMPLE_RATE


def longest_zero_run(x: np.ndarray) -> int:
    zero = np.concatenate([[False], x == 0, [False]])
    edges = np.flatnonzero(np.diff(zero.astype(int)))
    return int(np.max(edges[1::2] - edges[::2])) if edges.size else 0


@pytest.mark.parametrize("name", sorted(BEDS))
def test_bed_level(name):
    audio = bed(name, 20 * SR, level_lufs=-60)
    assert integrated_loudness(audio) == pytest.approx(-60, abs=1.0)


@pytest.mark.parametrize("name", sorted(BEDS))
def test_bed_has_no_zero_runs(name):
    # Longer than one loop, so the loop seam is covered too.
    audio = bed(name, 75 * SR, level_lufs=-60)
    assert longest_zero_run(audio) <= int(0.010 * SR)


def test_bed_deterministic():
    np.testing.assert_array_equal(bed("room_tone", SR, level_lufs=-60, seed=7),
                                  bed("room_tone", SR, level_lufs=-60, seed=7))
    assert not np.array_equal(bed("room_tone", SR, level_lufs=-60, seed=7),
                              bed("room_tone", SR, level_lufs=-60, seed=8))


def test_beds_differ():
    room, brown = bed("room_tone", SR, level_lufs=-60), bed("brown_noise", SR, level_lufs=-60)
    assert not np.allclose(room, brown)


def test_bed_track_switch_crossfades():
    switch = 10 * SR
    track = bed_track(20 * SR, [(switch, "brown_noise")], level_lufs=-60)
    xfade = int(CROSSFADE_SEC * SR)
    room = bed("room_tone", 20 * SR, level_lufs=-60)
    brown = bed("brown_noise", 20 * SR, level_lufs=-60)
    np.testing.assert_allclose(track[: switch - 1], room[: switch - 1], atol=1e-7)
    np.testing.assert_allclose(track[switch + xfade + 1 :], brown[switch + xfade + 1 :],
                               atol=1e-7)
    middle = track[switch : switch + xfade]
    assert not np.allclose(middle, room[switch : switch + xfade])
    assert longest_zero_run(track) <= int(0.010 * SR)
    # Equal-power crossfade keeps the level steady.
    assert integrated_loudness(middle) == pytest.approx(-60, abs=1.5)


def test_bell_soft():
    bell = sound("bell_soft", level_lufs=-22)
    assert integrated_loudness(bell) == pytest.approx(-22, abs=0.5)
    assert abs(bell[0]) < 1e-3 and abs(bell[-1]) < 1e-6  # no click at start or end
    np.testing.assert_array_equal(bell, sound("bell_soft", level_lufs=-22))
