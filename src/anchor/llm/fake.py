"""Deterministic stand-in for an LLM Provider (design D12).

Responses are queued as documents (dicts or models, serialized to JSON), raw strings (parsed
like real output) or exceptions (raised). Every call is recorded.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from anchor.llm.base import LLMError, LLMResult, Message, parse_structured


@dataclass(frozen=True)
class FakeCall:
    system: str
    user: str
    schema: type[BaseModel]
    model: str
    history: list[Message]


@dataclass
class FakeLLMAdapter:
    responses: list[Any] = field(default_factory=list)
    calls: list[FakeCall] = field(default_factory=list)
    input_tokens: int = 1000
    output_tokens: int = 500

    def queue(self, *responses: Any) -> "FakeLLMAdapter":
        self.responses.extend(responses)
        return self

    def generate_structured[T: BaseModel](
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        model: str,
        history: Sequence[Message] = (),
    ) -> LLMResult[T]:
        self.calls.append(FakeCall(system, user, schema, model, list(history)))
        if not self.responses:
            raise LLMError(f"fake/{model}: no queued response for call {len(self.calls)}")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, BaseModel):
            raw = response.model_dump_json()
        elif isinstance(response, str):
            raw = response
        else:
            raw = json.dumps(response, ensure_ascii=False)
        document = parse_structured(raw, schema, source=f"fake/{model}")
        return LLMResult(document, raw, model, self.input_tokens, self.output_tokens, 0.01)
