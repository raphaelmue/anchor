"""Speech synthesis through pluggable TTS Adapters."""

from anchor.tts.base import (
    HealthStatus,
    SynthesisIdentity,
    SynthesisResult,
    TTSAdapter,
    TTSCapabilities,
    TTSError,
    Voice,
)

__all__ = [
    "HealthStatus",
    "SynthesisIdentity",
    "SynthesisResult",
    "TTSAdapter",
    "TTSCapabilities",
    "TTSError",
    "Voice",
]
