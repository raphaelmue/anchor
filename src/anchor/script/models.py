"""Pydantic models for Session Script v1.2 (docs/spec.md §9)."""

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.2"
MAX_SPEECH_CHARS = 300


class SessionType(StrEnum):
    DAY = "day"
    SLEEP = "sleep"
    SHORT = "short"
    CUE_RECALL = "cue_recall"
    REHEARSAL = "rehearsal"
    PRE_EVENT = "pre_event"
    TASTER = "taster"


class SpeechRole(StrEnum):
    INDUCTION = "induction"
    DEEPENING = "deepening"
    EMERGENCE = "emergence"


class _Segment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SpeechSegment(_Segment):
    type: Literal["speech"]
    text: str
    style: str | None = None
    role: SpeechRole | None = None
    strategy: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_formula(cls, data: Any) -> Any:
        if isinstance(data, dict) and "formula" in data:
            raise ValueError(
                f"Formula references are not yet supported (formula {data['formula']!r}): "
                "they require the content base; use literal `text` instead"
            )
        return data

    @field_validator("text")
    @classmethod
    def _text_limits(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("text must not be empty")
        if len(text) > MAX_SPEECH_CHARS:
            raise ValueError(f"text has {len(text)} characters, at most {MAX_SPEECH_CHARS} allowed")
        return text


class _TimedSegment(_Segment):
    seconds: float = Field(ge=0)
    elastic: tuple[float, float] | None = None

    @model_validator(mode="after")
    def _elastic_range(self):
        if self.elastic is not None:
            lo, hi = self.elastic
            if not 0 <= lo <= self.seconds <= hi:
                raise ValueError(
                    f"elastic range [{lo:g}, {hi:g}] must satisfy "
                    f"0 <= min <= seconds ({self.seconds:g}) <= max"
                )
        return self

    @property
    def is_elastic(self) -> bool:
        return self.elastic is not None


class PauseSegment(_TimedSegment):
    type: Literal["pause"]


class SilentPracticeSegment(_TimedSegment):
    type: Literal["silent_practice"]
    prompt: str | None = None

    @field_validator("prompt")
    @classmethod
    def _prompt_limits(cls, prompt: str | None) -> str | None:
        if prompt is not None:
            SpeechSegment._text_limits(prompt)
        return prompt


class SoundSegment(_Segment):
    type: Literal["sound"]
    sound: str = Field(min_length=1)


class AmbienceSegment(_Segment):
    type: Literal["ambience"]
    ambience: str = Field(min_length=1)


class MarkerSegment(_Segment):
    type: Literal["marker"]
    name: str = Field(min_length=1)


Segment = Annotated[
    SpeechSegment
    | PauseSegment
    | SilentPracticeSegment
    | SoundSegment
    | AmbienceSegment
    | MarkerSegment,
    Field(discriminator="type"),
]


class Script(BaseModel):
    """A Session Script. Optional metadata is preserved but not interpreted by rendering."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    session_type: SessionType
    language: str = Field(pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")
    target_duration_sec: float = Field(gt=0)
    segments: list[Segment] = Field(min_length=1)

    session_context: str | None = None
    goal_pattern: str | None = None
    goal_domain: str | None = None
    method: str | None = None
    guidance_level: str | None = None
    stage_ref: str | None = None
    content_snapshot: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _supported_version(cls, version: str) -> str:
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version {version!r}; the supported version is "
                f"{SCHEMA_VERSION!r}"
            )
        return version
