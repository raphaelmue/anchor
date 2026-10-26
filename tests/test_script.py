import copy

import pytest

from anchor.script import SpeechRole, validate_script

MINIMAL = {
    "schema_version": "1.2",
    "session_type": "day",
    "language": "de-DE",
    "target_duration_sec": 300,
    "segments": [{"type": "speech", "text": "Mach es dir bequem."}],
}


def make(**overrides):
    doc = copy.deepcopy(MINIMAL)
    doc.update(overrides)
    return doc


def errors_of(doc):
    result = validate_script(doc)
    assert not result.ok
    return result.errors


def test_minimal_valid_script():
    result = validate_script(MINIMAL)
    assert result.ok, result.errors


def test_missing_required_field_is_named():
    doc = make()
    del doc["target_duration_sec"]
    assert any(e.location == "target_duration_sec" for e in errors_of(doc))


def test_empty_segment_list_fails():
    assert any(e.location == "segments" for e in errors_of(make(segments=[])))


def test_unsupported_version_names_supported_one():
    (err,) = errors_of(make(schema_version="1.1"))
    assert "'1.2'" in err.message


def test_unknown_session_type_lists_allowed():
    (err,) = errors_of(make(session_type="nap"))
    for allowed in ("day", "sleep", "short", "cue_recall", "rehearsal", "pre_event", "taster"):
        assert allowed in err.message


def test_pause_without_seconds_identifies_index():
    segments = [*MINIMAL["segments"], {"type": "pause"}]
    (err,) = errors_of(make(segments=segments))
    assert err.location.startswith("segments[1]")


def test_unknown_segment_type_fails():
    (err,) = errors_of(make(segments=[{"type": "music"}]))
    assert err.location == "segments[0]"


@pytest.mark.parametrize(
    "segment",
    [
        {"type": "pause", "seconds": 5},
        {"type": "silent_practice", "seconds": 60},
        {"type": "silent_practice", "seconds": 60, "prompt": "Übe jetzt selbst."},
        {"type": "sound", "sound": "bell_soft"},
        {"type": "ambience", "ambience": "brown_noise"},
        {"type": "marker", "name": "deepening_start"},
    ],
)
def test_each_segment_type_with_required_fields(segment):
    assert validate_script(make(segments=[segment])).ok


@pytest.mark.parametrize("segment", [{"type": "sound"}, {"type": "ambience"}, {"type": "marker"}])
def test_segment_type_missing_required_field(segment):
    assert errors_of(make(segments=[segment]))


def test_speech_text_too_long_identifies_index():
    (err,) = errors_of(make(segments=[{"type": "speech", "text": "a" * 301}]))
    assert err.location.startswith("segments[0]")
    assert validate_script(make(segments=[{"type": "speech", "text": "a" * 300}])).ok


def test_speech_text_blank_fails():
    assert errors_of(make(segments=[{"type": "speech", "text": "   "}]))


def test_speech_with_role_style_strategy():
    seg = {"type": "speech", "text": "Komm zurück.", "role": "emergence", "style": "calm",
           "strategy": "mental_rehearsal"}
    result = validate_script(make(segments=[seg]))
    assert result.ok
    assert result.script.segments[0].role is SpeechRole.EMERGENCE


def test_metadata_preserved():
    meta = {"session_context": "stage", "goal_pattern": "calm_in_situation",
            "goal_domain": "performance_anxiety", "method": "self_hypnosis",
            "guidance_level": "semi_guided", "stage_ref": "pa-02",
            "content_snapshot": "cs-2026-10-25-01"}
    script = validate_script(make(**meta)).script
    dumped = script.model_dump(exclude_none=True)
    for key, value in meta.items():
        assert dumped[key] == value


def test_formula_reference_rejected():
    (err,) = errors_of(make(segments=[{"type": "speech", "formula": "at.rest.01"}]))
    assert "not yet supported" in err.message
    assert "Formula" in err.message


def test_valid_elastic_range():
    assert validate_script(make(segments=[{"type": "pause", "seconds": 15,
                                           "elastic": [10, 25]}])).ok


@pytest.mark.parametrize("elastic", [[10, 25], [-1, 40], [31, 40]])
def test_seconds_outside_elastic_range(elastic):
    # seconds 30 is outside [10, 25]; a negative min and min > seconds are also invalid
    assert errors_of(make(segments=[{"type": "pause", "seconds": 30, "elastic": elastic}]))


def test_elastic_on_silent_practice():
    seg = {"type": "silent_practice", "seconds": 60, "elastic": [45, 90]}
    assert validate_script(make(segments=[seg])).ok


def test_multiple_errors_reported_together():
    errs = errors_of(make(session_type="nap", segments=[{"type": "pause"}]))
    locations = {e.location for e in errs}
    assert "session_type" in locations
    assert any(loc.startswith("segments[0]") for loc in locations)


def test_invalid_json_text():
    (err,) = validate_script("{not json").errors
    assert "invalid JSON" in err.message
