"""Content-addressed Segment Cache for rendered speech."""

from anchor.cache.caching import CacheStats, CachingSynthesizer
from anchor.cache.key import TEXT_NORM_VERSION, cache_key, normalize_text
from anchor.cache.store import SegmentStore

__all__ = [
    "TEXT_NORM_VERSION",
    "CacheStats",
    "CachingSynthesizer",
    "SegmentStore",
    "cache_key",
    "normalize_text",
]
