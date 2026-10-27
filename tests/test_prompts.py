from anchor.generate.prompts import render_feedback, render_script_prompts
from anchor.generate.request import GuidanceLevel, load_request
from anchor.script.domain import DomainContext, DomainIssue
from anchor.script.models import SessionType
from domain_helpers import EXAMPLE_REQUESTS, make_request

CTX = DomainContext.default()


def full(prompts):
    return prompts.system + "\n" + prompts.user


def test_style_sheet_reaches_the_prompt():
    request = make_request(style_sheet={"address": "Sie", "imagery": ["Strand am Morgen"]})
    text = full(render_script_prompts(request, CTX))
    assert "Form of address: Sie" in text
    assert "Strand am Morgen" in text


def test_cue_word_without_introduction():
    request = make_request(style_sheet={"cue_word": "Gelassen",
                                        "cue_word_phrasing": "Mit Gelassen kommt Ruhe."})
    text = full(render_script_prompts(request, CTX))
    assert "gelassen" not in text.lower()
    assert "not introduced" in text


def test_cue_word_after_introduction():
    request = make_request(style_sheet={"cue_word": "Gelassen"}, cue_word_introduced=True)
    assert "Cue Word: Gelassen" in full(render_script_prompts(request, CTX))


def test_ledger_in_prompt():
    request = make_request(suggestion_ledger=["Ruhe im Bauch beim Meeting",
                                              "Schritt für Schritt durch den Tag"])
    text = full(render_script_prompts(request, CTX))
    assert "Ruhe im Bauch beim Meeting" in text
    assert "Schritt für Schritt durch den Tag" in text
    assert "never contradict" in text


def test_speech_budget_is_present():
    request = make_request(target_duration_sec=600)
    prompts = render_script_prompts(request, CTX)
    assert "The target duration is 600 seconds" in prompts.system
    assert "spoken characters in total" in prompts.system
    assert "characters per minute" in prompts.system


def test_goal_method_and_rules_in_prompt():
    request, _ = load_request(EXAMPLE_REQUESTS / "sleep.yaml")
    prompts = render_script_prompts(request, CTX)
    assert "NO Emergence" in prompts.system
    assert "`sleep_permission`" in prompts.system
    assert "Method: mindfulness_body_scan" in prompts.user
    assert "sleep_onset" in prompts.user
    assert "No guarantees or absolutes" in prompts.system
    assert "German (de-DE)" in prompts.system
    assert prompts.version == "script.v1"


def test_every_session_type_and_level_renders():
    for session_type in SessionType:
        for level in GuidanceLevel:
            request = make_request(session_type=session_type.value, guidance_level=level.value)
            prompts = render_script_prompts(request, CTX)
            assert "{" not in prompts.user


def test_feedback_lists_every_error():
    text = render_feedback([DomainIssue("segments[3]", "emergence.required", "missing"),
                            DomainIssue("$", "duration.range", "too short")])
    assert "2 error(s)" in text
    assert "segments[3]: emergence.required: missing" in text
    assert "$: duration.range: too short" in text
