# Design

## Context

Greenfield: the repo contains only `docs/spec.md` (v0.4) and OpenSpec scaffolding. See proposal.md – Why. Constraints from the product spec that shape this design:

- CPU-only home server (≥ 4 cores, 8 GB RAM); the TTS Engine is the expensive part, so avoiding synthesis matters more than mixer speed.
- TTS runs in a separate container (license boundary: Piper engine is GPL-3.0) behind an OpenAI-compatible HTTP API.
- The same Script format, cache and mixer will later run inside the M5 worker, so M1 code must be a library first and a CLI second.
- Audio assembly rules (spec §9.1) and the Segment Cache key (spec §9.2) are fixed product decisions; this design decides how to realize them.

## Goals / Non-Goals

**Goals:**
- A library (`anchor.script`, `anchor.tts`, `anchor.cache`, `anchor.audio`) with a thin CLI on top, reusable unchanged by the M5 worker.
- Deterministic, testable mixing: everything except synthesis is testable without a running TTS Backend.
- A render report good enough to benchmark NFR-1/2 on the target hardware.

**Non-Goals:**
- Parallel synthesis, job queues, progress streaming (M5).
- Speech Rate calibration and pre-render duration estimation (M2/M7; M1 measures real durations after synthesis).
- Formula resolution, Lessons, content packs (M3).
- A SQLite index for the cache (filesystem layout is sufficient until the worker needs cache statistics).

## Decisions

### D1 — Project layout and tooling
`src/anchor/` package, `pyproject.toml` managed with **uv**, Python 3.12, **typer** CLI (`anchor render`, `anchor tts health`, `anchor tts voices`), **pydantic v2** models, **pydantic-settings** for config, **pytest**.
*Alternatives:* Poetry (slower, no added value here); click directly (typer is click with type hints, matching the Pydantic style).

### D2 — Mix on a NumPy timeline, use ffmpeg only at the edges
All units are decoded and resampled to **48 kHz mono float32** via ffmpeg (soxr resampler), then placed on a NumPy timeline; ffmpeg is used again only for final loudness and encoding.
*Why:* the rules in §9.1 (trim to margin, never fade voiced audio, continuous bed, elastic fitting, marker timestamps) need exact sample positions. A single ffmpeg filtergraph could do it but is hard to reason about, hard to unit-test and hard to report on.
*Why 48 kHz mono:* Opus-native, enough headroom for bell/ambience; speech is mono anyway.
*Alternatives:* pure ffmpeg filtergraph (rejected above); pydub (thin wrapper, same ffmpeg dependency, less control).

### D3 — Pipeline stages
```
parse+validate -> preflight -> plan -> synthesize misses -> prepare units
   -> layout (unfitted) -> fit elastic -> mix (bed + speech + sounds) -> fades
   -> final loudness -> encode to temp -> atomic rename -> report
```
- **Preflight** resolves sounds/ambience names and checks the sleep end-sound rule before anything else. The backend health check runs only if `plan` finds at least one cache miss (a fully cached render needs no backend).
- **Plan** splits speech into sentences, normalizes text, computes cache keys. Sentence splitting uses a regex on `.`, `!`, `?`, `…` followed by whitespace, with a protected list of German abbreviations (`z. B.`, `usw.`, `bzw.`, `d. h.`, …). Script text is hand- or LLM-written and short (≤ 300 chars per Segment), so a full NLP splitter is not justified.
- **Synthesize misses** runs sequentially: a CPU-bound backend gains nothing from parallel requests and may run out of memory.

### D4 — Silence trimming
Energy-based: 10 ms RMS windows, threshold −45 dB relative to the unit's peak; keep a fixed **30 ms margin** on both sides. A 5 ms de-click ramp is applied only inside that margin, so voiced audio is never faded (spec requirement "Speech is never cut or crossfaded").
*Alternative:* ffmpeg `silenceremove` — absolute thresholds behave badly across voices with different levels.

### D5 — Loudness
- **Per unit:** loudness-normalize each speech unit with **pyloudnorm** (BS.1770) to the speech target. Units shorter than 400 ms (one BS.1770 block) are measured on a zero-padded copy and gain-matched by RMS.
- **Peak limiting:** before the final pass, the mix gets the measured loudness gain and then a true-peak limiter (ffmpeg `alimiter`, 4× oversampled, 1 ms attack, 60 ms release, latency-compensated) with its ceiling at TP − 0.5 dB (MP3) or TP − 1.0 dB (Opus, larger encoder overshoot). Limiting lowers loudness slightly, so gain plus limiter is repeated (at most 3 times) until the remaining linear gain keeps peaks under TP. The largest gain reduction is reported as `peak_limiting_db`.
  *Why:* Piper speech normalized to −18 LUFS peaks at a median −2.4 dBTP, and about 10 % of units exceed −1 dBTP (up to +1.1). Without limiting, loudnorm fell back to dynamic mode in every example render, which lifted the Noise Floor in long pauses by about 10 dB (−49.9 instead of −60 LUFS). The limiter only acts on those peaks (1.9–3.3 dB in the examples). It does not shorten, overlap or fade speech, and quiet audio is never touched.
- **Final:** ffmpeg `loudnorm` **two-pass, linear mode**, target −18 LUFS, TP −1 dBTP; measured values written to the report. After limiting, linear mode applies; if loudnorm still reports dynamic mode, the report flags it.
*Why per-unit first:* guarantees cached and fresh units match (the 2 LU scenario), independent of the engine's output level.

