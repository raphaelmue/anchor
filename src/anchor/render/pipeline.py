"""The render pipeline (design D3):

parse+validate -> preflight -> plan -> synthesize misses -> prepare units -> layout (unfitted)
  -> fit elastic -> mix (bed + speech + sounds) -> fades -> final loudness -> encode to temp
  -> atomic rename -> report
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from anchor.audio import SAMPLE_RATE
from anchor.audio.beds import SOUND_LEVEL_LU, sound
from anchor.audio.decode import decode
from anchor.audio.loudness import normalize
from anchor.audio.pacing import PacingProfile, load_pacing
from anchor.audio.trim import trim
from anchor.cache import CachingSynthesizer, SegmentStore
from anchor.config import Settings
from anchor.ffmpeg import check_ffmpeg
from anchor.render.errors import RenderError
from anchor.render.fit import fit
from anchor.render.layout import Layout, build_layout
from anchor.render.mix import mix
from anchor.render.output import finalize, report_path, resolve_format, write_json_atomic
from anchor.render.plan import Plan, make_plan
from anchor.render.preflight import preflight
from anchor.script import Script, SoundSegment
from anchor.tts import TTSAdapter, TTSError


@dataclass
class RenderResult:
    output: Path
    report_path: Path
    report: dict


def _synthesize(script: Script, plan: Plan, synth: CachingSynthesizer,
                ffmpeg: str) -> dict[tuple[int, int], np.ndarray]:
    """Fetch every planned unit (cache hit or sequential synthesis) and decode it."""
    raw: dict[tuple[int, int], np.ndarray] = {}
    for unit in plan.units:
        try:
            result = synth.synthesize(unit.text, language=script.language, speed=plan.speed,
                                      style=unit.style)
        except TTSError as exc:
            raise RenderError(
                f"synthesis failed for segments[{unit.segment_index}] "
                f"sentence {unit.sentence_index + 1} ({unit.text[:40]!r}): {exc}") from exc
        raw[(unit.segment_index, unit.sentence_index)] = decode(result.wav, ffmpeg=ffmpeg)
    return raw


def _prepare(raw: dict[tuple[int, int], np.ndarray],
             speech_lufs: float) -> dict[tuple[int, int], np.ndarray]:
    return {k: normalize(trim(audio), speech_lufs) for k, audio in raw.items()}


def render(
    script: Script,
    output: Path,
    *,
    settings: Settings,
    adapter: TTSAdapter,
    no_cache: bool = False,
    fmt: str | None = None,
    pacing: dict | None = None,
    script_path: Path | None = None,
) -> RenderResult:
    started = time.perf_counter()
    audio_cfg = settings.audio
    output_format = resolve_format(output, fmt)

    # -- preflight: everything that can fail without touching the backend
    check_ffmpeg(audio_cfg.ffmpeg)
    preflight(script)
    profiles = pacing or load_pacing(audio_cfg.pacing_file)
    profile: PacingProfile = profiles[script.session_type]

    # -- plan; the backend is only contacted if something is missing from the cache
    synth = CachingSynthesizer(adapter, SegmentStore.from_settings(settings.cache),
                               bypass=no_cache)
    plan = make_plan(script, profile, synth)
    if plan.misses:
        status = adapter.health()
        if not status.ok:
            raise RenderError(
                f"TTS backend {adapter.id} not ready ({plan.misses} unit(s) to synthesize): "
                f"{status.detail or 'unreachable'}")

    raw = _synthesize(script, plan, synth, audio_cfg.ffmpeg)
    speech = _prepare(raw, audio_cfg.speech_lufs)
    sound_level = audio_cfg.speech_lufs + SOUND_LEVEL_LU
    sounds = {s.sound: sound(s.sound, level_lufs=sound_level)
              for s in script.segments if isinstance(s, SoundSegment)}

    # -- layout, fit, mix
    layout: Layout = build_layout(script, speech, sounds, profile)
    unfitted_sec = layout.total_sec
    fitted = fit(layout, script.target_duration_sec)
    audio = mix(layout,
                bed_level_lufs=audio_cfg.loudness_target_lufs + audio_cfg.bed_level_lu,
                fade_in_sec=profile.fade_in_sec)

    # -- final loudness + encode (atomic), then the report
    bitrate = audio_cfg.opus_bitrate if output_format == "opus" else audio_cfg.mp3_bitrate
    loudness = finalize(audio, output, fmt=output_format,
                        target_lufs=audio_cfg.loudness_target_lufs,
                        true_peak_dbtp=audio_cfg.true_peak_dbtp, bitrate=bitrate,
                        ffmpeg=audio_cfg.ffmpeg)

    identity = adapter.identity(speed=profile.speed)
    speech_sec = sum(a.size for a in speech.values()) / SAMPLE_RATE
    report = {
        "output": str(output),
        "format": output_format,
        "script": str(script_path) if script_path else None,
        "session_type": script.session_type.value,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "output_duration_sec": round(audio.size / SAMPLE_RATE, 3),
        "target_duration_sec": script.target_duration_sec,
        "unfitted_duration_sec": round(unfitted_sec, 3),
        "integrated_loudness_lufs": loudness.integrated_lufs,
        "true_peak_dbtp": loudness.true_peak_dbtp,
        "loudnorm_mode": loudness.normalization_type,
        "loudnorm_dynamic_fallback": loudness.normalization_type != "linear",
        "peak_limiting_db": loudness.peak_reduction_db,
        "speech_units": len(plan.units),
        "speech_duration_sec": round(speech_sec, 3),
        "cache_hits": synth.stats.hits,
        "cache_misses": synth.stats.misses,
        "cache_bypass": no_cache,
        "synthesis_time_sec": round(synth.stats.synthesis_sec, 3),
        "render_time_sec": round(time.perf_counter() - started, 3),
        "elastic_pauses": [
            {"segment_index": p.segment_index, "seconds": p.seconds,
             "fitted_sec": round(p.fitted_sec, 3), "elastic": list(p.elastic)}
            for p in fitted
        ],
        "markers": [{"name": name, "time_sec": round(t, 3)} for name, t in layout.markers()],
        "tts": {"backend_id": identity.backend_id, "model": identity.model,
                "voice": identity.voice, "speed": identity.speed,
                "sample_rate": identity.sample_rate},
        "pacing": profile.model_dump(),
    }
    path = report_path(output)
    write_json_atomic(path, report)
    return RenderResult(output, path, report)
