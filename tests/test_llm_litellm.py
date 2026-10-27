import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import httpx
import litellm
import pytest
from pydantic import BaseModel

from anchor.config import LLMSettings
from anchor.llm import LLMAdapter, LLMError, LLMInvalidOutputError, LLMRefusalError
from anchor.llm.litellm_adapter import LiteLLMAdapter

SAMPLING = ("temperature", "top_p", "top_k")


class Doc(BaseModel):
    name: str
    count: int


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-SECRET-0123456789")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test-SECRET-0123456789")


# -- request shape over LiteLLM's real transport (task 2.3) -------------------------------------


@pytest.fixture
def server():
    """A local HTTP server that records requests and answers like Anthropic or OpenAI."""
    seen: list[tuple[str, dict, dict]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            seen.append((self.path, dict(self.headers), body))
            text = '{"name": "a", "count": 1}'
            if self.path.endswith("/messages"):
                resp = {"id": "m", "type": "message", "role": "assistant", "model": body["model"],
                        "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
                        "usage": {"input_tokens": 10, "output_tokens": 5}}
            else:
                resp = {"id": "c", "object": "chat.completion", "created": 0,
                        "model": body["model"],
                        "choices": [{"index": 0, "finish_reason": "stop",
                                     "message": {"role": "assistant", "content": text}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                                  "total_tokens": 15}}
            out = json.dumps(resp).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", seen
    srv.shutdown()


def _send(base_url, model, monkeypatch, effort="high"):
    real = litellm.completion
    monkeypatch.setattr(litellm, "completion", lambda **kw: real(api_base=base_url, **kw))
    adapter = LiteLLMAdapter(LLMSettings(effort=effort))
    return adapter.generate_structured("sys", "usr", Doc, model=model,
                                       history=[{"role": "assistant", "content": "{}"},
                                                {"role": "user", "content": "fix"}])


def test_anthropic_request_uses_native_structured_output(server, monkeypatch):
    base_url, seen = server
    result = _send(base_url, "anthropic/claude-opus-5-5", monkeypatch)
    assert result.document == Doc(name="a", count=1)
    path, headers, body = seen[0]
    assert path.endswith("/v1/messages")
    assert body["output_format"]["type"] == "json_schema"
    assert body["output_format"]["schema"]["required"] == ["name", "count"]
    assert "tools" not in body and "tool_choice" not in body
    assert body["output_config"] == {"effort": "high"}
    assert body["system"][0]["text"] == "sys"
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert not set(SAMPLING) & set(body)
    assert "structured-outputs" in headers.get("anthropic-beta", "")


def test_anthropic_request_without_effort(server, monkeypatch):
    base_url, seen = server
    _send(base_url, "anthropic/claude-opus-5-5", monkeypatch, effort="")
    body = seen[0][2]
    assert "output_config" not in body and "thinking" not in body


def test_openai_request_uses_json_schema(server, monkeypatch):
    base_url, seen = server
    result = _send(f"{base_url}/v1", "openai/gpt-5", monkeypatch)
    assert result.model == "openai/gpt-5"
    path, _, body = seen[0]
    assert path.endswith("/chat/completions")
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert "reasoning_effort" not in body
    assert not set(SAMPLING) & set(body)


def test_litellm_proxy_request(server, monkeypatch):
    base_url, seen = server
    monkeypatch.setenv("LITELLM_PROXY_API_BASE", base_url)
    monkeypatch.setenv("LITELLM_PROXY_API_KEY", "sk-proxy-test")
    adapter = LiteLLMAdapter(LLMSettings(effort="high"))
    result = adapter.generate_structured("sys", "usr", Doc, model="litellm_proxy/claude-opus-5-5")
    assert result.document == Doc(name="a", count=1)
    path, headers, body = seen[0]
    assert path == "/chat/completions"
    assert headers.get("Authorization") == "Bearer sk-proxy-test"
    assert body["model"] == "claude-opus-5-5"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["reasoning_effort"] == "high"
    assert not set(SAMPLING) & set(body)


def test_litellm_proxy_requires_base_url(monkeypatch):
    monkeypatch.delenv("LITELLM_PROXY_API_BASE", raising=False)
    monkeypatch.setattr(litellm, "completion", lambda **kw: pytest.fail("request sent"))
    with pytest.raises(LLMError, match="LITELLM_PROXY_API_BASE"):
        LiteLLMAdapter(LLMSettings()).generate_structured(
            "s", "u", Doc, model="litellm_proxy/claude-opus-5-5")


# -- behaviour with mocked litellm.completion (task 2.4) ----------------------------------------


def _response(content, finish="stop", model="claude-opus-5-5", refusal=None):
    message = SimpleNamespace(content=content, refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish)],
                           model=model,
                           usage=SimpleNamespace(prompt_tokens=1200, completion_tokens=340))


def _status_error(cls, status, message):
    if cls in (litellm.InternalServerError, litellm.RateLimitError, litellm.BadRequestError):
        resp = httpx.Response(status, request=httpx.Request("POST", "http://x"))
        return cls(message=message, llm_provider="anthropic", model="claude-opus-5-5",
                   response=resp)
    return cls(message=message, llm_provider="anthropic", model="claude-opus-5-5")


@pytest.fixture
def mock_completion(monkeypatch):
    calls: list[dict] = []
    queue: list = []

    def completion(**kwargs):
        calls.append(kwargs)
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(litellm, "completion", completion)
    return queue, calls


