"""Full check of a Script against its request: structure, then domain rules, then the
optional LLM Suggestion Review (which runs only if every rule-based check passed)."""

from dataclasses import dataclass
from typing import Any

from anchor.generate.request import ScriptRequest
from anchor.generate.review import ReviewResult, review_script
from anchor.llm import LLMAdapter
from anchor.script.domain import DomainContext, DomainIssue, validate_domain
from anchor.script.duration import DurationEstimate
from anchor.script.models import Script
from anchor.script.validate import validate_script


@dataclass(frozen=True)
class CheckResult:
    script: Script | None
    issues: list[DomainIssue]
    estimate: DurationEstimate | None
    review: ReviewResult

    @property
    def ok(self) -> bool:
        return self.script is not None and not self.issues


def check_script(script: Script, request: ScriptRequest, ctx: DomainContext, *,
                 reviewer: LLMAdapter | None = None, review_model: str = "") -> CheckResult:
    domain = validate_domain(script, request, ctx)
    if domain.issues:
        review = ReviewResult.skip("rule-based checks failed")
    elif reviewer is None:
        review = ReviewResult.skip("review disabled")
    else:
        review = review_script(script, request, reviewer, model=review_model)
    return CheckResult(script, [*domain.issues, *review.issues], domain.estimate, review)


def check_document(doc: Any, request: ScriptRequest, ctx: DomainContext, *,
                   reviewer: LLMAdapter | None = None, review_model: str = "") -> CheckResult:
    structural = validate_script(doc)
    if not structural.ok:
        return CheckResult(None, [DomainIssue.structural(e) for e in structural.errors], None,
                           ReviewResult.skip("structural validation failed"))
    return check_script(structural.script, request, ctx, reviewer=reviewer,
                        review_model=review_model)
