"""Final loudness (ffmpeg loudnorm, two-pass linear), encoding and atomic output (design D5)."""

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf

from anchor.audio import SAMPLE_RATE
from anchor.ffmpeg import FFmpegError

OutputFormat = Literal["mp3", "opus"]

# Limiter ceiling below the true-peak target, absorbing loudnorm's residual gain and encoder
# overshoot (measured: MP3 ≈ 0.3 dB, Opus ≈ 0.8 dB on the example renders).
LIMITER_MARGIN_DB = {"mp3": 0.5, "opus": 1.0}
LIMITER_PASSES = 3

_CODECS = {"mp3": ("libmp3lame", "mp3"), "opus": ("libopus", "ogg")}


def resolve_format(output: Path, explicit: str | None) -> OutputFormat:
    """--format wins; otherwise the extension decides (.opus -> Opus), MP3 by default."""
    if explicit:
        if explicit not in _CODECS:
            raise ValueError(f"unsupported format {explicit!r}; use mp3 or opus")
        return explicit  # type: ignore[return-value]
    return "opus" if output.suffix.lower() in (".opus", ".ogg") else "mp3"


@dataclass(frozen=True)
class LoudnessResult:
    integrated_lufs: float
    true_peak_dbtp: float
    normalization_type: str  # "linear" or "dynamic" (loudnorm fell back)
    peak_reduction_db: float = 0.0  # largest gain reduction applied by the peak limiter


def _ffmpeg(args: list[str]) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise FFmpegError(f"ffmpeg failed: {proc.stderr.strip()[-800:]}")
    return proc.stderr


def _loudnorm_json(stderr: str) -> dict:
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.S)
    if not match:
        raise FFmpegError("could not read loudnorm measurement from ffmpeg output")
    return json.loads(match.group(0))


def measure_file(path: Path, ffmpeg: str = "ffmpeg") -> tuple[float, float]:
    """Integrated loudness (LUFS) and true peak (dBTP) of an encoded file (EBU R128)."""
    stderr = _ffmpeg([ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
                      "-af", "ebur128=peak=true", "-f", "null", "-"])
    summary = stderr[stderr.rfind("Summary:"):]
    integrated = float(re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary).group(1))
    peak = float(re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary).group(1))
    return integrated, peak


def finalize(
    audio: np.ndarray,
    output: Path,
    *,
    fmt: OutputFormat,
    target_lufs: float = -18.0,
    true_peak_dbtp: float = -1.0,
    bitrate: str = "128k",
    ffmpeg: str = "ffmpeg",
    sample_rate: int = SAMPLE_RATE,
) -> LoudnessResult:
    """Normalize and encode `audio` to `output` atomically.

    The encoded file goes to a temp file next to `output` and is moved into place only on
    success, so a failed render never leaves a partial file or overwrites an existing one.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    codec, muxer = _CODECS[fmt]
    with tempfile.TemporaryDirectory(prefix="anchor-render-") as tmp:
        mix_path = Path(tmp) / "mix.wav"
        sf.write(mix_path, audio, sample_rate, subtype="FLOAT")

        base = f"loudnorm=I={target_lufs}:TP={true_peak_dbtp}"
        measure = f"{base}:LRA=50:print_format=json"
        initial = _loudnorm_json(_ffmpeg([
            ffmpeg, "-hide_banner", "-nostats", "-i", str(mix_path),
            "-af", measure, "-f", "null", "-"]))

        # Apply the loudness gain, then limit true peaks below the ceiling. TTS speech peaks
        # 15–19 dB above its loudness, so without this loudnorm falls back to dynamic mode and
        # lifts the Noise Floor in pauses. Limiting runs 4x oversampled (≈ true peak) and
        # latency-compensated, so timing is unchanged; quiet audio is never touched.
        # Limiting lowers loudness a little, so the gain is refined until the remaining linear
        # gain no longer pushes peaks over the true-peak target.
        gain_db = target_lufs - float(initial["input_i"])
        ceiling_db = true_peak_dbtp - LIMITER_MARGIN_DB[fmt]
        limited_path = Path(tmp) / "limited.wav"
        for _ in range(LIMITER_PASSES):
            _ffmpeg([
                ffmpeg, "-hide_banner", "-nostats", "-y", "-i", str(mix_path), "-af",
                f"volume={gain_db:.3f}dB,aresample={4 * sample_rate}:resampler=soxr,"
                f"alimiter=limit={10 ** (ceiling_db / 20):.5f}:attack=1:release=60"
                f":level=false:latency=true,aresample={sample_rate}:resampler=soxr",
                "-c:a", "pcm_f32le", str(limited_path)])
            first = _loudnorm_json(_ffmpeg([
                ffmpeg, "-hide_banner", "-nostats", "-i", str(limited_path),
                "-af", measure, "-f", "null", "-"]))
            residual_db = target_lufs - float(first["input_i"])
            if float(first["input_tp"]) + residual_db <= true_peak_dbtp - 0.1:
                break
            gain_db += residual_db
        peak_reduction_db = max(0.0, float(initial["input_tp"]) + gain_db - ceiling_db)
        # LRA target at least the measured range, so loudnorm is not forced into dynamic mode.
        lra = min(50.0, max(7.0, float(first["input_lra"]) + 1.0))
        second_filter = (
            f"{base}:LRA={lra}:measured_I={first['input_i']}:measured_TP={first['input_tp']}"
            f":measured_LRA={first['input_lra']}:measured_thresh={first['input_thresh']}"
            f":offset={first['target_offset']}:linear=true:print_format=json"
            # loudnorm upsamples to 192 kHz internally; return to the single internal rate.
            f",aresample={sample_rate}:resampler=soxr"
        )
        fd, tmp_out = tempfile.mkstemp(dir=output.parent, prefix=f".{output.name}.",
                                       suffix=".tmp")
        os.close(fd)
        try:
            second = _loudnorm_json(_ffmpeg([
                ffmpeg, "-hide_banner", "-nostats", "-y", "-i", str(limited_path),
                "-af", second_filter, "-ar", str(sample_rate), "-ac", "1",
                "-c:a", codec, "-b:a", bitrate, "-f", muxer, tmp_out]))
            integrated, peak = measure_file(Path(tmp_out), ffmpeg)
            os.replace(tmp_out, output)
        except BaseException:
            Path(tmp_out).unlink(missing_ok=True)
            raise
    return LoudnessResult(integrated, peak, second.get("normalization_type", "unknown"),
                          round(peak_reduction_db, 2))


def write_json_atomic(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def report_path(output: Path) -> Path:
    """`session.mp3` -> `session.report.json` next to it."""
    return output.with_name(f"{output.stem}.report.json")
