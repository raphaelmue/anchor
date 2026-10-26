from typer.testing import CliRunner

from anchor.cli import app

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
