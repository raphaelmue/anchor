import json
import subprocess

import numpy as np
import pytest

from anchor.audio import SAMPLE_RATE
from anchor.audio.decode import decode
from anchor.audio.pacing import load_pacing
from anchor.cache import CachingSynthesizer, SegmentStore
from anchor.config import CacheSettings, Settings
from anchor.render import RenderError, render
from anchor.render.fit import fit
from anchor.render.layout import LEAD_IN_SEC, build_layout
from anchor.render.mix import mix
from anchor.render.plan import make_plan
from anchor.render.preflight import preflight
from anchor.script import SessionType, validate_script
from anchor.tts.fake import FakeTTSAdapter

SR = SAMPLE_RATE
PACING = load_pacing()


def script(segments, session_type="day", target=120):
    result = validate_script({"schema_version": "1.2", "session_type": session_type,
                              "language": "de-DE", "target_duration_sec": target,
                              "segments": segments})
    assert result.ok, result.errors
    return result.script


def speech_audio(seconds, level=0.1):
    t = np.arange(round(seconds * SR)) / SR
    return (level * np.sin(2 * np.pi * 150 * t)).astype(np.float32)


@pytest.fixture
def settings(tmp_path):
    return Settings(cache=CacheSettings(dir=tmp_path / "cache"))


def longest_zero_run(x):
    zero = np.concatenate([[False], x == 0, [False]])
    edges = np.flatnonzero(np.diff(zero.astype(int)))
    return int(np.max(edges[1::2] - edges[::2])) if edges.size else 0


# -- 6.1 preflight + plan ----------------------------------------------------------------------


def test_unknown_sound_fails_before_synthesis(tmp_path, settings):
    s = script([{"type": "speech", "text": "Hallo."}, {"type": "sound", "sound": "gong_xl"}])
    fake = FakeTTSAdapter()
    with pytest.raises(RenderError, match="gong_xl"):
        render(s, tmp_path / "o.mp3", settings=settings, adapter=fake)
    assert fake.calls == [] and fake.health_calls == 0
    assert not (tmp_path / "o.mp3").exists()


def test_unknown_ambience_fails():
    with pytest.raises(RenderError, match="rain_forest"):
        preflight(script([{"type": "ambience", "ambience": "rain_forest"}]))


def test_sleep_end_bell_rejected(tmp_path, settings):
    s = script([{"type": "speech", "text": "Schlaf gut."}, {"type": "sound", "sound": "bell_soft"},
                {"type": "pause", "seconds": 10}, {"type": "marker", "name": "end"}],
               session_type="sleep")
    fake = FakeTTSAdapter()
    with pytest.raises(RenderError, match="sleep Sessions must not end with a sound"):
        render(s, tmp_path / "o.mp3", settings=settings, adapter=fake)
    assert fake.calls == []


def test_bell_at_end_allowed_for_day():
    preflight(script([{"type": "speech", "text": "Fertig."},
                      {"type": "sound", "sound": "bell_soft"}]))


def test_plan_splits_and_keys(settings):
    s = script([{"type": "speech", "text": "Mach es dir bequem. Schließe die Augen."},
                {"type": "silent_practice", "seconds": 5, "prompt": "Übe  jetzt."},
                {"type": "speech", "text": "Mach es dir bequem."}])
    synth = CachingSynthesizer(FakeTTSAdapter(), SegmentStore(settings.cache.dir))
    plan = make_plan(s, PACING[SessionType.DAY], synth)
    assert [u.text for u in plan.units] == ["Mach es dir bequem.", "Schließe die Augen.",
                                           "Übe jetzt.", "Mach es dir bequem."]
    assert plan.units[0].key == plan.units[3].key
    assert plan.misses == 3  # the repeated sentence is synthesized once


# -- 6.2 synthesis only on misses --------------------------------------------------------------


def test_fully_cached_plan_makes_no_backend_calls(tmp_path, settings):
    s = script([{"type": "speech", "text": "Atme ruhig. Ganz ruhig."},
                {"type": "pause", "seconds": 5, "elastic": [0, 200]}])
    render(s, tmp_path / "a.mp3", settings=settings, adapter=FakeTTSAdapter())

    second = FakeTTSAdapter(healthy=False)  # would fail if contacted
    result = render(s, tmp_path / "b.mp3", settings=settings, adapter=second)
    assert second.calls == [] and second.health_calls == 0
    assert result.report["cache_hits"] == 2 and result.report["cache_misses"] == 0
    assert result.report["synthesis_time_sec"] == 0


