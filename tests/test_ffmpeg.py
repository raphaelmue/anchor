import pytest

from anchor.ffmpeg import FFmpegError, check_ffmpeg

GOOD_VERSION = """ffmpeg version 6.1.1 Copyright (c) 2000-2023 the FFmpeg developers
configuration: --enable-gpl --enable-libmp3lame --enable-libopus --enable-libsoxr
"""
GOOD_ENCODERS = """Encoders:
 ------
 A....D libmp3lame           libmp3lame MP3 (MPEG audio layer 3) (codec mp3)
 A....D libopus              libopus Opus (codec opus)
 A....D pcm_s16le            PCM signed 16-bit little-endian
"""
OLD_VERSION = """ffmpeg version 4.4.2-0ubuntu0.22.04.1 Copyright (c) 2000-2021
configuration: --enable-gpl --enable-libmp3lame
"""
OLD_ENCODERS = """Encoders:
 A....D libmp3lame           libmp3lame MP3 (MPEG audio layer 3) (codec mp3)
 A....D pcm_s16le            PCM signed 16-bit little-endian
"""


def fake_runner(version: str, encoders: str):
    def run(args: list[str]) -> str:
        return version if "-version" in args else encoders

    return run


def test_passing_build():
    info = check_ffmpeg(runner=fake_runner(GOOD_VERSION, GOOD_ENCODERS))
    assert info.version == "6.1.1"


def test_git_snapshot_build_passes():
    version = GOOD_VERSION.replace("6.1.1", "N-112233-gabcdef")
    check_ffmpeg(runner=fake_runner(version, GOOD_ENCODERS))


def test_failing_build_lists_every_problem():
    with pytest.raises(FFmpegError) as exc:
        check_ffmpeg(runner=fake_runner(OLD_VERSION, OLD_ENCODERS))
    message = str(exc.value)
    assert "older than 6" in message
    assert "libopus missing" in message
    assert "soxr" in message
    assert "libmp3lame missing" not in message
