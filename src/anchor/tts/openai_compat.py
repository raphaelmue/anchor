"""Adapter for OpenAI-compatible speech endpoints (`POST /v1/audio/speech`), design D9."""

import time
from collections.abc import Callable

import httpx

from anchor.tts.base import (
    HealthStatus,
    SynthesisIdentity,
    SynthesisResult,
    TTSCapabilities,
    TTSError,
    Voice,
    wav_sample_rate,
)


class OpenAICompatibleAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        voice: str,
        backend_id: str = "openai",
        api_key: str | None = None,
        sample_rate: int = 22050,
        timeout_sec: float = 120.0,
        retries: int = 3,
        backoff_sec: float = 0.5,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.id = backend_id
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.voice = voice
        self.sample_rate = sample_rate
        self.retries = retries
        self.backoff_sec = backoff_sec
        self._sleep = sleep
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(
            base_url=self.base_url, headers=headers, timeout=timeout_sec, transport=transport
        )

    # -- helpers -----------------------------------------------------------------------------

    def _error(self, cause: str) -> TTSError:
        return TTSError(f"TTS backend {self.id} ({self.base_url}): {cause}")

    @staticmethod
    def _detail(response: httpx.Response) -> str:
        try:
            body = response.json()
            if isinstance(body, dict) and "detail" in body:
                return str(body["detail"])
        except ValueError:
            pass
        return response.text[:500]

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Send a request, retrying connection errors and 5xx with exponential backoff."""
        last_cause = ""
        for attempt in range(self.retries + 1):
            if attempt:
                self._sleep(self.backoff_sec * 2 ** (attempt - 1))
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                last_cause = f"unreachable ({type(exc).__name__}: {exc})"
                continue
            if response.status_code >= 500:
                last_cause = f"HTTP {response.status_code}: {self._detail(response)}"
                continue
            if response.status_code >= 400:
                raise self._error(f"HTTP {response.status_code}: {self._detail(response)}")
            return response
        raise self._error(f"{last_cause} (after {self.retries + 1} attempts)")

    # -- TTSAdapter --------------------------------------------------------------------------

    def capabilities(self) -> TTSCapabilities:
        return TTSCapabilities(sample_rate=self.sample_rate, rate_control=True)

    def list_voices(self, language: str | None = None) -> list[Voice]:
        # Plain OpenAI-compatible servers have no voice listing; only the configured voice is known.
        return [Voice(id=self.voice, name=self.voice, language=language or "", model=self.model)]

    def identity(
        self, *, speed: float = 1.0, style: str | None = None, seed: int | None = None
    ) -> SynthesisIdentity:
        return SynthesisIdentity(self.id, self.model, self.voice, speed, self.sample_rate, style,
                                 seed)

    def synthesize(
        self,
        text: str,
        *,
        language: str,
        speed: float = 1.0,
        style: str | None = None,
        seed: int | None = None,
    ) -> SynthesisResult:
        body: dict = {
            "model": self.model,
            "voice": self.voice,
            "input": text,
            "response_format": "wav",
            "speed": speed,
            # Not part of the OpenAI API; Speaches needs it to label Piper WAV output correctly.
            "sample_rate": self.sample_rate,
        }
        if style:
            body["instructions"] = style
        response = self._request("POST", "/v1/audio/speech", json=body)
        if not response.content:
            raise self._error("empty audio response")
        try:
            actual_rate = wav_sample_rate(response.content)
        except ValueError as exc:
            raise self._error(str(exc)) from exc
        if actual_rate != self.sample_rate:
            raise self._error(
                f"returned {actual_rate} Hz audio but tts.sample_rate is {self.sample_rate}; "
                "set tts.sample_rate to the backend's rate"
            )
        return SynthesisResult(response.content, self.identity(speed=speed, style=style, seed=seed))

    def health(self) -> HealthStatus:
        try:
            self._client.get("/v1/models")
        except httpx.TransportError as exc:
            return HealthStatus(reachable=False, detail=f"{self.base_url} unreachable: {exc}")
        return HealthStatus(reachable=True, detail="model/voice availability not checkable")