def test_misses_require_healthy_backend(tmp_path, settings):
    s = script([{"type": "speech", "text": "Hallo."}])
    fake = FakeTTSAdapter(healthy=False)
    with pytest.raises(RenderError, match="not ready"):
        render(s, tmp_path / "o.mp3", settings=settings, adapter=fake)
    assert fake.health_calls == 1 and fake.calls == []


def test_synthesis_is_sequential_and_once_per_unit(tmp_path, settings):
    s = script([{"type": "speech", "text": "Eins. Zwei. Drei."},
                {"type": "pause", "seconds": 5, "elastic": [0, 200]}])
    fake = FakeTTSAdapter()
    render(s, tmp_path / "o.mp3", settings=settings, adapter=fake)
    assert fake.calls == ["Eins.", "Zwei.", "Drei."]


# -- 6.3 layout --------------------------------------------------------------------------------


def test_two_sentences_joined_with_sentence_gap():
    s = script([{"type": "speech", "text": "Mach es dir bequem. Schließe die Augen."}])
    layout = build_layout(s, {(0, 0): speech_audio(1), (0, 1): speech_audio(1)}, {},
                          PACING[SessionType.DAY])
    kinds = [(b.kind, b.samples) for b in layout.blocks]
    assert kinds == [("speech", SR), ("gap", round(1.1 * SR)), ("speech", SR)]


def test_silent_practice_with_prompt():
    s = script([{"type": "speech", "text": "Gut."},
                {"type": "silent_practice", "seconds": 60, "prompt": "Übe jetzt selbst."}])
    prompt = speech_audio(1.5)
    layout = build_layout(s, {(0, 0): speech_audio(1), (1, 0): prompt}, {},
                          PACING[SessionType.DAY])
    kinds = [b.kind for b in layout.blocks]
    assert kinds == ["speech", "gap", "speech", "pause"]
    pause = layout.blocks[3]
    assert pause.samples == 60 * SR

    audio = mix(layout, bed_level_lufs=-60, fade_in_sec=2)
    pos = layout.positions()
    bed = mix_bed_only(layout)
    np.testing.assert_allclose(audio[pos[2] : pos[2] + prompt.size] - bed[pos[2] : pos[2]
                               + prompt.size], prompt, atol=1e-7)
    silence = audio[pos[3] : pos[3] + pause.samples]
    rms_db = 20 * np.log10(np.sqrt(np.mean(silence**2)))
    assert rms_db < -50  # background only
    assert longest_zero_run(silence) <= 0.010 * SR


def test_pause_replaces_segment_gap():
    s = script([{"type": "speech", "text": "A."}, {"type": "pause", "seconds": 4},
                {"type": "speech", "text": "B."}])
    layout = build_layout(s, {(0, 0): speech_audio(1), (2, 0): speech_audio(1)}, {},
                          PACING[SessionType.DAY])
    assert [b.kind for b in layout.blocks] == ["speech", "pause", "speech"]


def test_marker_timestamp():
    s = script([{"type": "speech", "text": "Lang."}, {"type": "pause", "seconds": 60},
                {"type": "marker", "name": "deepening_start"}])
    speech = speech_audio(90 - 60 - LEAD_IN_SEC)
    layout = build_layout(s, {(0, 0): speech}, {}, PACING[SessionType.DAY])
    ((name, t),) = layout.markers()
    assert name == "deepening_start" and t == pytest.approx(90, abs=0.01)


def test_bell_at_start_over_background():
    from anchor.audio.beds import sound

    bell = sound("bell_soft", level_lufs=-22)
    s = script([{"type": "sound", "sound": "bell_soft"}, {"type": "speech", "text": "Hallo."}])
    layout = build_layout(s, {(1, 0): speech_audio(1)}, {"bell_soft": bell},
                          PACING[SessionType.DAY])
    assert layout.blocks[0].kind == "sound" and layout.positions()[0] == layout.lead_in
    audio = mix(layout, bed_level_lufs=-60, fade_in_sec=2)
    start = layout.lead_in
    np.testing.assert_allclose(audio[start : start + 1000] - bell[:1000],
                               mix_bed_only(layout)[start : start + 1000], atol=1e-6)


