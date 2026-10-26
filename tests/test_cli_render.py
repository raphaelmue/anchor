import json

import pytest
from typer.testing import CliRunner

import anchor.cli
from anchor.cli import app
from anchor.tts.fake import FakeTTSAdapter

runner = CliRunner()

SCRIPT = {
    "schema_version": "1.2",
    "session_type": "short",
    "language": "de-DE",
    "target_duration_sec": 40,
    "segments": [
        {"type": "speech", "text": "Atme ruhig ein. Und wieder aus."},
        {"type": "pause", "seconds": 20, "elastic": [10, 60]},
        {"type": "speech", "text": "Gut gemacht."},
    ],
}


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANCHOR_CACHE__DIR", str(tmp_path / "cache"))
    adapter = FakeTTSAdapter()
    monkeypatch.setattr(anchor.cli, "build_adapter", lambda settings: adapter)
    return adapter


def test_render_success(fake, write_json, tmp_path):
    out = tmp_path / "out" / "session.mp3"
    result = runner.invoke(app, ["render", str(write_json(SCRIPT)), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.is_file() and out.stat().st_size > 0
    report = json.loads((tmp_path / "out" / "session.report.json").read_text())
    assert report["cache_misses"] == 3
    assert "LUFS" in result.output and "report:" in result.output


def test_render_invalid_script(fake, write_json, tmp_path):
    out = tmp_path / "session.mp3"
    doc = {**SCRIPT, "session_type": "nap", "segments": [{"type": "pause"}]}
    result = runner.invoke(app, ["render", str(write_json(doc)), "-o", str(out)])
    assert result.exit_code != 0
    assert "session_type" in result.output and "segments[0].seconds" in result.output
    assert fake.calls == [] and fake.health_calls == 0
    assert not out.exists()


def test_render_backend_failure(fake, write_json, tmp_path):
    fake.fail_on_call = 2
    out = tmp_path / "session.mp3"
    result = runner.invoke(app, ["render", str(write_json(SCRIPT)), "-o", str(out)])
    assert result.exit_code != 0
    assert "render failed" in result.output and "simulated failure" in result.output
    assert not out.exists()


def test_render_backend_down(fake, write_json, tmp_path):
    fake.healthy = False
    result = runner.invoke(app, ["render", str(write_json(SCRIPT)), "-o",
                                 str(tmp_path / "s.mp3")])
    assert result.exit_code != 0 and "not ready" in result.output


def test_render_format_option_and_no_cache(fake, write_json, tmp_path):
    path = write_json(SCRIPT)
    runner.invoke(app, ["render", str(path), "-o", str(tmp_path / "a.mp3")])
    result = runner.invoke(app, ["render", str(path), "-o", str(tmp_path / "b.bin"),
                                 "--format", "opus", "--no-cache"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "b.bin").read_bytes()[:4] == b"OggS"
    assert json.loads((tmp_path / "b.report.json").read_text())["cache_misses"] == 3


def test_render_rejects_unknown_format(fake, write_json, tmp_path):
    result = runner.invoke(app, ["render", str(write_json(SCRIPT)), "-o",
                                 str(tmp_path / "a.mp3"), "--format", "flac"])
    assert result.exit_code != 0 and "unsupported format" in result.output