def adapter(**overrides):
    sleeps: list[float] = []
    a = LiteLLMAdapter(LLMSettings(**overrides), sleep=sleeps.append)
    a.sleeps = sleeps
    return a


def test_is_an_adapter():
    assert isinstance(adapter(), LLMAdapter)


def test_valid_output(mock_completion):
    queue, _ = mock_completion
    queue.append(_response('{"name": "x", "count": 2}'))
    result = adapter().generate_structured("s", "u", Doc, model="anthropic/claude-opus-5-5")
    assert result.document == Doc(name="x", count=2)


def test_usage_on_success(mock_completion):
    queue, _ = mock_completion
    queue.append(_response('{"name": "x", "count": 2}'))
    result = adapter().generate_structured("s", "u", Doc, model="anthropic/claude-opus-5-5")
    assert result.model == "anthropic/claude-opus-5-5"
    assert (result.input_tokens, result.output_tokens) == (1200, 340)
    assert result.duration_sec >= 0


def test_schema_mismatch(mock_completion):
    queue, _ = mock_completion
    queue.append(_response('{"name": "x"}'))
    with pytest.raises(LLMInvalidOutputError) as exc:
        adapter().generate_structured("s", "u", Doc, model="anthropic/claude-opus-5-5")
    assert "count" in str(exc.value)
    assert exc.value.raw == '{"name": "x"}'


def test_truncated_output_is_invalid(mock_completion):
    queue, _ = mock_completion
    queue.append(_response('{"name": "x", "cou', finish="length"))
    with pytest.raises(LLMInvalidOutputError, match="truncated"):
        adapter().generate_structured("s", "u", Doc, model="anthropic/claude-opus-5-5")


def test_missing_key(mock_completion, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    _, calls = mock_completion
    with pytest.raises(LLMError) as exc:
        adapter().generate_structured("s", "u", Doc, model="anthropic/claude-opus-5-5")
    assert "ANTHROPIC_API_KEY" in str(exc.value)
    assert "anthropic" in str(exc.value)
    assert calls == []


def test_server_error_then_success(mock_completion):
    queue, calls = mock_completion
    queue += [_status_error(litellm.InternalServerError, 500, "boom"),
              _response('{"name": "x", "count": 2}')]
    a = adapter(backoff_sec=1.0)
    assert a.generate_structured("s", "u", Doc, model="anthropic/claude-opus-5-5").document
    assert len(calls) == 2
    assert a.sleeps == [1.0]


@pytest.mark.parametrize("make", [
    lambda: _status_error(litellm.RateLimitError, 429, "slow down"),
    lambda: litellm.Timeout(message="timed out", model="claude-opus-5-5",
                            llm_provider="anthropic"),
    lambda: litellm.APIConnectionError(message="refused", llm_provider="anthropic",
                                       model="claude-opus-5-5"),
])
def test_transient_errors_retried_with_backoff(mock_completion, make):
    queue, calls = mock_completion
    queue += [make() for _ in range(3)]
    a = adapter(retries=2, backoff_sec=0.5)
    with pytest.raises(LLMError) as exc:
        a.generate_structured("s", "u", Doc, model="anthropic/claude-opus-5-5")
    assert len(calls) == 3
    assert a.sleeps == [0.5, 1.0]
    assert "anthropic" in str(exc.value) and "claude-opus-5-5" in str(exc.value)


def test_invalid_request_not_retried(mock_completion):
    queue, calls = mock_completion
    queue.append(_status_error(litellm.BadRequestError, 400, "output_format: bad schema"))
    with pytest.raises(LLMError) as exc:
        adapter().generate_structured("s", "u", Doc, model="anthropic/claude-opus-5-5")
    assert len(calls) == 1
    msg = str(exc.value)
    assert "provider anthropic" in msg and "anthropic/claude-opus-5-5" in msg
    assert "bad schema" in msg


def test_error_message_never_contains_key(mock_completion):
    queue, _ = mock_completion
    queue.append(_status_error(litellm.BadRequestError, 400,
                               "key sk-ant-test-SECRET-0123456789 rejected"))
    with pytest.raises(LLMError) as exc:
        adapter().generate_structured("s", "u", Doc, model="anthropic/claude-opus-5-5")
    assert "SECRET" not in str(exc.value)


def test_refusal_anthropic(mock_completion):
    queue, _ = mock_completion
    queue.append(_response(None, finish="content_filter"))
    with pytest.raises(LLMRefusalError):
        adapter().generate_structured("s", "u", Doc, model="anthropic/claude-opus-5-5")


def test_refusal_openai(mock_completion):
    queue, _ = mock_completion
    queue.append(_response(None, model="gpt-5", refusal="I can't help with that."))
    with pytest.raises(LLMRefusalError, match="can't help"):
        adapter().generate_structured("s", "u", Doc, model="openai/gpt-5")


def test_refusal_is_not_invalid_output():
    assert not issubclass(LLMRefusalError, LLMInvalidOutputError)


@pytest.mark.parametrize("model", ["anthropic/claude-opus-5-5", "openai/gpt-5"])
def test_no_sampling_params(mock_completion, model):
    queue, calls = mock_completion
    queue.append(_response('{"name": "x", "count": 2}'))
    adapter().generate_structured("s", "u", Doc, model=model)
    assert not set(SAMPLING) & set(calls[0])
    assert calls[0]["num_retries"] == 0
    assert calls[0]["response_format"] is Doc
