"""Configuration: `anchor.toml` plus `ANCHOR_` environment overrides (design D11).

Precedence: explicit arguments > environment > config file > defaults.
The file is located via the `--config` option, `ANCHOR_CONFIG`, or `./anchor.toml`.
"""

import os
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

DEFAULT_CONFIG_PATH = Path("anchor.toml")


class TTSSettings(BaseModel):
    kind: Literal["openai", "speaches"] = "speaches"
    backend_id: str = "speaches"
    base_url: str = "http://127.0.0.1:8000"
    api_key: SecretStr | None = None
    model: str = "speaches-ai/piper-de_DE-thorsten-medium"
    voice: str = "thorsten"
    # Requested output rate; part of the cache key. Piper medium/high voices run at 22050 Hz.
    sample_rate: int = 22050
    timeout_sec: float = 120.0
    retries: int = Field(default=3, ge=0)
    backoff_sec: float = 0.5


def _expand(path: Path | None) -> Path | None:
    return path.expanduser() if path is not None else None


class CacheSettings(BaseModel):
    dir: Path = Field(default=Path("~/.cache/anchor/segments"), validate_default=True)

    _expand_dir = field_validator("dir")(_expand)


class AudioSettings(BaseModel):
    ffmpeg: str = "ffmpeg"
    # Optional YAML file whose values replace the built-in pacing profiles.
    pacing_file: Path | None = None
    loudness_target_lufs: float = -18.0
    true_peak_dbtp: float = -1.0
    # Speech units are normalized to this level before mixing.
    speech_lufs: float = -18.0
    # Noise Floor level relative to the loudness target.
    bed_level_lu: float = -42.0
    mp3_bitrate: str = "128k"
    opus_bitrate: str = "64k"

    _expand_pacing = field_validator("pacing_file")(_expand)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ANCHOR_", env_nested_delimiter="__", extra="forbid"
    )

    tts: TTSSettings = Field(default_factory=TTSSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)

    toml_path: ClassVar[Path | None] = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
        if cls.toml_path is not None:
            sources.append(TomlConfigSettingsSource(settings_cls, toml_file=cls.toml_path))
        return tuple(sources)


class ConfigError(RuntimeError):
    pass


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings; an explicitly named config file must exist, the default one may not."""
    explicit = config_path or (Path(p) if (p := os.environ.get("ANCHOR_CONFIG")) else None)
    path = explicit or DEFAULT_CONFIG_PATH
    if explicit is not None and not path.is_file():
        raise ConfigError(f"config file not found: {path}")

    class _Settings(Settings):
        toml_path = path if path.is_file() else None

    try:
        loaded = _Settings()
    except Exception as exc:  # pydantic ValidationError or TOML decode error
        raise ConfigError(f"invalid configuration ({path}): {exc}") from exc
    return Settings.model_validate(loaded.model_dump())
