import pytest

from anchor.audio.pacing import PacingError, load_pacing
from anchor.script import SessionType


def test_every_session_type_has_a_profile():
    assert set(load_pacing()) == set(SessionType)


def test_sleep_slower_and_longer_than_pre_event():
    p = load_pacing()
    sleep, pre = p[SessionType.SLEEP], p[SessionType.PRE_EVENT]
    assert sleep.speed < pre.speed
    assert sleep.sentence_gap_sec > pre.sentence_gap_sec
    assert sleep.segment_gap_sec > pre.segment_gap_sec
    assert sleep.fade_out_sec == 30.0


def test_short_tighter_than_day():
    p = load_pacing()
    assert p[SessionType.SHORT].sentence_gap_sec < p[SessionType.DAY].sentence_gap_sec


def test_override_replaces_values(tmp_path):
    override = tmp_path / "pacing.yaml"
    override.write_text("sleep:\n  sentence_gap_sec: 2.2\n  fade_out_sec: 45\n")
    p = load_pacing(override)
    assert p[SessionType.SLEEP].sentence_gap_sec == 2.2
    assert p[SessionType.SLEEP].fade_out_sec == 45
    assert p[SessionType.SLEEP].speed == 0.85  # untouched keys keep their defaults
    assert p[SessionType.DAY] == load_pacing()[SessionType.DAY]


@pytest.mark.parametrize("content", ["nap:\n  speed: 1\n", "sleep:\n  sped: 1\n",
                                     "sleep:\n  speed: -1\n", "- a\n"])
def test_invalid_override(tmp_path, content):
    override = tmp_path / "pacing.yaml"
    override.write_text(content)
    with pytest.raises(PacingError):
        load_pacing(override)
