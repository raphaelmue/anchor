from pathlib import Path

import pytest

from anchor.audio.pacing import load_pacing
from anchor.script import load_script, validate_script
from anchor.script.duration import estimate, speech_budget

PACING = load_pacing()
EXAMPLES = Path(__file__).parent.parent / "examples" / "scripts"


def script(segments, session_type="day", target=600):
    result = validate_script({"schema_version": "1.2", "session_type": session_type,
                              "language": "de-DE", "target_duration_sec": target,
                              "segments": segments})
    assert result.ok, result.errors
    return result.script


def test_components_follow_the_layout():
    p = PACING["day"]
    s = script([
        {"type": "sound", "sound": "bell_soft"},
        {"type": "speech", "text": "Eins zwei. Drei vier."},  # 10 + 10 chars
        {"type": "pause", "seconds": 10, "elastic": [5, 20]},
        {"type": "speech", "text": "Fünf sechs."},
    ])
    est = estimate(s, p, chars_per_sec=10)
    speech = 31 / (10 * p.speed)
    gaps = p.segment_gap_sec + p.sentence_gap_sec  # bell→speech, sentence gap; pause replaces gap
    assert est.speech_chars == 31
    assert est.speech_sec == pytest.approx(speech)
    assert est.gap_sec == pytest.approx(gaps)
    expected = 0.5 + 6.0 + speech + gaps + 10 + p.fade_out_sec
    assert est.nominal_sec == pytest.approx(expected)
    assert (est.min_sec, est.max_sec) == pytest.approx((expected - 5, expected + 10))


def _padded(target, lo, hi):
    """A Script whose reachable range is [lo, hi] seconds (one long elastic pause)."""
    p = PACING["day"]
    base = estimate(script([{"type": "pause", "seconds": 0, "elastic": [0, 0]}],
                           target=target), p, 21.0).fixed_sec
    return script([{"type": "pause", "seconds": lo - base, "elastic": [lo - base, hi - base]}],
                  target=target)


def test_target_reachable():
    est = estimate(_padded(600, 520, 700), PACING["day"], 21.0)
    assert (round(est.min_sec), round(est.max_sec)) == (520, 700)
    assert est.ok
    assert "520–700" in est.describe()


def test_too_short():
    est = estimate(_padded(600, 200, 380), PACING["day"], 21.0)
    assert not est.ok
    assert est.allowed == pytest.approx((540, 660))
    assert "200–380" in est.describe() and "540–660" in est.describe()


# M1 benchmark renders (docs/render-pipeline.md §9): trimmed speech in seconds. Gaps, pauses,
# sounds, lead-in and tail are deterministic, so the measured unfitted duration is the estimate
# with its speech time replaced by the measured speech time.
M1_SPEECH_SEC = {"day": 93.0, "sleep": 63.3, "short": 36.4}


@pytest.mark.parametrize("name", sorted(M1_SPEECH_SEC))
def test_estimate_matches_m1_unfitted_duration(name):
    s = load_script(EXAMPLES / f"{name}.json").script
    est = estimate(s, PACING[s.session_type], 21.0)
    measured = est.nominal_sec - est.speech_sec + M1_SPEECH_SEC[name]
    assert est.nominal_sec == pytest.approx(measured, rel=0.10)


def test_speech_budget():
    p = PACING["day"]
    budget = speech_budget(600, p, 21.0, (0.15, 0.30))
    lo, hi = budget.chars
    assert 0 < lo < hi
    # A Script with exactly these characters and pauses lands near the target.
    sec_per_char = 1 / (21.0 * p.speed) + p.sentence_gap_sec / 40
    assert lo * sec_per_char == pytest.approx(90, abs=1)
    assert budget.pause_sec[0] < budget.pause_sec[1] < 600
