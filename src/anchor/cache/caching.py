"""Caching wrapper around any TTS Adapter: hits skip the backend, misses are stored raw."""

import time
from dataclasses import dataclass

from anchor.cache.key import cache_key, key_fields, normalize_text
from anchor.cache.store import SegmentStore
from anchor.tts.base import SynthesisResult, TTSAdapter


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    synthesis_sec: float = 0.0  # wall time spent in backend calls


class CachingSynthesizer:
    def __init__(self, adapter: TTSAdapter, store: SegmentStore, *, bypass: bool = False) -> None:
        self.adapter = adapter
        self.store = store
        self.bypass = bypass
        self.stats = CacheStats()

    def key_for(self, text: str, *, speed: float = 1.0, style: str | None = None,
                seed: int | None = None) -> str:
        identity = self.adapter.identity(speed=speed, style=style, seed=seed)
        return cache_key(normalize_text(text), identity)

    def is_cached(self, key: str) -> bool:
        return not self.bypass and self.store.contains(key)

    def synthesize(self, text: str, *, language: str, speed: float = 1.0,
                   style: str | None = None, seed: int | None = None) -> SynthesisResult:
        normalized = normalize_text(text)
        identity = self.adapter.identity(speed=speed, style=style, seed=seed)
        key = cache_key(normalized, identity)
        if not self.bypass and (wav := self.store.get(key)) is not None:
            self.stats.hits += 1
            return SynthesisResult(wav, identity)

        self.stats.misses += 1
        started = time.perf_counter()
        try:
            result = self.adapter.synthesize(normalized, language=language, speed=speed,
                                             style=style, seed=seed)
        finally:
            self.stats.synthesis_sec += time.perf_counter() - started
        # Store under the identity the backend reported, so a mismatch can never alias entries.
        stored_key = cache_key(normalized, result.identity)
        self.store.put(stored_key, result.wav, key_fields(normalized, result.identity))
        return result
