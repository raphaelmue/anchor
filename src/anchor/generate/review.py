"""LLM Suggestion Review (spec `script-domain-validation`, design D9).

A separate LLM call checks every spoken Segment against the Suggestion Rules (spec §8.2). It runs
only after all rule-based checks passed. Findings on Segments that do not exist or are not
spoken text are discarded as anomalies rather than reported as Script errors.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from anchor.generate.prompts import ledger_text, load_prompt, style_sheet_text
from anchor.generate.request import ScriptRequest
from anchor.llm import LLMAdapter
from anchor.script.domain import DomainIssue
from anchor.script.duration import spoken_texts
from anchor.script.models import Script

REVIEW_PROMPT_VERSION = "review.v1"


class ReviewRule(StrEnum):
    POSITIVE_REALISTIC = "positive_realistic"
    PERMISSIVE_LANGUAGE = "permissive_language"
    NO_ABSOLUTES = "no_absolutes"
    NO_MEDICAL = "no_medical"
    GOAL_ONLY = "goal_only"
    CUE_WORD_PAIRING = "cue_word_pairing"
    STYLE_SHEET = "style_sheet"
    LEDGER = "ledger"


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_index: int
    rule: ReviewRule
    explanation: str


class ReviewFindings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[Finding]


@dataclass(frozen=True)
class ReviewResult:
    skipped: bool
    reason: str = ""
    issues: list[DomainIssue] = field(default_factory=list)
    anomalies: list[dict] = field(default_factory=list)
    raw: str | None = None
    usage: dict | None = None

    @classmethod
    def skip(cls, reason: str) -> "ReviewResult":
        return cls(skipped=True, reason=reason)

    def as_record(self) -> dict:
        if self.skipped:
            return {"skipped": True, "reason": self.reason}
        return {"skipped": False, "findings": [i.as_dict() for i in self.issues],
                "anomalies": self.anomalies, "raw_output": self.raw, "usage": self.usage}


def render_review_prompts(script: Script, request: ScriptRequest) -> tuple[str, str]:
    segments = "\n".join(f"{i}: {text}" for i, text in spoken_texts(script))
    values = {
        "session_type": request.session_type.value,
        "method": request.method.value,
        "language": request.language,
        "goal_pattern": request.goal.pattern,
        "goal_domain": request.goal.domain or "(none)",
        "target_situation": request.goal.target_situation,
        "desired_state": request.goal.desired_state,
        "style_sheet": style_sheet_text(request),
        "ledger": ledger_text(request),
        "segments": segments,
    }
    return (load_prompt("review_system.v1").format_map(values),
            load_prompt("review_user.v1").format_map(values))


def review_script(script: Script, request: ScriptRequest, adapter: LLMAdapter, *,
                  model: str) -> ReviewResult:
    """Run the review; raises LLMError if the call fails."""
    system, user = render_review_prompts(script, request)
    result = adapter.generate_structured(system, user, ReviewFindings, model=model)
    spoken = {i for i, _ in spoken_texts(script)}
    issues, anomalies = [], []
    for finding in result.document.findings:
        if finding.segment_index in spoken:
            issues.append(DomainIssue(f"segments[{finding.segment_index}]",
                                      f"review.{finding.rule}", finding.explanation))
        else:
            reason = ("no such Segment" if not 0 <= finding.segment_index < len(script.segments)
                      else "not spoken text")
            anomalies.append({**finding.model_dump(mode="json"), "reason": reason})
    return ReviewResult(False, issues=issues, anomalies=anomalies, raw=result.raw,
                        usage=result.usage())