def mix_bed_only(layout, fade_in_sec=2):
    from anchor.render.layout import Layout

    empty = Layout([type(b)(b.kind, b.samples, name=b.name) for b in layout.blocks],
                   layout.lead_in, layout.tail)
    return mix(empty, bed_level_lufs=-60, fade_in_sec=fade_in_sec)


# -- 6.4 fitting -------------------------------------------------------------------------------


def fit_layout(target, pauses, speech_sec=10):
    segments = [{"type": "speech", "text": "X."}, *pauses]
    s = script(segments, target=target)
    layout = build_layout(s, {(0, 0): speech_audio(speech_sec)}, {}, PACING[SessionType.DAY])
    return layout, s


def test_fits_by_stretching():
    # unfitted: 0.5 + 10 + 20 + 30 + 3 = 63.5 s; target 15 % longer
    layout, _ = fit_layout(75, [{"type": "pause", "seconds": 20, "elastic": [10, 40]},
                                {"type": "pause", "seconds": 30, "elastic": [20, 35]}])
    before = layout.total_sec
    fitted = fit(layout, 75)
    assert before < 75 * 0.9
    assert layout.total_sec == pytest.approx(75, abs=0.01)
    # proportional to flexibility (max - seconds): 20 s vs 5 s of room
    grow = [p.fitted_sec - p.seconds for p in fitted]
    assert grow[0] / grow[1] == pytest.approx(20 / 5, rel=1e-3)


def test_fits_by_shrinking():
    layout, _ = fit_layout(50, [{"type": "pause", "seconds": 20, "elastic": [10, 40]},
                                {"type": "pause", "seconds": 30, "elastic": [20, 35]}])
    fit(layout, 50)
    assert layout.total_sec == pytest.approx(50, abs=0.01)


def test_clamped_but_within_tolerance():
    layout, _ = fit_layout(40, [{"type": "pause", "seconds": 20, "elastic": [10, 25]}])
    fit(layout, 40)  # 0.5 + 10 + 25 + 3 = 38.5 s is within 10 %
    assert layout.total_sec == pytest.approx(38.5, abs=0.01)


def test_cannot_fit_reports_range_and_target():
    # no Elastic Pauses, 30 % longer than the target
    layout, _ = fit_layout(50, [{"type": "pause", "seconds": 51.5}])
    assert layout.total_sec == pytest.approx(65, abs=0.01)
    with pytest.raises(RenderError) as exc:
        fit(layout, 50)
    msg = str(exc.value)
    assert "target duration 50 s" in msg and "65.0–65.0 s" in msg


def test_non_elastic_pauses_unchanged():
    layout, _ = fit_layout(60, [{"type": "pause", "seconds": 20},
                                {"type": "pause", "seconds": 10, "elastic": [5, 40]}])
    fit(layout, 60)
    assert layout.blocks[1].samples == 20 * SR


# -- 6.5 mixing and fades ----------------------------------------------------------------------


def test_sleep_fade_out(tmp_path, settings):
    s = script([{"type": "speech", "text": "Schlaf jetzt ein."},
                {"type": "pause", "seconds": 30}], session_type="sleep", target=62)
    fake = FakeTTSAdapter()
    synth = CachingSynthesizer(fake, SegmentStore(settings.cache.dir))
    profile = PACING[SessionType.SLEEP]
    plan = make_plan(s, profile, synth)
    unit = plan.units[0]
    audio = decode(synth.synthesize(unit.text, language="de-DE", speed=profile.speed).wav)
    layout = build_layout(s, {(0, 0): audio}, {}, profile)
    out = mix(layout, bed_level_lufs=-60, fade_in_sec=profile.fade_in_sec)

    assert layout.tail == 30 * SR
    tail = out[-layout.tail :]
    # the last Segment (the pause) ends exactly where the 30 s fade starts
    assert layout.positions()[-1] + layout.blocks[-1].samples == out.size - layout.tail
    first, last = np.sqrt(np.mean(tail[: SR] ** 2)), np.sqrt(np.mean(tail[-SR:] ** 2))
    assert last < first * 0.01
    assert abs(out[-1]) < 1e-9


