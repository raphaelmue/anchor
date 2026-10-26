"""ffmpeg discovery and capability check.

The pipeline needs ffmpeg >= 6 with libmp3lame, libopus and the soxr resampler
(design D2). The check runs once before rendering and fails with a message that
says exactly what is missing.
"""

import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

MIN_MAJOR_VERSION = 6
REQUIRED_ENCODERS = ("libmp3lame", "libopus")

Runner = Callable[[list[str]], str]


class FFmpegError(RuntimeError):
    """ffmpeg is missing, too old, lacks a capability, or a call failed."""


def _run(args: list[str]) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise FFmpegError(f"`{' '.join(args)}` failed: {proc.stderr.strip()[-500:]}")
    return proc.stdout


@dataclass(frozen=True)
class FFmpegInfo:
    binary: str
    version: str


def _parse_major(version_output: str) -> tuple[str, int | None]:
    match = re.search(r"ffmpeg version (\S+)", version_output)
    if not match:
        raise FFmpegError("could not read ffmpeg version from `ffmpeg -version`")
    version = match.group(1)
    # Git snapshot builds ("N-12345-g…") are newer than any release.
    if version.startswith("N-"):
        return version, None
    major = re.match(r"n?(\d+)", version)
    if not major:
        raise FFmpegError(f"unrecognized ffmpeg version {version!r}")
    return version, int(major.group(1))


def check_ffmpeg(binary: str = "ffmpeg", runner: Runner = _run) -> FFmpegInfo:
    """Verify the ffmpeg build; raise FFmpegError listing every missing capability."""
    if runner is _run and shutil.which(binary) is None:
        raise FFmpegError(f"ffmpeg not found ({binary!r}); install ffmpeg >= {MIN_MAJOR_VERSION}")

    version_output = runner([binary, "-hide_banner", "-version"])
    version, major = _parse_major(version_output)
    encoders_output = runner([binary, "-hide_banner", "-encoders"])

    problems: list[str] = []
    if major is not None and major < MIN_MAJOR_VERSION:
        problems.append(f"version {version} is older than {MIN_MAJOR_VERSION}")
    encoder_names = {
        parts[1] for line in encoders_output.splitlines() if len(parts := line.split()) >= 2
    }
    problems += [f"encoder {enc} missing" for enc in REQUIRED_ENCODERS if enc not in encoder_names]
    if "--enable-libsoxr" not in version_output:
        problems.append("soxr resampler missing (build without --enable-libsoxr)")

    if problems:
        raise FFmpegError(
            f"unsuitable ffmpeg build ({binary}): "
            + "; ".join(problems)
            + f". Required: ffmpeg >= {MIN_MAJOR_VERSION} with libmp3lame, libopus and libsoxr."
        )
    return FFmpegInfo(binary=binary, version=version)
