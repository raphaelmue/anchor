"""Filesystem storage for cached speech units (design D10).

Layout: `<dir>/<key[:2]>/<key>.wav` plus `<key>.json` with the key fields. Both are written to a
temp file and moved into place with `os.replace`; the `.json` is written last, so an entry is
valid only once its `.json` exists. Leftover temp files and orphaned `.wav` files are misses.
"""

import json
import os
import tempfile
from pathlib import Path

from anchor.config import CacheSettings


class SegmentStore:
    def __init__(self, directory: Path) -> None:
        self.dir = Path(directory)

    @classmethod
    def from_settings(cls, settings: CacheSettings) -> "SegmentStore":
        return cls(settings.dir)

    def _paths(self, key: str) -> tuple[Path, Path]:
        shard = self.dir / key[:2]
        return shard / f"{key}.wav", shard / f"{key}.json"

    def contains(self, key: str) -> bool:
        wav, meta = self._paths(key)
        return meta.is_file() and wav.is_file()

    def get(self, key: str) -> bytes | None:
        wav, meta = self._paths(key)
        if not meta.is_file():
            return None
        try:
            return wav.read_bytes()
        except FileNotFoundError:
            return None

    def put(self, key: str, wav_bytes: bytes, fields: dict) -> None:
        wav, meta = self._paths(key)
        wav.parent.mkdir(parents=True, exist_ok=True)
        # Invalidate first, so a crash between the two writes never pairs new audio with old meta.
        meta.unlink(missing_ok=True)
        _atomic_write(wav, wav_bytes)
        _atomic_write(meta, json.dumps({"key": key, **fields}, ensure_ascii=False,
                                       indent=2).encode("utf-8"))


def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
