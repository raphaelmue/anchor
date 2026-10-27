import pytest
import yaml

from anchor.generate.request import MethodId, load_request, parse_request
from domain_helpers import BASE_REQUEST, EXAMPLE_REQUESTS

MINIMAL = {k: v for k, v in BASE_REQUEST.items() if k != "strategies"}


def errors(doc):
    request, issues = parse_request(doc)
    assert request is None
    return {i.location: i.message for i in issues}


def test_minimal_valid_request():
    request, issues = parse_request(MINIMAL)
    assert issues == []
    assert request.session_context == "stage"
    assert request.strategies == []
    assert request.cue_word_introduced is False
    assert request.suggestion_ledger == []
    assert request.style_sheet.imagery == []
    assert request.goal.domain == "stress"


def test_unknown_method():
    found = errors({**MINIMAL, "method": "progressive_muscle_relaxation"})
    message = found["method"]
    assert "progressive_muscle_relaxation" in message
    for method in ("pmr", "autogenic_training", "self_hypnosis", "mindfulness_body_scan",
                   "paced_breathing", "mental_rehearsal", "implementation_intention"):
        assert method in message
    assert len(MethodId) == 7


def test_several_errors():
    doc = {k: v for k, v in MINIMAL.items() if k != "style_sheet"}
    found = errors({**doc, "session_type": "nap"})
    assert set(found) == {"session_type", "style_sheet"}


def test_unsupported_language():
    found = errors({**MINIMAL, "language": "en-US"})
    assert "de-DE" in found["language"]


def test_unknown_fields_rejected_with_paths():
    found = errors({**MINIMAL, "practitioner_name": "Anna",
                    "style_sheet": {**MINIMAL["style_sheet"], "font": "x"},
                    "goal": {**MINIMAL["goal"], "pattern": "Calm In Situation"}})
    assert {"practitioner_name", "style_sheet.font", "goal.pattern"} <= set(found)


@pytest.mark.parametrize("field,value", [
    ("guidance_level", "mostly"), ("target_duration_sec", 0), ("strategies", ["hypnotize"]),
    ("session_context", "program"),
])
def test_invalid_values(field, value):
    assert field in " ".join(errors({**MINIMAL, field: value}))


def test_address_must_be_du_or_sie():
    found = errors({**MINIMAL, "style_sheet": {"address": "ihr", "tone": "warm"}})
    assert "style_sheet.address" in found


def test_not_a_mapping():
    _, issues = parse_request(["a"])
    assert issues[0].location == "$"


@pytest.mark.parametrize("name", ["day", "sleep", "short"])
def test_example_requests_load(name):
    request, issues = load_request(EXAMPLE_REQUESTS / f"{name}.yaml")
    assert issues == [] and request.session_type == name


def test_load_invalid_yaml(tmp_path):
    path = tmp_path / "r.yaml"
    path.write_text("a: [unclosed", encoding="utf-8")
    _, issues = load_request(path)
    assert "invalid YAML" in issues[0].message


def test_full_request_round_trip(tmp_path):
    doc = {**BASE_REQUEST, "stage_ref": "stage-2", "cue_word_introduced": True,
           "suggestion_ledger": ["Ruhe im Bauch", "Schritt für Schritt"], "notes": "x",
           "style_sheet": {"address": "Sie", "tone": "ruhig", "imagery": ["Strand am Morgen"],
                           "cue_word": "Ruhe", "cue_word_phrasing": "Ruhe – und los.",
                           "situation_vocabulary": ["Büro"]}}
    path = tmp_path / "r.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    request, issues = load_request(path)
    assert issues == []
    assert request.style_sheet.address == "Sie"
    assert request.suggestion_ledger == ["Ruhe im Bauch", "Schritt für Schritt"]
