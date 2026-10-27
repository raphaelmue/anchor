import pytest

from anchor.script.domain import DomainContext, validate_domain
from domain_helpers import make_request, make_script, segments_doc

CTX = DomainContext.default()


def rules(script, request):
    return [(i.location, i.rule) for i in validate_domain(script, request, CTX).issues]


def test_valid_script_has_no_issues():
    s = make_script(["Atme ruhig ein.", "Öffne langsam die Augen."])
    assert rules(s, make_request()) == []


def test_several_violations():
    s = make_script(["Atmen Sie ruhig ein.", "Bleib noch einen Moment liegen."], last_role=None)
    issues = validate_domain(s, make_request(), CTX).issues
    found = {(i.location, i.rule) for i in issues}
    assert ("segments[2]", "emergence.required") in found
    assert ("segments[1]", "address.du") in found
    assert all(str(i).startswith(f"{i.location}: {i.rule}: ") for i in issues)


def test_session_type_mismatch():
    s = make_script(["Schlaf gut."], session_type="day")
    issues = validate_domain(s, make_request(session_type="sleep"), CTX).issues
    mismatch = [i for i in issues if i.rule == "match.session_type"]
    assert len(mismatch) == 1
    assert "day" in mismatch[0].message and "sleep" in mismatch[0].message


def test_method_and_duration_mismatch():
    s = make_script(["Atme ruhig."], method="paced_breathing", target=300)
    found = rules(s, make_request())
    assert ("method", "match.method") in found
    assert ("target_duration_sec", "match.target_duration_sec") in found


def test_method_unset_in_script_is_fine():
    s = make_script(["Atme ruhig."])
    assert not [r for _, r in rules(s, make_request()) if r.startswith("match.")]


def test_day_without_emergence():
    s = make_script(["Atme ruhig."], last_role=None)
    assert ("segments[1]", "emergence.required") in rules(s, make_request())


def test_day_emergence_must_be_last_speech():
    s = make_script(["Öffne die Augen.", "Und noch etwas."], last_role=None)
    s2 = segments_doc([*[seg.model_dump(exclude_none=True) for seg in s.segments[:2]],
                       {"type": "speech", "role": "emergence", "text": "Wach."},
                       {"type": "speech", "text": "Noch ein Satz."}])
    assert ("segments[3]", "emergence.required") in rules(s2, make_request())


def test_sleep_with_emergence():
    s = make_script(["Schlaf ein.", "Wach auf."], session_type="sleep", last_role="emergence")
    found = rules(s, make_request(session_type="sleep"))
    assert found == [("segments[2]", "emergence.forbidden")]


@pytest.mark.parametrize("session_type", ["short", "cue_recall", "taster"])
def test_no_emergence_constraint(session_type):
    s = make_script(["Atme ruhig."], session_type=session_type, last_role=None)
    assert rules(s, make_request(session_type=session_type)) == []


@pytest.mark.parametrize("session_type", ["rehearsal", "pre_event"])
def test_emergence_required_types(session_type):
    s = make_script(["Atme ruhig."], session_type=session_type, last_role=None)
    assert ("segments[1]", "emergence.required") in rules(s, make_request(
        session_type=session_type))


def test_strategy_not_introduced():
    s = segments_doc([
        {"type": "pause", "seconds": 60, "elastic": [30, 120]},
        {"type": "speech", "text": "Die Aufregung ist Energie.", "strategy": "reframe"},
        {"type": "speech", "role": "emergence", "text": "Öffne die Augen."},
    ])
    found = rules(s, make_request(strategies=["calm_competence"]))
    assert found == [("segments[1]", "elements.strategy")]


def test_cue_word_before_introduction():
    req = make_request(style_sheet={"cue_word": "Gelassen"}, cue_word_introduced=False)
    s = make_script(["Denk an das Wort gelassen.", "Öffne die Augen."])
    assert rules(s, req) == [("segments[1]", "elements.cue_word")]


def test_cue_word_after_introduction():
    req = make_request(style_sheet={"cue_word": "Gelassen"}, cue_word_introduced=True)
    s = make_script(["Denk an das Wort gelassen.", "Öffne die Augen."])
    assert rules(s, req) == []


def test_cue_word_in_silent_practice_prompt():
    req = make_request(style_sheet={"cue_word": "Ruhe Anker"})
    s = segments_doc([
        {"type": "silent_practice", "seconds": 60, "elastic": [30, 120],
         "prompt": "Denk still an deinen Ruhe  Anker."},
        {"type": "speech", "role": "emergence", "text": "Öffne die Augen."},
    ])
    assert rules(s, req) == [("segments[0]", "elements.cue_word")]


def test_duration_unreachable():
    s = make_script(["Atme ruhig."], pause=(10, 5, 20), target=120)
    issues = [i for i in validate_domain(s, make_request(), CTX).issues
              if i.rule == "duration.range"]
    assert len(issues) == 1 and issues[0].location == "$"
    assert "108–132" in issues[0].message


def test_estimate_is_reported():
    s = make_script(["Atme ruhig."])
    assert validate_domain(s, make_request(), CTX).estimate.ok
