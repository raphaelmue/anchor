"""Decode any audio payload to 48 kHz mono float32 via ffmpeg's soxr resampler (design D2)."""

import subprocess

import numpy as np

from anchor.audio import SAMPLE_RATE
from anchor.ffmpeg import FFmpegError


def decode(data: bytes, *, ffmpeg: str = "ffmpeg", sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    args = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", "pipe:0",
        "-af", f"aresample={sample_rate}:resampler=soxr:precision=28",
        "-ac", "1", "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1",
    ]
    proc = subprocess.run(args, input=data, capture_output=True, check=False)
    if proc.returncode != 0:
        raise FFmpegError(f"decoding audio failed: {proc.stderr.decode(errors='replace')[-500:]}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()
