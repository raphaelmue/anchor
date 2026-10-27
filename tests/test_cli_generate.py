import json

import litellm
import pytest
from typer.testing import CliRunner

import anchor.cli
from anchor.cli import app
from anchor.config import LLMSettings
from anchor.llm import FakeLLMAdapter
from anchor.llm.litellm_adapter import LiteLLMAdapter
from anchor.script import load_script
from domain_helpers import EXAMPLE_REQUESTS, llm_doc

runner = CliRunner()


def day_doc(**kw):
    """A valid answer for examples/requests/day.yaml (600 s target)."""
    return llm_doc(("Willkommen. Setz dich bequem hin.", "Öffne langsam die Augen."),
                   pause=(500, 300, 700), **kw)


@pytest.fixture
def fake_llm(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = FakeLLMAdapter()
    monkeypatch.setattr(anchor.cli, "_llm_adapter", lambda settings: fake)
    return fake


def invoke(*args):
    return runner.invoke(app, ["generate", str(EXAMPLE_REQUESTS / "day.yaml"), *args])


def test_successful_command(fake_llm, tmp_path):
    fake_llm.queue(day_doc(), {"findings": []})
    out = tmp_path / "out" / "day.json"
    result = invoke("-o", str(out))
    assert result.exit_code == 0, result.output
    assert load_script(out).ok
    record = tmp_path / "out" / "day.generation.json"
    assert record.is_file()
    assert "1 attempt(s)" in result.output
    assert "duration: estimated" in result.output and "target 600 s" in result.output
    assert "2000 in / 1000 out tokens in 2 call(s)" in result.output
    assert f"record: {record}" in result.output
    assert len(fake_llm.calls) == 2


def test_review_skipped(fake_llm, tmp_path):
    fake_llm.queue(day_doc())
    out = tmp_path / "day.json"
    result = invoke("-o", str(out), "--no-review")
    assert result.exit_code == 0, result.output
    assert len(fake_llm.calls) == 1
    assert "review skipped" in result.output
    record = json.loads((tmp_path / "day.generation.json").read_text(encoding="utf-8"))
    assert record["review"] == "skipped"
    assert record["attempts"][0]["review"]["skipped"] is True


def test_failing_generation(fake_llm, tmp_path):
    bad = day_doc(last_role=None)
    fake_llm.queue(bad, bad, bad)
    out = tmp_path / "day.json"
    result = invoke("-o", str(out), "--no-review")
    assert result.exit_code == 1
    assert "generation failed after 3 attempt(s)" in result.output
    assert "emergence.required" in result.output
    assert not out.exists()
    assert (tmp_path / "day.generation.json").is_file()


def test_invalid_request(fake_llm, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("session_type: day\nlanguage: en-US\n", encoding="utf-8")
    result = runner.invoke(app, ["generate", str(bad), "-o", str(tmp_path / "x.json")])
    assert result.exit_code == 1
    assert "language" in result.output and "de-DE" in result.output
    assert fake_llm.calls == []


def test_missing_api_key_fails_before_any_request(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANCHOR_LLM__MODEL", "anthropic/claude-opus-5-5")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    adapter = LiteLLMAdapter(LLMSettings())
    monkeypatch.setattr(anchor.cli, "_llm_adapter", lambda settings: adapter)
    monkeypatch.setattr(litellm, "completion", lambda **kw: pytest.fail("request sent"))
    result = invoke("-o", str(tmp_path / "day.json"))
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output
    assert not (tmp_path / "day.generation.json").exists()


def test_missing_proxy_base_url_fails_before_any_request(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANCHOR_LLM__MODEL", "litellm_proxy/glm")
    monkeypatch.delenv("LITELLM_PROXY_API_BASE", raising=False)
    monkeypatch.setattr(anchor.cli, "_llm_adapter", lambda settings: LiteLLMAdapter(settings.llm))
    monkeypatch.setattr(litellm, "completion", lambda **kw: pytest.fail("request sent"))
    result = invoke("-o", str(tmp_path / "day.json"))
    assert result.exit_code == 1
    assert "LITELLM_PROXY_API_BASE" in result.output
