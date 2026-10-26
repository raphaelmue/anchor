"""Structural validation that reports every error with its location at once."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from anchor.script.models import Script

_SEGMENT_TAGS = {"speech", "pause", "silent_practice", "sound", "ambience", "marker"}


@dataclass(frozen=True)
class ValidationIssue:
    location: str
    message: str

    def __str__(self) -> str:
        return f"{self.location}: {self.message}"


@dataclass(frozen=True)
class ValidationResult:
    script: Script | None
    errors: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.script is not None and not self.errors


def _format_location(loc: tuple[int | str, ...]) -> str:
    parts: list[str] = []
    for i, item in enumerate(loc):
        if isinstance(item, int):
            parts.append(f"[{item}]")
        elif i > 0 and isinstance(loc[i - 1], int) and item in _SEGMENT_TAGS:
            # Pydantic adds the discriminator tag after the index; the index alone is clearer.
            continue
        else:
            parts.append(f".{item}" if parts else str(item))
    return "".join(parts) or "$"


def _message(err: dict[str, Any]) -> str:
    msg = err["msg"]
    # Pydantic prefixes errors raised from our validators with "Value error, ".
    return msg.removeprefix("Value error, ")


def validate_script(data: Any) -> ValidationResult:
    """Validate a parsed JSON document (or JSON text) as a Session Script."""
    if isinstance(data, str | bytes):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            return ValidationResult(None, [ValidationIssue("$", f"invalid JSON: {exc}")])
    try:
        return ValidationResult(Script.model_validate(data))
    except ValidationError as exc:
        issues = [
            ValidationIssue(_format_location(err["loc"]), _message(err)) for err in exc.errors()
        ]
        return ValidationResult(None, issues)


def load_script(path: Path) -> ValidationResult:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return ValidationResult(None, [ValidationIssue("$", f"cannot read {path}: {exc}")])
    return validate_script(text)
