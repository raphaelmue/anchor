import pytest
import yaml
from typer.testing import CliRunner

import anchor.cli
from anchor.cli import app
from anchor.llm import FakeLLMAdapter
from domain_helpers import BASE_REQUEST, EXAMPLE_REQUESTS, EXAMPLE_SCRIPTS

runner = CliRunner()

VALID = {
    "schema_version": "1.2",
    "session_type": "day",
    "language": "de-DE",
    "target_duration_sec": 300,
    "segments": [{"type": "speech", "text": "Mach es dir bequem."}],
}


def test_validate_valid_file(write_json):
    result = runner.invoke(app, ["validate", str(write_json(VALID))])
    assert result.exit_code == 0, result.output
    assert "valid" in result.output


def test_validate_invalid_file_prints_all_errors(write_json):
    doc = {**VALID, "session_type": "nap", "segments": [{"type": "pause"}]}
    result = runner.invoke(app, ["validate", str(write_json(doc))])
    assert result.exit_code != 0
    assert "2 validation error(s)" in result.output
    assert "session_type" in result.output
    assert "segments[0].seconds" in result.output


def test_validate_missing_file(tmp_path):
    result = runner.invoke(app, ["validate", str(tmp_path / "nope.json")])
    assert result.exit_code != 0
    assert "cannot read" in result.output


# -- domain validation (--request) ---------------------------------------------------------------

@pytest.fixture
def fake_llm(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no ./anchor.toml
    fake = FakeLLMAdapter()
    built = []
    monkeypatch.setattr(anchor.cli, "_llm_adapter", lambda settings: built.append(1) or fake)
    fake.built = built
    return fake


def write_request(tmp_path, doc=None):
    path = tmp_path / "request.yaml"
    path.write_text(yaml.safe_dump(doc or BASE_REQUEST, allow_unicode=True), encoding="utf-8")
    return path


@pytest.mark.parametrize("name", ["day", "sleep", "short"])
def test_hand_written_script_checked(name, fake_llm):
    result = runner.invoke(app, ["validate", str(EXAMPLE_SCRIPTS / f"{name}.json"),
                                 "--request", str(EXAMPLE_REQUESTS / f"{name}.yaml")])
    assert result.exit_code == 0, result.output
    assert "duration: estimated" in result.output
    assert "domain rules passed" in result.output
    assert fake_llm.calls == [] and fake_llm.built == []


def test_invalid_script_lists_every_rule_violation(write_json, tmp_path, fake_llm):
    doc = {**VALID, "target_duration_sec": 120, "segments": [
        {"type": "pause", "seconds": 60, "elastic": [30, 120]},
        {"type": "speech", "text": "Atmen Sie ruhig ein.", "strategy": "reframe"},
        {"type": "speech", "text": "Du wirst nie wieder nervös sein."},
    ]}
    result = runner.invoke(app, ["validate", str(write_json(doc)),
                                 "--request", str(write_request(tmp_path))])
    assert result.exit_code == 1
    out = result.output
    assert "validation error(s)" in out
    for line in ("segments[1]: address.du: ", "segments[1]: elements.strategy: ",
                 "segments[2]: emergence.required: ", "segments[2]: suggestion.absolute: "):
        assert line in out, out
    assert "duration: estimated" in out


def test_unchanged_structural_mode(write_json, fake_llm):
    doc = {**VALID, "segments": [{"type": "speech", "text": "Atmen Sie ruhig ein."}]}
    result = runner.invoke(app, ["validate", str(write_json(doc))])
    assert result.exit_code == 0, result.output
    assert "duration" not in result.output
    assert fake_llm.calls == [] and fake_llm.built == []


def test_invalid_request_is_reported(write_json, tmp_path, fake_llm):
    bad = {**BASE_REQUEST, "method": "progressive_muscle_relaxation"}
    result = runner.invoke(app, ["validate", str(write_json(VALID)),
                                 "--request", str(write_request(tmp_path, bad))])
    assert result.exit_code == 1
    assert "request error(s)" in result.output and "method" in result.output
