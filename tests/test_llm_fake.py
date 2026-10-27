import pytest
from pydantic import BaseModel

from anchor.llm import FakeLLMAdapter, LLMAdapter, LLMError, LLMInvalidOutputError


class Doc(BaseModel):
    name: str
    count: int


def test_fake_is_an_adapter():
    assert isinstance(FakeLLMAdapter(), LLMAdapter)


def test_queued_responses_in_order():
    fake = FakeLLMAdapter().queue({"name": "a", "count": 1}, Doc(name="b", count=2),
                                  '{"name": "c", "count": 3}')
    names = [fake.generate_structured("s", "u", Doc, model="m").document.name for _ in range(3)]
    assert names == ["a", "b", "c"]


def test_queued_exception_is_raised():
    fake = FakeLLMAdapter().queue(LLMError("boom"))
    with pytest.raises(LLMError, match="boom"):
        fake.generate_structured("s", "u", Doc, model="m")


def test_empty_queue_fails():
    with pytest.raises(LLMError, match="no queued response"):
        FakeLLMAdapter().generate_structured("s", "u", Doc, model="m")


def test_calls_are_recorded():
    fake = FakeLLMAdapter().queue({"name": "a", "count": 1})
    history = [{"role": "assistant", "content": "x"}, {"role": "user", "content": "fix it"}]
    result = fake.generate_structured("sys", "usr", Doc, model="anthropic/x", history=history)
    call = fake.calls[0]
    assert (call.system, call.user, call.schema, call.model) == ("sys", "usr", Doc, "anthropic/x")
    assert call.history == history
    assert result.model == "anthropic/x"
    assert result.input_tokens > 0 and result.output_tokens > 0


def test_invalid_raw_output_carries_raw_text():
    raw = '{"name": "a"}'
    fake = FakeLLMAdapter().queue(raw)
    with pytest.raises(LLMInvalidOutputError) as exc:
        fake.generate_structured("s", "u", Doc, model="m")
    assert exc.value.raw == raw
    assert "count" in str(exc.value)


def test_unparseable_output():
    fake = FakeLLMAdapter().queue("not json at all")
    with pytest.raises(LLMInvalidOutputError) as exc:
        fake.generate_structured("s", "u", Doc, model="m")
    assert exc.value.raw == "not json at all"


def test_code_fence_is_tolerated():
    fake = FakeLLMAdapter().queue('```json\n{"name": "a", "count": 1}\n```')
    assert fake.generate_structured("s", "u", Doc, model="m").document.count == 1
