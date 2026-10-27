"""LLM Adapter on LiteLLM (design D2, D3; mechanism verified in docs/llm-scripts.md §2).

LiteLLM translates a Pydantic `response_format` into the provider's native structured output
(Anthropic `output_format`, OpenAI `json_schema`); the answer is still validated locally, since a
refusal or truncation can produce invalid output. Retrying is ours alone (`num_retries=0`).
"""

import os
import time
from collections.abc import Callable, Sequence

import litellm
from pydantic import BaseModel

from anchor.config import LLMSettings
from anchor.llm.base import (
    LLMError,
    LLMInvalidOutputError,
    LLMRefusalError,
    LLMResult,
    Message,
    parse_structured,
)

RETRYABLE = (
    litellm.RateLimitError,
    litellm.Timeout,
    litellm.APIConnectionError,
    litellm.InternalServerError,
    litellm.ServiceUnavailableError,
)


REQUIRED_ENV = {"litellm_proxy": ("LITELLM_PROXY_API_BASE",)}
EFFORT_PROVIDERS = {"anthropic", "litellm_proxy"}


def provider_of(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else "unknown"


def _scrub(text: str) -> str:
    """Remove any credential value from `text`, in case a provider message echoes one."""
    for name, value in os.environ.items():
        if value and len(value) >= 8 and ("API_KEY" in name or name.endswith("_TOKEN")):
            text = text.replace(value, "***")
    return text


def check_environment(model: str) -> None:
    """Fail before any request if the provider's API key is not set."""
    missing = litellm.validate_environment(model).get("missing_keys") or []
    # LiteLLM reports a proxy model as ready without a base URL and then sends the request,
    # with the proxy key, to api.openai.com. Require the base URL explicitly.
    missing += [var for var in REQUIRED_ENV.get(provider_of(model), ())
                if not os.environ.get(var) and var not in missing]
    if missing:
        raise LLMError(
            f"{model}: no API key for provider {provider_of(model)}: "
            f"set {' / '.join(missing)} in the environment"
        )


def _cause(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    message = getattr(exc, "message", None) or str(exc)
    prefix = f"HTTP {status}: " if status else ""
    return _scrub(f"{type(exc).__name__}: {prefix}{message}")[:1000]


class LiteLLMAdapter:
    def __init__(self, settings: LLMSettings, *, sleep: Callable[[float], None] = time.sleep):
        self.settings = settings
        self._sleep = sleep

    def preflight(self, *models: str) -> None:
        """Fail before any request if a model's provider has no API key set."""
        for model in dict.fromkeys(models):
            check_environment(model)

    def request_kwargs(
        self, system: str, user: str, schema: type[BaseModel], model: str,
        history: Sequence[Message] = (),
    ) -> dict:
        s = self.settings
        kwargs: dict = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user},
                         *({"role": m["role"], "content": m["content"]} for m in history)],
            "response_format": schema,
            "max_tokens": s.max_tokens,
            "timeout": s.timeout_sec,
            "num_retries": 0,
        }
        # LiteLLM maps `reasoning_effort` to Anthropic `output_config.effort` (with adaptive
        # thinking); a LiteLLM proxy receives it as-is and maps it for its backend model.
        # No sampling parameters are ever sent.
        if s.effort and provider_of(model) in EFFORT_PROVIDERS:
            kwargs["reasoning_effort"] = s.effort
        return kwargs

    def _complete(self, kwargs: dict):
        model = kwargs["model"]
        where = f"provider {provider_of(model)}, model {model}"
        for attempt in range(self.settings.retries + 1):
            try:
                return litellm.completion(**kwargs)
            except RETRYABLE as exc:
                if attempt == self.settings.retries:
                    raise LLMError(f"LLM call failed after {attempt + 1} attempt(s) "
                                   f"({where}): {_cause(exc)}") from None
                self._sleep(self.settings.backoff_sec * 2**attempt)
            except Exception as exc:  # 4xx other than 429, or a local error: not retried
                raise LLMError(f"LLM call failed ({where}): {_cause(exc)}") from None
        raise AssertionError("unreachable")

    def generate_structured[T: BaseModel](
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        model: str,
        history: Sequence[Message] = (),
    ) -> LLMResult[T]:
        check_environment(model)
        started = time.perf_counter()
        response = self._complete(self.request_kwargs(system, user, schema, model, history))
        duration = time.perf_counter() - started

        choice = response.choices[0]
        message = choice.message
        raw = message.content or ""
        refusal = getattr(message, "refusal", None)
        if choice.finish_reason == "content_filter" or refusal:
            raise LLMRefusalError(
                f"{model} declined the request"
                + (f": {_scrub(refusal)[:500]}" if isinstance(refusal, str) else ""), raw)
        source = model
        if choice.finish_reason == "length":
            source = f"{model} (output truncated at max_tokens={self.settings.max_tokens})"
        if not raw.strip():
            raise LLMInvalidOutputError(f"{source}: empty output", raw)
        document = parse_structured(raw, schema, source=source)

        usage = getattr(response, "usage", None)
        used = response.model or model
        if "/" not in used:
            used = f"{provider_of(model)}/{used}"
        return LLMResult(document, raw, used,
                         int(getattr(usage, "prompt_tokens", 0) or 0),
                         int(getattr(usage, "completion_tokens", 0) or 0), duration)


def build_llm_adapter(settings: LLMSettings) -> LiteLLMAdapter:
    return LiteLLMAdapter(settings)
