"""TTS Adapter protocol and result types (docs/spec.md §10.1, design D9)."""

import io
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import soundfile as sf


class TTSError(RuntimeError):
    """Synthesis or backend communication failed. The message names backend and cause."""


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    language: str
    model: str | None = None


@dataclass(frozen=True)
class TTSCapabilities:
    languages: tuple[str, ...] = ()
    rate_control: bool = True
    style_instructions: bool = False
    sample_rate: int | None = None
    max_chars: int | None = None
    engine_version: str | None = None


@dataclass(frozen=True)
class HealthStatus:
    reachable: bool
    model_available: bool | None = None
    voice_available: bool | None = None
    detail: str = ""
    authorized: bool = True

    @property
    def ok(self) -> bool:
        return (
            self.reachable
            and self.authorized
            and self.model_available is not False
            and self.voice_available is not False
        )


@dataclass(frozen=True)
class SynthesisIdentity:
    """Everything that determines a synthesis output; the Segment Cache key is built from it."""

    backend_id: str
    model: str
    voice: str
    speed: float
    sample_rate: int
    style: str | None = None
    seed: int | None = None


@dataclass(frozen=True)
class SynthesisResult:
    """Raw backend audio (a complete WAV file) plus the identity that produced it."""

    wav: bytes = field(repr=False)
    identity: SynthesisIdentity

    @property
    def sample_rate(self) -> int:
        return self.identity.sample_rate


@runtime_checkable
class TTSAdapter(Protocol):
    id: str

    def capabilities(self) -> TTSCapabilities: ...

    def list_voices(self, language: str | None = None) -> list[Voice]: ...

    def identity(
        self, *, speed: float = 1.0, style: str | None = None, seed: int | None = None
    ) -> SynthesisIdentity:
        """The identity a synthesize call with these options would report (for cache lookup)."""
        ...

    def synthesize(
        self,
        text: str,
        *,
        language: str,
        speed: float = 1.0,
        style: str | None = None,
        seed: int | None = None,
    ) -> SynthesisResult: ...

    def health(self) -> HealthStatus: ...


def wav_sample_rate(wav: bytes) -> int:
    """Sample rate of a WAV payload; raises ValueError if it is not decodable audio."""
    try:
        info = sf.info(io.BytesIO(wav))
    except Exception as exc:
        raise ValueError(f"undecodable audio: {exc}") from exc
    if info.frames == 0:
        raise ValueError("audio contains no samples")
    return info.samplerate