def test_fades_never_attenuate_voiced_samples():
    s = script([{"type": "speech", "text": "Sofort."}], session_type="sleep")
    speech = speech_audio(2, level=0.2)
    layout = build_layout(s, {(0, 0): speech}, {}, PACING[SessionType.SLEEP])
    out = mix(layout, bed_level_lufs=-60, fade_in_sec=5)  # speech starts inside the fade-in
    pos = layout.positions()[0]
    bed = mix_bed_only(layout, fade_in_sec=5)
    np.testing.assert_allclose(out[pos : pos + speech.size] - bed[pos : pos + speech.size],
                               speech, atol=1e-7)


def test_no_digital_silence_in_long_pause():
    s = script([{"type": "speech", "text": "Ruhe."}, {"type": "pause", "seconds": 60},
                {"type": "speech", "text": "Weiter."}])
    layout = build_layout(s, {(0, 0): speech_audio(1), (2, 0): speech_audio(1)}, {},
                          PACING[SessionType.DAY])
    out = mix(layout, bed_level_lufs=-60, fade_in_sec=2)
    pos = layout.positions()[1]
    assert longest_zero_run(out[pos : pos + 60 * SR]) <= 0.010 * SR


def test_ambience_switch():
    s = script([{"type": "speech", "text": "A."}, {"type": "ambience", "ambience": "brown_noise"},
                {"type": "pause", "seconds": 20}])
    layout = build_layout(s, {(0, 0): speech_audio(1)}, {}, PACING[SessionType.DAY])
    assert [b.kind for b in layout.blocks] == ["speech", "ambience", "pause"]
    out = mix(layout, bed_level_lufs=-60, fade_in_sec=2)
    assert longest_zero_run(out[: -layout.tail]) <= 0.010 * SR


# -- 6.6 loudness + encoding -------------------------------------------------------------------


def ffprobe_codec(path):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                           "stream=codec_name,sample_rate", "-of", "json", str(path)],
                          capture_output=True, text=True, check=True).stdout


SESSION = [
    {"type": "sound", "sound": "bell_soft"},
    {"type": "speech", "text": "Mach es dir bequem. Schließe langsam die Augen."},
    {"type": "pause", "seconds": 10, "elastic": [5, 40]},
    {"type": "speech", "text": "Atme ruhig ein und wieder aus. Ganz ruhig."},
    {"type": "marker", "name": "deepening_start"},
    {"type": "silent_practice", "seconds": 15, "elastic": [10, 40], "prompt": "Übe jetzt."},
    {"type": "speech", "text": "Komm langsam zurück.", "role": "emergence"},
]


@pytest.mark.parametrize("name,fmt,codec", [("s.mp3", None, "mp3"), ("s.opus", None, "opus"),
                                            ("s.audio", "opus", "opus")])
def test_output_loudness_peak_and_format(tmp_path, settings, name, fmt, codec):
    result = render(script(SESSION, target=90), tmp_path / name, settings=settings,
                    adapter=FakeTTSAdapter(level_dbfs=-12), fmt=fmt)
    r = result.report
    assert r["integrated_loudness_lufs"] == pytest.approx(-18, abs=1.0)
    assert r["true_peak_dbtp"] <= -1.0
    assert r["loudnorm_mode"] == "linear"
    probe = json.loads(ffprobe_codec(tmp_path / name))["streams"][0]
    assert probe["codec_name"] == codec and probe["sample_rate"] == str(SR)


def test_output_duration_within_tolerance(tmp_path, settings):
    r = render(script(SESSION, target=90), tmp_path / "s.mp3", settings=settings,
               adapter=FakeTTSAdapter()).report
    assert r["output_duration_sec"] == pytest.approx(90, rel=0.10)


# -- 6.7 atomic output + report ----------------------------------------------------------------


def test_failure_mid_render_leaves_existing_output(tmp_path, settings):
    out = tmp_path / "session.mp3"
    out.write_bytes(b"previous render")
    segments = [{"type": "speech", "text": f"Satz Nummer {i}."} for i in range(1, 7)]
    with pytest.raises(RenderError, match=r"segments\[4\]"):
        render(script(segments), out, settings=settings,
               adapter=FakeTTSAdapter(fail_on_call=5))
    assert out.read_bytes() == b"previous render"
    assert not (tmp_path / "session.report.json").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cache", "session.mp3"]


