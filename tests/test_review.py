import pytest
from typer.testing import CliRunner

import anchor.cli
from anchor.cli import app
from anchor.generate.check import check_script
from anchor.generate.request import load_request
from anchor.generate.review import ReviewFindings, render_review_prompts, review_script
from anchor.llm import FakeLLMAdapter
from anchor.script import load_script
from anchor.script.domain import DomainContext
from domain_helpers import (
    BASE_REQUEST,
    EXAMPLE_REQUESTS,
    EXAMPLE_SCRIPTS,
    make_request,
    make_script,
)

CTX = DomainContext.default()
runner = CliRunner()


def script_with_cue():
    return make_script(["Denk an dein Wort Gelassen, wenn das Meeting brenzlig wird.",
                        "Öffne die Augen."])


def test_review_finds_violation():
    s = script_with_cue()
    req = make_request(style_sheet={"cue_word": "Gelassen"}, cue_word_introduced=True)
    fake = FakeLLMAdapter().queue({"findings": [{
        "segment_index": 1, "rule": "cue_word_pairing",
        "explanation": "pairs the Cue Word with a stressful image ('brenzlig')"}]})
    result = check_script(s, req, CTX, reviewer=fake, review_model="anthropic/x")
    assert not result.ok
    [issue] = result.issues
    assert issue.location == "segments[1]"
    assert issue.rule == "review.cue_word_pairing"
    assert "brenzlig" in issue.message
    assert fake.calls[0].model == "anthropic/x"
    assert fake.calls[0].schema is ReviewFindings


def test_review_passes():
    fake = FakeLLMAdapter().queue({"findings": []})
    result = check_script(make_script(["Atme ruhig.", "Öffne die Augen."]), make_request(),
                          CTX, reviewer=fake, review_model="m")
    assert result.ok and not result.review.skipped
    assert result.review.usage["input_tokens"] > 0


def test_review_skipped_after_rule_failure():
    fake = FakeLLMAdapter()
    s = make_script(["Du wirst nie wieder nervös sein.", "Öffne die Augen."])
    result = check_script(s, make_request(), CTX, reviewer=fake, review_model="m")
    assert not result.ok
    assert result.review.skipped and "rule-based" in result.review.reason
    assert fake.calls == []


def test_review_reports_out_of_range_segment():
    s = make_script(["Atme ruhig.", "Öffne die Augen."])  # [0] is a pause
    fake = FakeLLMAdapter().queue({"findings": [
        {"segment_index": 17, "rule": "no_absolutes", "explanation": "x"},
        {"segment_index": 0, "rule": "no_medical", "explanation": "y"},
    ]})
    review = review_script(s, make_request(), fake, model="m")
    assert review.issues == []
    assert [(a["segment_index"], a["reason"]) for a in review.anomalies] == [
        (17, "no such Segment"), (0, "not spoken text")]
    assert check_script(s, make_request(), CTX,
                        reviewer=FakeLLMAdapter().queue({"findings": [
                            {"segment_index": 17, "rule": "ledger", "explanation": "x"}]}),
                        review_model="m").ok


def test_review_prompt_lists_spoken_segments_with_indices():
    request, _ = load_request(EXAMPLE_REQUESTS / "short.yaml")
    s = load_script(EXAMPLE_SCRIPTS / "short.json").script
    system, user = render_review_prompts(s, request)
    assert "1: Eine kurze Atempause für dich." in user
    assert "7: Atme jetzt in deinem eigenen Tempo weiter." in user  # silent_practice prompt
    assert "\n0: " not in user  # the bell is not spoken
    assert "[cue_word_pairing]" in system
    assert "Form of address: du" in user


@pytest.fixture
def fake_llm(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = FakeLLMAdapter()
    monkeypatch.setattr(anchor.cli, "_llm_adapter", lambda settings: fake)
    return fake


def test_cli_review(fake_llm):
    fake_llm.queue({"findings": [{"segment_index": 4, "rule": "permissive_language",
                                  "explanation": "commanding tone"}]})
    result = runner.invoke(app, ["validate", str(EXAMPLE_SCRIPTS / "day.json"), "--request",
                                 str(EXAMPLE_REQUESTS / "day.yaml"), "--review"])
    assert result.exit_code == 1
    assert "review: 1 finding(s)" in result.output
    assert "segments[4]: review.permissive_language: commanding tone" in result.output
    assert fake_llm.calls[0].model == "litellm_proxy/glm"


def test_cli_review_passes(fake_llm):
    fake_llm.queue({"findings": []})
    result = runner.invoke(app, ["validate", str(EXAMPLE_SCRIPTS / "sleep.json"), "--request",
                                 str(EXAMPLE_REQUESTS / "sleep.yaml"), "--review"])
    assert result.exit_code == 0, result.output
    assert "domain rules and review passed" in result.output


def test_cli_review_requires_request(fake_llm):
    result = runner.invoke(app, ["validate", str(EXAMPLE_SCRIPTS / "day.json"), "--review"])
    assert result.exit_code == 1 and "--request" in result.output


def test_base_request_fixture_is_valid():
    assert make_request().style_sheet.address == BASE_REQUEST["style_sheet"]["address"]
