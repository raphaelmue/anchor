"""The generation loop: Script Request -> LLM -> validated Session Script (design D6, FR-16).

Attempt n > 1 continues the conversation: the previous answer, then every error as
`location: rule: message`. Invalid output counts as an attempt. A refusal or a transport failure
(after the adapter's own retries) ends the run at once. The Script is written atomically, and
only on success; the generation record is written last, on every outcome.
"""

import time
from dataclasses import dataclass
from pathlib import Path

from anchor.config import LLMSettings
from anchor.generate.check import CheckResult, check_document
from anchor.generate.llm_schema import LLMScript, script_document
from anchor.generate.prompts import SCRIPT_PROMPT_VERSION, render_feedback, render_script_prompts
from anchor.generate.record import AttemptRecord, GenerationRecord
from anchor.generate.request import ScriptRequest
from anchor.generate.review import REVIEW_PROMPT_VERSION
from anchor.llm import LLMAdapter, LLMError, LLMInvalidOutputError, LLMRefusalError, Message
from anchor.render.output import write_json_atomic
from anchor.script.domain import DomainContext, DomainIssue
from anchor.script.duration import DurationEstimate
from anchor.script.models import Script


@dataclass(frozen=True)
class GenerationResult:
    outcome: str  # "success", "failed", "refused" or "error"
    script: Script | None
    errors: list[DomainIssue]  # of the last attempt, or the failure that ended the run
    attempts: int
    estimate: DurationEstimate | None
    record: GenerationRecord

    @property
    def ok(self) -> bool:
        return self.outcome == "success"

    @property
    def record_path(self) -> Path:
        return self.record.path


def _estimate_dict(est: DurationEstimate | None) -> dict | None:
    if est is None:
        return None
    return {"nominal_sec": round(est.nominal_sec, 1), "min_sec": round(est.min_sec, 1),
            "max_sec": round(est.max_sec, 1), "speech_chars": est.speech_chars,
            "target_sec": est.target_sec, "ok": est.ok}


def generate(
    request: ScriptRequest,
    output: Path,
    *,
    adapter: LLMAdapter,
    settings: LLMSettings,
    ctx: DomainContext,
    review: bool = True,
) -> GenerationResult:
    prompts = render_script_prompts(request, ctx)
    review_model = settings.effective_review_model
    record = GenerationRecord(
        request=request,
        output=output,
        models={"generation": settings.model, "review": review_model if review else None},
        prompt_versions={"script": SCRIPT_PROMPT_VERSION,
                         "review": REVIEW_PROMPT_VERSION if review else None},
        lexicon_version=ctx.lexicon(request.language).version,
        chars_per_sec=ctx.chars_per_sec,
        review_enabled=review,
    )
    history: list[Message] = []
    last: CheckResult | None = None
    errors: list[DomainIssue] = []

    def finish(outcome: str, script: Script | None = None) -> GenerationResult:
        record.outcome = outcome
        if outcome != "success":
            record.errors = [e.as_dict() for e in errors]
        record.write()
        return GenerationResult(outcome, script, errors, len(record.attempts),
                                last.estimate if last else None, record)

    for number in range(1, settings.max_attempts + 1):
        attempt = AttemptRecord(number)
        record.attempts.append(attempt)
        last = None
        started = time.perf_counter()
        try:
            result = adapter.generate_structured(prompts.system, prompts.user, LLMScript,
                                                 model=settings.model, history=history)
        except LLMInvalidOutputError as exc:
            raw = exc.raw
            errors = [DomainIssue("$", "output.invalid", str(exc))]
        except LLMRefusalError as exc:
            attempt.raw_output, attempt.failure = exc.raw, f"refused: {exc}"
            attempt.duration_sec = round(time.perf_counter() - started, 3)
            errors = [DomainIssue("$", "llm.refusal", str(exc))]
            return finish("refused")
        except LLMError as exc:
            attempt.failure = str(exc)
            attempt.duration_sec = round(time.perf_counter() - started, 3)
            errors = [DomainIssue("$", "llm.error", str(exc))]
            return finish("error")
        else:
            raw = result.raw
            attempt.usage.append({"call": "generation", **result.usage()})
            try:
                last = check_document(script_document(result.document, request), request, ctx,
                                      reviewer=adapter if review else None,
                                      review_model=review_model)
            except LLMError as exc:  # the review call failed
                attempt.raw_output, attempt.failure = raw, f"review failed: {exc}"
                attempt.duration_sec = round(time.perf_counter() - started, 3)
                errors = [DomainIssue("$", "llm.error", f"review failed: {exc}")]
                return finish("error")
            errors = last.issues
            attempt.review = last.review.as_record()
            if last.review.usage:
                attempt.usage.append({"call": "review", **last.review.usage})
            attempt.estimate = _estimate_dict(last.estimate)

        attempt.raw_output = raw
        attempt.errors = [e.as_dict() for e in errors]
        attempt.duration_sec = round(time.perf_counter() - started, 3)
        if last is not None and last.ok:
            output.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(output, last.script.model_dump(mode="json", exclude_none=True))
            return finish("success", last.script)
        history += [{"role": "assistant", "content": raw or "(empty output)"},
                    {"role": "user", "content": render_feedback(errors)}]

    return finish("failed")