### D6 — Noise Floor and built-in sounds are generated, not shipped as files
- `room_tone` (default) and `brown_noise` beds are generated procedurally (filtered noise, fixed seed) at render length, at a level of **target −42 LU** (configurable). Ambience switches crossfade beds over 2 s.
- `bell_soft` is synthesized (sum of exponentially decaying partials) and cached in memory.
*Why:* no licensing questions, no binary assets in the repo, deterministic output for tests. A curated Ambience library is a later milestone.

### D7 — Duration fitting
Let `delta = target − unfitted_total`. If `delta > 0`, each Elastic Pause grows toward its `max` proportionally to `(max − seconds)`; if `delta < 0`, it shrinks toward `min` proportionally to `(seconds − min)`. The fit aims at the exact target and is clamped to the ranges; afterwards the ±10 % check runs. On failure the error reports `[sum of mins, sum of maxes] + fixed` as the achievable range. Segment gaps, sentence gaps and fades count as fixed.

### D8 — Pacing profiles
A YAML file shipped in the package (`anchor/audio/pacing.yaml`), overridable via config, with per Session Type: `speed`, `sentence_gap_sec`, `segment_gap_sec`, `fade_in_sec`, `fade_out_sec`. Initial defaults (to be tuned in the listening test):

| type | speed | sentence gap | segment gap | fade-out |
| --- | --- | --- | --- | --- |
| `sleep` | 0.85 | 1.6 s | 2.5 s | 30 s |
| `day`, `rehearsal`, `taster` | 0.9 | 1.1 s | 1.8 s | 3 s |
| `short`, `cue_recall` | 0.95 | 0.9 s | 1.4 s | 2 s |
| `pre_event` | 1.0 | 0.7 s | 1.0 s | 1.5 s |

`speed` is sent to the backend; the mixer never time-stretches speech (time-stretching degrades TTS audio audibly).

### D9 — TTS Adapter
A `TTSAdapter` Protocol following spec §10.1 (`capabilities`, `list_voices`, `synthesize`, `health`; `clone_voice` omitted for now) and one `OpenAICompatibleAdapter` using **httpx**: `POST /v1/audio/speech` with `response_format: "wav"`; 3 retries with exponential backoff on connection errors and 5xx, none on 4xx. Results carry `backend_id`, `model`, `voice`, `speed`, `sample_rate`. Speaches-specific calls (health, model/voice listing) live in a small subclass, so a plain OpenAI-compatible server still works for synthesis.

### D10 — Segment Cache on the filesystem
Key = SHA-256 over a canonical JSON of the fields in spec §9.2 (`text_norm_version` starts at `"1"`; `seed` is `null` for Piper). Layout: `<cache_dir>/<key[:2]>/<key>.wav` plus `<key>.json` with the key fields, for debugging. Writes go to a temp file in the same directory followed by `os.replace` (atomic on POSIX); readers only consider `.wav` files whose `.json` exists, which is written last. Raw backend WAV is stored unmodified (spec: "Stored audio is raw synthesis output").

### D11 — Config
`anchor.toml` (path via `--config` or `ANCHOR_CONFIG`, default `./anchor.toml`), env overrides with prefix `ANCHOR_` (e.g. `ANCHOR_TTS__BASE_URL`, `ANCHOR_TTS__API_KEY`). The API key is only read from env or config, never from Scripts.

### D12 — Speaches deployment
`docker-compose.yml` with a pinned Speaches CPU image, a named volume for the model cache, port bound to **127.0.0.1** only (the M1 CLI runs on the host; from M5 on, the worker joins an internal network and the port binding goes away). API key enabled.

### D13 — Testing strategy
- A `FakeTTSAdapter` returns deterministic synthetic "speech" (tone bursts with known leading/trailing silence and level) — used for all mixer, trimming, fitting, loudness and cache tests.
- Assertions on audio properties (duration, zero-runs, LUFS, true peak, gap lengths) rather than golden files.
- One integration test, marked `@pytest.mark.speaches`, skipped unless a backend is reachable.
- Acceptance: the listening test (`docs/listening-test.md`) is a manual checklist run on the three example Scripts.

## Risks / Trade-offs

- [Piper German voices sound robotic] → accepted for M1; the pipeline is engine-agnostic and Qwen3-TTS arrives in M7. The listening test judges assembly, not voice quality.
- [Backend ignores `speed`] → integration test compares durations at speed 0.85 vs 1.0; if Speaches/Piper ignores it, record that in the report and pick a slower Voice, rather than time-stretching.
- [Trimming eats soft onsets (breathy "h", "f")] → relative threshold plus 30 ms margin; unit tests with low-level onsets; listening test item.
- [Memory for long Sessions] → 30 min at 48 kHz mono float32 ≈ 350 MB per buffer; acceptable on 8 GB with one Render Job at a time. If the worker later runs jobs concurrently, switch to chunked mixing.
- [loudnorm falls back to dynamic mode] → happened for all Piper renders (speech peaks); prevented by the true-peak limiter (D5), still flagged in the report.
- [Limiter audibly squashes plosives] → it only acts on the few peaks above −1.5 dBTP, by about 3 dB at most in the examples; listening-test item.
- [ffmpeg build differences] → require ffmpeg ≥ 6 with libmp3lame, libopus and soxr; checked at startup with a clear error.
- [Sentence splitter mis-splits] → protected abbreviation list; mis-splits only change gap placement, never content.

## Migration Plan

Greenfield; nothing to migrate. Rollback = not using the CLI. The cache directory can be deleted at any time without loss beyond re-synthesis.

## Open Questions

- Final pacing defaults and bed level — tuned during the listening test; changes only values in `pacing.yaml`/config.
- Which German Piper voice is the default (`thorsten` variants vs. others) — chosen during the listening test; a config value.
