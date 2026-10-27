"""Script Request and Program Style Sheet (spec `script-generation`, FR-49/FR-50).

A Script Request holds everything Script generation needs, and nothing that may not leave the
server (spec §12): Goal Profile essentials, the Style Sheet and an optional Ledger summary. There
is no field for names, Safety Screening answers or Practice Logs, and unknown fields are rejected.
"""

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from anchor.script.models import SessionType
from anchor.script.validate import ValidationIssue, _format_location, _message

SUPPORTED_LANGUAGES = ("de-DE",)


class MethodId(StrEnum):
    PMR = "pmr"
    AUTOGENIC_TRAINING = "autogenic_training"
    SELF_HYPNOSIS = "self_hypnosis"
    MINDFULNESS_BODY_SCAN = "mindfulness_body_scan"
    PACED_BREATHING = "paced_breathing"
    MENTAL_REHEARSAL = "mental_rehearsal"
    IMPLEMENTATION_INTENTION = "implementation_intention"


class Strategy(StrEnum):
    CALM_COMPETENCE = "calm_competence"
    EGO_STRENGTHENING = "ego_strengthening"
    MENTAL_REHEARSAL = "mental_rehearsal"
    IF_THEN_CUE = "if_then_cue"
    REFRAME = "reframe"
    SLEEP_PERMISSION = "sleep_permission"


class GuidanceLevel(StrEnum):
    GUIDED = "guided"
    SEMI_GUIDED = "semi_guided"
    SELF_GUIDED = "self_guided"


_ID = r"^[a-z][a-z0-9_]*$"  # curated catalog id; Patterns and Domains live in Blueprints (M3)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Goal(_Strict):
    pattern: str = Field(pattern=_ID)
    domain: str | None = Field(default=None, pattern=_ID)
    target_situation: str = Field(min_length=1)
    desired_state: str = Field(min_length=1)


class StyleSheet(_Strict):
    address: Literal["du", "Sie"]
    tone: str = Field(min_length=1)
    imagery: list[str] = Field(default_factory=list)
    cue_word: str | None = Field(default=None, min_length=1)
    cue_word_phrasing: str | None = None
    situation_vocabulary: list[str] = Field(default_factory=list)


class ScriptRequest(_Strict):
    session_type: SessionType
    method: MethodId
    guidance_level: GuidanceLevel
    target_duration_sec: float = Field(gt=0)
    language: str
    goal: Goal
    style_sheet: StyleSheet

    session_context: Literal["stage", "orientation", "library"] = "stage"
    stage_ref: str | None = None
    strategies: list[Strategy] = Field(default_factory=list)
    cue_word_introduced: bool = False
    suggestion_ledger: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("language")
    @classmethod
    def _supported_language(cls, language: str) -> str:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported language {language!r}; supported languages: "
                             f"{', '.join(SUPPORTED_LANGUAGES)}")
        return language


def _issues(exc: ValidationError) -> list[ValidationIssue]:
    issues = []
    for err in exc.errors():
        msg = _message(err)
        if err["type"] == "enum" and err["loc"][:1] == ("method",):
            msg = f"unknown Method {err['input']!r}; Method ids: " + ", ".join(m.value
                                                                               for m in MethodId)
        issues.append(ValidationIssue(_format_location(err["loc"]), msg))
    return issues


def parse_request(data: Any) -> tuple[ScriptRequest | None, list[ValidationIssue]]:
    """Validate a parsed YAML document; every error is reported with its field path."""
    if not isinstance(data, dict):
        return None, [ValidationIssue("$", "a Script Request must be a mapping")]
    try:
        return ScriptRequest.model_validate(data), []
    except ValidationError as exc:
        return None, _issues(exc)


def load_request(path: Path) -> tuple[ScriptRequest | None, list[ValidationIssue]]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, [ValidationIssue("$", f"cannot read {path}: {exc}")]
    except yaml.YAMLError as exc:
        return None, [ValidationIssue("$", f"invalid YAML: {exc}")]
    return parse_request(data)
