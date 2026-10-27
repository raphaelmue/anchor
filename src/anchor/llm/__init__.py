"""LLM Adapter: structured JSON generation through a configurable provider (docs/spec.md §10.1)."""

from anchor.llm.base import (
    LLMAdapter,
    LLMError,
    LLMInvalidOutputError,
    LLMRefusalError,
    LLMResult,
    Message,
    parse_structured,
)
from anchor.llm.fake import FakeCall, FakeLLMAdapter

__all__ = [
    "FakeCall",
    "FakeLLMAdapter",
    "LLMAdapter",
    "LLMError",
    "LLMInvalidOutputError",
    "LLMRefusalError",
    "LLMResult",
    "Message",
    "parse_structured",
]
