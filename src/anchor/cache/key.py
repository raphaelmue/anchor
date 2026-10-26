"""Text normalization and the content-addressed Segment Cache key (spec §9.2, design D10)."""

import hashlib
import json
import re
import unicodedata

from anchor.tts.base import SynthesisIdentity

TEXT_NORM_VERSION = "1"

_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Unicode NFC, whitespace runs collapsed to one space, trimmed (text_norm_version 1)."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()


def key_fields(normalized_text: str, identity: SynthesisIdentity) -> dict:
    return {
        "text": normalized_text,
        "text_norm_version": TEXT_NORM_VERSION,
        "backend_id": identity.backend_id,
        "model": identity.model,
        "voice": identity.voice,
        "speed": identity.speed,
        "style": identity.style,
        "seed": identity.seed,
        "sample_rate": identity.sample_rate,
    }


def cache_key(normalized_text: str, identity: SynthesisIdentity) -> str:
    canonical = json.dumps(
        key_fields(normalized_text, identity),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
