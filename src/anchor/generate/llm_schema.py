"""The LLM-facing segment schema and its mapping to a Session Script (design D4).

The LLM writes segments only; all metadata comes from the Script Request. The schema stays
within what both Anthropic and OpenAI strict structured output accept: a plain `anyOf` union
(no `oneOf`/discriminator), objects instead of tuples (`elastic`), every field required but
nullable, and no length or range constraints. Those limits are enforced afterwards by Script
validation, whose located errors become the retry feedback.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from anchor.generate.request import ScriptRequest, Strategy
from anchor.script.models import SCHEMA_VERSION, SpeechRole
from anchor.script.validate import ValidationResult, validate_script

BuiltinSound = Literal["bell_soft"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Elastic(_Strict):
    min: float
    max: float


class LLMSpeech(_Strict):
    type: Literal["speech"]
    text: str
    role: SpeechRole | None
    strategy: Strategy | None


class LLMPause(_Strict):
    type: Literal["pause"]
    seconds: float
    elastic: Elastic | None


class LLMSilentPractice(_Strict):
    type: Literal["silent_practice"]
    seconds: float
    elastic: Elastic | None
    prompt: str | None


class LLMSound(_Strict):
    type: Literal["sound"]
    sound: BuiltinSound


class LLMScript(_Strict):
    segments: list[LLMSpeech | LLMPause | LLMSilentPractice | LLMSound]


def _segment(seg: BaseModel) -> dict[str, Any]:
    out = {k: v for k, v in seg.model_dump(mode="json").items() if v is not None}
    if isinstance(seg, LLMPause | LLMSilentPractice) and seg.elastic is not None:
        out["elastic"] = [seg.elastic.min, seg.elastic.max]
    return out


def script_document(generated: LLMScript, request: ScriptRequest) -> dict[str, Any]:
    """The Session Script v1.2 document: metadata from the request, segments from the LLM."""
    doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "session_type": request.session_type.value,
        "session_context": request.session_context,
        "language": request.language,
        "goal_pattern": request.goal.pattern,
        "goal_domain": request.goal.domain,
        "method": request.method.value,
        "guidance_level": request.guidance_level.value,
        "target_duration_sec": request.target_duration_sec,
        "stage_ref": request.stage_ref,
        "segments": [_segment(s) for s in generated.segments],
    }
    return {k: v for k, v in doc.items() if v is not None}


def to_script(generated: LLMScript, request: ScriptRequest) -> ValidationResult:
    return validate_script(script_document(generated, request))
