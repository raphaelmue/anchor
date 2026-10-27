"""Generation record: one JSON file per generation run, success or failure (design D10).

It holds what is needed to reproduce and debug a run (NFR-7): models, prompt and lexicon
versions, the request hash, and per attempt the raw output, errors, review and usage. It never
holds credentials. Its content (goal context, Script text) is what was sent to the provider.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from anchor.generate.request import ScriptRequest
from anchor.render.output import write_json_atomic

RECORD_VERSION = 1


def record_path(output: Path) -> Path:
    """`out/day.json` -> `out/day.generation.json` next to it."""
    return output.with_name(f"{output.stem}.generation.json")


def request_sha256(request: ScriptRequest) -> str:
    canonical = json.dumps(request.model_dump(mode="json"), sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class AttemptRecord:
    number: int
    raw_output: str | None = None
    errors: list[dict] = field(default_factory=list)
    review: dict = field(default_factory=lambda: {"skipped": True, "reason": "not reached"})
    usage: list[dict] = field(default_factory=list)  # one entry per LLM call (generation, review)
    duration_sec: float = 0.0
    estimate: dict | None = None
    failure: str | None = None  # refusal or transport failure that ended the run


@dataclass
class GenerationRecord:
    request: ScriptRequest
    output: Path
    models: dict
    prompt_versions: dict
    lexicon_version: str
    chars_per_sec: float
    review_enabled: bool
    started_at: str = field(default_factory=now)
    attempts: list[AttemptRecord] = field(default_factory=list)
    outcome: str = "running"
    errors: list[dict] = field(default_factory=list)  # errors that ended the run

    @property
    def path(self) -> Path:
        return record_path(self.output)

    def totals(self) -> dict:
        calls = [u for a in self.attempts for u in a.usage]
        return {"calls": len(calls),
                "input_tokens": sum(u["input_tokens"] for u in calls),
                "output_tokens": sum(u["output_tokens"] for u in calls)}

    def as_dict(self) -> dict:
        return {
            "record_version": RECORD_VERSION,
            "outcome": self.outcome,
            "started_at": self.started_at,
            "finished_at": now(),
            "output": str(self.output),
            "request_sha256": request_sha256(self.request),
            "models": self.models,
            "prompt_versions": self.prompt_versions,
            "lexicon_version": self.lexicon_version,
            "chars_per_sec": self.chars_per_sec,
            "review": "enabled" if self.review_enabled else "skipped",
            "usage": self.totals(),
            "errors": self.errors,
            "attempts": [a.__dict__ for a in self.attempts],
        }

    def write(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self.path, self.as_dict())
        return self.path
