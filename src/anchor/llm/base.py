"""LLM Adapter protocol, result and error types (docs/spec.md §10.1, design D2).

The spec sketch's `temperature` parameter is dropped: current models reject sampling
parameters, so variation comes from the prompt and the request content alone.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict, runtime_checkable

from pydantic import BaseModel, ValidationError


class Message(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class LLMError(RuntimeError):
    """Generation failed. The message names provider, model and cause, never a credential."""


class LLMInvalidOutputError(LLMError):
    """The output could not be parsed or does not match the target schema."""

    def __init__(self, message: str, raw: str):
        super().__init__(message)
        self.raw = raw


class LLMRefusalError(LLMError):
    """The provider declined the request."""

    def __init__(self, message: str, raw: str = ""):
        super().__init__(message)
        self.raw = raw


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    document: T
    raw: str
    model: str
    input_tokens: int
    output_tokens: int
    duration_sec: float

    def usage(self) -> dict:
        return {"model": self.model, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "duration_sec": round(self.duration_sec, 3)}


@runtime_checkable
class LLMAdapter(Protocol):
    def generate_structured[T: BaseModel](
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        model: str,
        history: Sequence[Message] = (),
    ) -> LLMResult[T]:
        """`history` continues the conversation after `user` (alternating assistant/user turns),
        e.g. a previous answer followed by error feedback."""
        ...


_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n\s*```\s*$", re.S)


def parse_structured[T: BaseModel](raw: str, schema: type[T], *, source: str) -> T:
    """Validate `raw` against `schema`; a surrounding Markdown code fence is tolerated."""
    match = _FENCE.match(raw)
    text = match.group(1) if match else raw
    try:
        return schema.model_validate_json(text)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or '$'}: {e['msg']}"
            for e in exc.errors(include_url=False)[:20]
        )
        raise LLMInvalidOutputError(
            f"{source}: output does not match schema {schema.__name__}: {details}", raw
        ) from None
