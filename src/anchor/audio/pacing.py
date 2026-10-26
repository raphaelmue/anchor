"""Pacing profiles per Session Type (design D8)."""

from importlib import resources
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from anchor.script.models import SessionType


class PacingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    speed: float = Field(gt=0)
    sentence_gap_sec: float = Field(ge=0)
    segment_gap_sec: float = Field(ge=0)
    fade_in_sec: float = Field(ge=0)
    fade_out_sec: float = Field(ge=0)


class PacingError(ValueError):
    pass


def _read_yaml(text: str, source: str) -> dict:
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise PacingError(f"{source}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise PacingError(f"{source}: expected a mapping of Session Types")
    unknown = set(data) - {t.value for t in SessionType}
    if unknown:
        raise PacingError(f"{source}: unknown Session Types {sorted(unknown)}")
    return data


def load_pacing(override_file: Path | None = None) -> dict[SessionType, PacingProfile]:
    """Built-in profiles, with values from `override_file` replacing individual keys."""
    builtin = resources.files("anchor.audio").joinpath("pacing.yaml").read_text("utf-8")
    data = {k: dict(v) for k, v in _read_yaml(builtin, "pacing.yaml").items()}
    if override_file is not None:
        try:
            text = Path(override_file).read_text("utf-8")
        except OSError as exc:
            raise PacingError(f"cannot read pacing file {override_file}: {exc}") from exc
        for session_type, values in _read_yaml(text, str(override_file)).items():
            data.setdefault(session_type, {}).update(values or {})
    try:
        return {SessionType(k): PacingProfile(**v) for k, v in data.items()}
    except (TypeError, ValueError) as exc:
        raise PacingError(f"invalid pacing profile: {exc}") from exc
