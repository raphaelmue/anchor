"""Deterministic stand-in for a TTS Backend (design D13).

Produces "speech" as syllable-like tone bursts with known leading/trailing silence and level,
so trimming, loudness, fitting and caching can be tested without a running backend.
"""

import hashlib
import io
from dataclasses import dataclass, field

import numpy as np
import soundfile as sf

from anchor.tts.base import (
    HealthStatus,
    SynthesisIdentity,
    SynthesisResult,
    TTSCapabilities,
    TTSError,
    Voice,
)


@dataclass
class FakeTTSAdapter:
    id: str = "fake"
    model: str = "fake-model-1"
    voice: str = "fake-voice"
    sample_rate: int = 22050
    lead_silence_sec: float = 0.1
    trail_silence_sec: float = 0.2
    level_dbfs: float = -20.0
    sec_per_char: float = 0.06
    # 1-based synthesize call number that raises TTSError; None = never fail.
    fail_on_call: int | None = None
    healthy: bool = True
    calls: list[str] = field(default_factory=list)
    health_calls: int = 0

    def capabilities(self) -> TTSCapabilities:
        return TTSCapabilities(languages=("de-DE",), sample_rate=self.sample_rate)

    def list_voices(self, language: str | None = None) -> list[Voice]:
        voice = Voice(id=self.voice, name=self.voice, language="de-DE", model=self.model)
        return [voice] if language in (None, "de-DE", "de") else []

    def identity(
        self, *, speed: float = 1.0, style: str | None = None, seed: int | None = None
    ) -> SynthesisIdentity:
        return SynthesisIdentity(self.id, self.model, self.voice, speed, self.sample_rate, style,
                                 seed)

    def health(self) -> HealthStatus:
        self.health_calls += 1
        if not self.healthy:
            return HealthStatus(reachable=False, detail="fake backend is down")
        return HealthStatus(reachable=True, model_available=True, voice_available=True)

    def voiced_duration(self, text: str, speed: float = 1.0) -> float:
        return max(0.2, len(text.strip()) * self.sec_per_char / speed)

    def synthesize(
        self,
        text: str,
        *,
        language: str,
        speed: float = 1.0,
        style: str | None = None,
        seed: int | None = None,
    ) -> SynthesisResult:
        self.calls.append(text)
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            raise TTSError(f"TTS backend {self.id}: simulated failure on call {len(self.calls)}")
        audio = self.render(text, speed)
        buf = io.BytesIO()
        sf.write(buf, audio, self.sample_rate, format="WAV", subtype="PCM_16")
        return SynthesisResult(buf.getvalue(), self.identity(speed=speed, style=style, seed=seed))

    def render(self, text: str, speed: float = 1.0) -> np.ndarray:
        sr = self.sample_rate
        rng = np.random.default_rng(int.from_bytes(hashlib.sha256(text.encode()).digest()[:8]))
        n_voiced = int(self.voiced_duration(text, speed) * sr)
        t = np.arange(n_voiced) / sr
        f0 = rng.uniform(110, 160)
        tone = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in (1, 2, 3))
        # Syllable envelope (~4 Hz) that never fully closes, so the voiced part is continuous.
        syllable = 0.6 + 0.4 * np.abs(np.sin(np.pi * 4 * t + rng.uniform(0, np.pi)))
        voiced = tone * syllable
        voiced *= 10 ** (self.level_dbfs / 20) / np.sqrt(np.mean(voiced**2))
        lead = np.zeros(int(self.lead_silence_sec * sr))
        trail = np.zeros(int(self.trail_silence_sec * sr))
        return np.concatenate([lead, voiced, trail]).astype(np.float32)