def test_failure_in_fitting_writes_nothing(tmp_path, settings):
    out = tmp_path / "session.mp3"
    with pytest.raises(RenderError, match="achievable range"):
        render(script([{"type": "speech", "text": "Kurz."}], target=600), out,
               settings=settings, adapter=FakeTTSAdapter())
    assert not out.exists()


REPORT_FIELDS = {
    "output_duration_sec", "target_duration_sec", "integrated_loudness_lufs", "true_peak_dbtp",
    "speech_units", "cache_hits", "cache_misses", "synthesis_time_sec", "render_time_sec",
    "elastic_pauses", "markers",
}


def test_report_contains_every_field(tmp_path, settings):
    out = tmp_path / "session.mp3"
    result = render(script(SESSION, target=90), out, settings=settings,
                    adapter=FakeTTSAdapter())
    path = tmp_path / "session.report.json"
    assert result.report_path == path
    report = json.loads(path.read_text())
    assert set(report) >= REPORT_FIELDS
    assert report["speech_units"] == 6
    assert report["cache_misses"] == 6 and report["cache_hits"] == 0
    assert [p["segment_index"] for p in report["elastic_pauses"]] == [2, 5]
    assert report["markers"][0]["name"] == "deepening_start"
    assert report["markers"][0]["time_sec"] > 0


def test_no_cache_resynthesizes(tmp_path, settings):
    s = script(SESSION, target=90)
    render(s, tmp_path / "a.mp3", settings=settings, adapter=FakeTTSAdapter())
    fake = FakeTTSAdapter()
    r = render(s, tmp_path / "b.mp3", settings=settings, adapter=fake, no_cache=True).report
    assert len(fake.calls) == 6 and r["cache_misses"] == 6 and r["cache_bypass"]


def test_sentence_gap_change_uses_cached_audio(tmp_path, settings):
    s = script(SESSION, target=90)
    render(s, tmp_path / "a.mp3", settings=settings, adapter=FakeTTSAdapter())
    pacing = dict(PACING)
    pacing[SessionType.DAY] = PACING[SessionType.DAY].model_copy(update={"sentence_gap_sec": 2})
    fake = FakeTTSAdapter()
    r = render(s, tmp_path / "b.mp3", settings=settings, adapter=fake, pacing=pacing).report
    assert fake.calls == [] and r["pacing"]["sentence_gap_sec"] == 2


def test_peaky_speech_stays_linear_and_aligned(tmp_path):
    from anchor.audio.beds import bed
    from anchor.render.output import finalize

    # Speech-like signal over a quiet bed, plus one isolated peak far above the ceiling.
    audio = bed("room_tone", 30 * SR, level_lufs=-60)
    t = np.arange(10 * SR) / SR
    speech = 0.05 * np.sin(2 * np.pi * 140 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
    audio[5 * SR : 15 * SR] += speech.astype(np.float32)
    click_at = 12 * SR
    audio[click_at : click_at + 48] += 0.9  # isolated plosive-like peak far above the ceiling

    out = tmp_path / "peaky.opus"
    result = finalize(audio, out, fmt="opus", bitrate="96k")
    assert result.normalization_type == "linear"
    assert result.peak_reduction_db > 3
    assert result.true_peak_dbtp <= -1.0
    assert result.integrated_lufs == pytest.approx(-18, abs=1.0)

    decoded = decode(out.read_bytes())
    assert abs(decoded.size - audio.size) < SR * 0.02
    # The limiter is latency-compensated: the peak stays where it was.
    assert abs(int(np.argmax(np.abs(decoded))) - click_at) < SR * 0.005
    # Linear: the bed gets exactly the same gain as unlimited speech (dynamic mode would lift
    # the quiet bed relative to the speech).
    rms_db = lambda x: 20 * np.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)))  # noqa: E731
    speech_gain = rms_db(decoded[6 * SR : 10 * SR]) - rms_db(audio[6 * SR : 10 * SR])
    bed_gain = rms_db(decoded[20 * SR : 28 * SR]) - rms_db(audio[20 * SR : 28 * SR])
    assert bed_gain == pytest.approx(speech_gain, abs=1.0)
