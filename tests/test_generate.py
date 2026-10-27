import json

import pytest

from anchor.config import LLMSettings
from anchor.generate.loop import generate
from anchor.generate.record import record_path
from anchor.llm import FakeLLMAdapter, LLMError, LLMRefusalError
from anchor.script import load_script
from anchor.script.domain import DomainContext
from domain_helpers import llm_doc, make_request

CTX = DomainContext.default()
NO_FINDINGS = {"findings": []}


def run(fake, tmp_path, request=None, review=False, **settings):
    out = tmp_path / "out" / "script.json"
    result = generate(request or make_request(), out, adapter=fake,
                      settings=LLMSettings(**settings), ctx=CTX, review=review)
    return result, out


def read_record(out):
    return json.loads(record_path(out).read_text(encoding="utf-8"))


def test_success_on_first_attempt(tmp_path):
    fake = FakeLLMAdapter().queue(llm_doc())
    result, out = run(fake, tmp_path)
    assert result.ok and result.attempts == 1
    written = load_script(out)
    assert written.ok and written.script == result.script
    assert result.estimate.ok
    assert fake.calls[0].history == []


def test_corrected_on_second_attempt(tmp_path):
    first = llm_doc(last_role=None)
    fake = FakeLLMAdapter().queue(first, llm_doc())
    result, _ = run(fake, tmp_path)
    assert result.ok and result.attempts == 2
    history = fake.calls[1].history
    assert [m["role"] for m in history] == ["assistant", "user"]
    assert json.loads(history[0]["content"]) == first
    assert "emergence.required" in history[1]["content"]
    assert "segments[2]" in history[1]["content"]
    # The conversation keeps the original prompts.
    assert fake.calls[1].system == fake.calls[0].system
    assert fake.calls[1].user == fake.calls[0].user


def test_invalid_output_counts_as_attempt(tmp_path):
    fake = FakeLLMAdapter().queue('{"segments": [{"type": "speech"}]}', llm_doc())
    result, _ = run(fake, tmp_path)
    assert result.ok and result.attempts == 2
    assert "output.invalid" in fake.calls[1].history[1]["content"]


def test_all_attempts_invalid(tmp_path):
    out = tmp_path / "out" / "script.json"
    out.parent.mkdir()
    out.write_text("previous", encoding="utf-8")
    short = llm_doc(pause=(5, 2, 10))  # cannot reach 120 s ±10 %
    fake = FakeLLMAdapter().queue(short, short, short)
    result, _ = run(fake, tmp_path, max_attempts=3)
    assert result.outcome == "failed" and result.attempts == 3
    assert {e.rule for e in result.errors} == {"duration.range"}
    assert out.read_text(encoding="utf-8") == "previous"
    assert len(fake.calls) == 3


def test_refusal_stops_without_further_attempts(tmp_path):
    fake = FakeLLMAdapter().queue(LLMRefusalError("model declined"), llm_doc())
    result, out = run(fake, tmp_path)
    assert result.outcome == "refused" and len(fake.calls) == 1
    assert not out.exists()
    assert read_record(out)["outcome"] == "refused"


def test_transport_failure_stops(tmp_path):
    fake = FakeLLMAdapter().queue(LLMError("anthropic: HTTP 500 after 4 attempts"))
    result, out = run(fake, tmp_path)
    assert result.outcome == "error" and not out.exists()
    assert "HTTP 500" in result.errors[0].message


def test_second_generation(tmp_path):
    fake = FakeLLMAdapter().queue(llm_doc(), llm_doc())
    first, out = run(fake, tmp_path)
    first_record = read_record(out)
    second, _ = run(fake, tmp_path)
    assert first.ok and second.ok
    assert len(fake.calls) == 2
    assert read_record(out)["started_at"] >= first_record["started_at"]


def test_review_in_loop(tmp_path):
    finding = {"findings": [{"segment_index": 1, "rule": "permissive_language",
                             "explanation": "too commanding"}]}
    fake = FakeLLMAdapter().queue(llm_doc(), finding, llm_doc(), NO_FINDINGS)
    result, out = run(fake, tmp_path, review=True, review_model="openai/reviewer")
    assert result.ok and result.attempts == 2
    assert [c.model for c in fake.calls] == ["litellm_proxy/glm", "openai/reviewer"] * 2
    assert "review.permissive_language" in fake.calls[2].history[1]["content"]
    record = read_record(out)
    assert record["attempts"][0]["review"]["findings"][0]["rule"] == "review.permissive_language"
    assert [u["call"] for u in record["attempts"][1]["usage"]] == ["generation", "review"]


def test_review_skipped_on_rule_failure_in_loop(tmp_path):
    fake = FakeLLMAdapter().queue(llm_doc(last_role=None), llm_doc(), NO_FINDINGS)
    result, out = run(fake, tmp_path, review=True)
    assert result.ok and len(fake.calls) == 3
    assert read_record(out)["attempts"][0]["review"] == {
        "skipped": True, "reason": "rule-based checks failed"}


# -- generation record (task 4.6) ---------------------------------------------------------------


def test_record_after_success(tmp_path):
    fake = FakeLLMAdapter(input_tokens=1200, output_tokens=800).queue(
        llm_doc(last_role=None), llm_doc())
    _, out = run(fake, tmp_path)
    record = read_record(out)
    assert record["outcome"] == "success"
    assert len(record["attempts"]) == 2
    assert record["attempts"][0]["errors"][0]["rule"] == "emergence.required"
    assert record["attempts"][1]["errors"] == []
    assert record["usage"] == {"calls": 2, "input_tokens": 2400, "output_tokens": 1600}
    assert record["models"] == {"generation": "litellm_proxy/glm", "review": None}
    assert record["prompt_versions"] == {"script": "script.v1", "review": None}
    assert record["review"] == "skipped"
    assert record["lexicon_version"] == "de-DE.1"
    assert record["chars_per_sec"] == 21.0
    assert len(record["request_sha256"]) == 64
    assert json.loads(record["attempts"][1]["raw_output"]) == llm_doc()
    assert record["attempts"][1]["estimate"]["ok"] is True


def test_record_after_failure(tmp_path):
    short = llm_doc(pause=(5, 2, 10))
    fake = FakeLLMAdapter().queue(short, short)
    _, out = run(fake, tmp_path, max_attempts=2)
    record = read_record(out)
    assert record["outcome"] == "failed"
    assert len(record["attempts"]) == 2
    assert record["errors"][0]["rule"] == "duration.range"
    assert not out.exists()


def test_request_hash_is_stable(tmp_path):
    fake = FakeLLMAdapter().queue(llm_doc(), llm_doc())
    _, out = run(fake, tmp_path)
    first = read_record(out)["request_sha256"]
    run(fake, tmp_path)
    assert read_record(out)["request_sha256"] == first
    fake.queue(llm_doc())
    other = tmp_path / "other"
    run(fake, other, request=make_request(notes="anders"))
    assert read_record(other / "out" / "script.json")["request_sha256"] != first


@pytest.mark.parametrize("outcome_queue", [
    lambda: [llm_doc()],
    lambda: [LLMError("boom")],
])
def test_record_contains_no_api_key(tmp_path, monkeypatch, outcome_queue):
    secret = "sk-ant-api03-THIS-IS-A-SECRET-KEY-0123456789"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    fake = FakeLLMAdapter().queue(*outcome_queue())
    _, out = run(fake, tmp_path)
    text = record_path(out).read_text(encoding="utf-8")
    assert secret not in text
    assert "SECRET" not in text
