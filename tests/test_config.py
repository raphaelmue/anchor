import pytest

from anchor.config import ConfigError, load_settings

TOML = """
[tts]
base_url = "http://file-host:8000"
model = "file-model"

[cache]
dir = "{cache}"
"""


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("ANCHOR_"):
            monkeypatch.delenv(key)


def write(tmp_path, cache_dir="/tmp/x"):
    path = tmp_path / "anchor.toml"
    path.write_text(TOML.format(cache=cache_dir))
    return path


def test_file_values_are_used(tmp_path):
    settings = load_settings(write(tmp_path))
    assert settings.tts.base_url == "http://file-host:8000"
    assert settings.tts.model == "file-model"


def test_env_overrides_file_base_url(tmp_path, monkeypatch):
    monkeypatch.setenv("ANCHOR_TTS__BASE_URL", "http://env-host:9000")
    settings = load_settings(write(tmp_path))
    assert settings.tts.base_url == "http://env-host:9000"
    assert settings.tts.model == "file-model"


def test_api_key_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ANCHOR_TTS__API_KEY", "secret")
    assert load_settings(write(tmp_path)).tts.api_key.get_secret_value() == "secret"


def test_config_path_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ANCHOR_CONFIG", str(write(tmp_path)))
    assert load_settings().tts.model == "file-model"


def test_missing_explicit_file(tmp_path):
    with pytest.raises(ConfigError):
        load_settings(tmp_path / "missing.toml")


def test_defaults_without_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = load_settings()
    assert settings.tts.voice == "thorsten"
    assert settings.audio.loudness_target_lufs == -18.0


def test_cache_dir_from_config(tmp_path):
    settings = load_settings(write(tmp_path, cache_dir=str(tmp_path / "segs")))
    assert settings.cache.dir == tmp_path / "segs"


def test_example_config_loads_and_expands_home(monkeypatch):
    from pathlib import Path

    settings = load_settings(Path(__file__).parent.parent / "anchor.example.toml")
    assert settings.cache.dir == Path("~/.cache/anchor/segments").expanduser()
    assert settings.tts.model == "speaches-ai/piper-de_DE-thorsten-medium"
