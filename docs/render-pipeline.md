# Render Pipeline (M1)

Turns a Session Script (JSON, format v1.2, `docs/spec.md` §9) into a listenable Audio Asset:

```
anchor render examples/scripts/day.json -o out/day.mp3
```

The library (`anchor.script`, `anchor.tts`, `anchor.cache`, `anchor.audio`, `anchor.render`) is
what the M5 worker will reuse; the CLI is a thin layer on top.

## 1. Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- ffmpeg ≥ 6 built with `libmp3lame`, `libopus` and `libsoxr` (checked before every render;
  the error names whatever is missing)
- Docker with Compose v2, for the TTS Backend

```
uv sync
uv run anchor --help
```

## 2. TTS Backend: Speaches with a German Piper voice

The backend runs in its own container (`docker-compose.yml`). This keeps Piper's GPL-3.0
engine out of the Anchor process. The image is pinned to `ghcr.io/speaches-ai/speaches:0.8.3-cpu`.
The port is bound to `127.0.0.1` only, and an API key is required.

### 2.1 Start

```
export ANCHOR_TTS__API_KEY=$(openssl rand -hex 16)   # the same variable is used by compose and anchor
docker compose up -d speaches
curl -sf -H "Authorization: Bearer $ANCHOR_TTS__API_KEY" http://127.0.0.1:8000/health   # -> OK
```

Compose refuses to start without `ANCHOR_TTS__API_KEY`. Speaches then requires the key on every
request, `/health` included (HTTP 403 without it). Set `SPEACHES_PORT` to publish on a port other
than 8000, and change `tts.base_url` to match.

### 2.2 Download the model

Models are stored in the named volume `hf-hub-cache` and survive container restarts.

```
curl -X POST -H "Authorization: Bearer $ANCHOR_TTS__API_KEY" \
  http://127.0.0.1:8000/v1/models/speaches-ai/piper-de_DE-thorsten-medium
```

To list the German models the registry offers (other voices: `kerstin-low`, `ramona-low`,
`thorsten-high`, `thorsten_emotional-medium`, `mls-medium`, …):

```
curl -s -H "Authorization: Bearer $ANCHOR_TTS__API_KEY" \
  "http://127.0.0.1:8000/v1/registry?task=text-to-speech" | grep -o '"id":"[^"]*de_DE[^"]*"'
```

### 2.3 Check

```
uv run anchor tts health                 # reachable / model installed / voice available; exit 1 if not
uv run anchor tts voices --language de-DE
```

Speaches reports bare language codes (`de`). The language filter accepts `de-DE`, `de_DE` or `de`.

### 2.4 Speaches endpoints used

| Purpose | Endpoint |
| --- | --- |
| Synthesis | `POST /v1/audio/speech` (`model`, `voice`, `input`, `speed`, `response_format: "wav"`, `sample_rate`) |
| Liveness | `GET /health` |
| Model installed? (+ its voices) | `GET /v1/models/{model_id}` (404 if not installed) |
| Installed models and voices | `GET /v1/models?task=text-to-speech` |
| Downloadable models | `GET /v1/registry?task=text-to-speech` |
| Download a model | `POST /v1/models/{model_id}` |

Backend quirks found during setup (Speaches 0.8.3, Piper `thorsten-medium`):

- **`sample_rate` must be sent.** If it is missing, Speaches labels Piper WAV output as
  24 kHz although Piper produces 22.05 kHz, so speech plays too fast and too high. The adapter
  always sends `tts.sample_rate`. If a backend returns any other rate, the adapter fails with an
  explicit error instead of caching mislabeled audio.
- **`speed` is honored, but weaker than its nominal value.** Speaches maps it to Piper's
  `length_scale = 1/speed`. At speed 0.85, the voiced span is about 7–12 % longer, not 18 %
  (medians of 7 syntheses, see `tests/test_speaches_integration.py`).
- **Piper is not deterministic.** Phoneme durations are randomized, so the same sentence differs
  in length by up to ~10 % from one synthesis to the next. The Segment Cache makes repeated text
  identical across renders.

### 2.5 Integration test

```
uv run pytest -m speaches -s      # needs the container and ANCHOR_TTS__API_KEY; skipped otherwise
```

## 3. Configuration

Settings come from `anchor.toml`, which is located by `--config`, then `$ANCHOR_CONFIG`, then
`./anchor.toml`. A missing default file is fine; a file named explicitly must exist.
Environment variables override the file: `ANCHOR_<SECTION>__<KEY>`. The API key is read only from
the config or the environment, never from Scripts. `anchor.example.toml` lists every key with its
default.

| Key | Env var | Default | Meaning |
| --- | --- | --- | --- |
| `tts.kind` | `ANCHOR_TTS__KIND` | `speaches` | `speaches` (health + voice listing) or `openai` (plain OpenAI-compatible server) |
| `tts.backend_id` | `ANCHOR_TTS__BACKEND_ID` | `speaches` | Backend identity (part of the cache key) |
| `tts.base_url` | `ANCHOR_TTS__BASE_URL` | `http://127.0.0.1:8000` | Backend URL |
| `tts.api_key` | `ANCHOR_TTS__API_KEY` | – | Bearer token |
| `tts.model` | `ANCHOR_TTS__MODEL` | `speaches-ai/piper-de_DE-thorsten-medium` | Model ID |
| `tts.voice` | `ANCHOR_TTS__VOICE` | `thorsten` | Voice ID |
| `tts.sample_rate` | `ANCHOR_TTS__SAMPLE_RATE` | `22050` | Requested output rate (cache key) |
| `tts.timeout_sec` | `ANCHOR_TTS__TIMEOUT_SEC` | `120` | Per-request timeout |
| `tts.retries` | `ANCHOR_TTS__RETRIES` | `3` | Retries on connection errors / HTTP 5xx; 4xx is never retried |
| `tts.backoff_sec` | `ANCHOR_TTS__BACKOFF_SEC` | `0.5` | First retry delay, doubled per attempt |
| `cache.dir` | `ANCHOR_CACHE__DIR` | `~/.cache/anchor/segments` | Segment Cache directory |
| `audio.ffmpeg` | `ANCHOR_AUDIO__FFMPEG` | `ffmpeg` | ffmpeg binary |
| `audio.pacing_file` | `ANCHOR_AUDIO__PACING_FILE` | – | YAML that replaces pacing profile values |
| `audio.loudness_target_lufs` | `ANCHOR_AUDIO__LOUDNESS_TARGET_LUFS` | `-18` | Final integrated loudness |
| `audio.true_peak_dbtp` | `ANCHOR_AUDIO__TRUE_PEAK_DBTP` | `-1` | Final true-peak ceiling |
| `audio.speech_lufs` | `ANCHOR_AUDIO__SPEECH_LUFS` | `-18` | Per-unit speech loudness before mixing |
| `audio.bed_level_lu` | `ANCHOR_AUDIO__BED_LEVEL_LU` | `-42` | Noise Floor level relative to the target |
| `audio.mp3_bitrate` / `audio.opus_bitrate` | `ANCHOR_AUDIO__MP3_BITRATE` / `…OPUS_BITRATE` | `128k` / `64k` | Encoder bitrates |

## 4. Segment Cache

Each speech sentence is stored content-addressed, so the same text with the same Voice settings
reaches the TTS Engine only once (spec §9.2, FR-51).

- **Location:** `cache.dir` (default `~/.cache/anchor/segments`, env `ANCHOR_CACHE__DIR`).
- **Key:** SHA-256 over canonical JSON of: normalized text, `text_norm_version` (`"1"`),
  backend ID, model ID, Voice ID, speed, style, seed, sample rate. Changing the model, Voice or
  pacing speed creates new entries, so old and new voices are never mixed silently.
- **Normalization (v1):** Unicode NFC, whitespace runs collapsed, trimmed. `"Atme  ruhig."`
  and `"Atme ruhig. "` share one entry.
- **Layout:** `<dir>/<key[:2]>/<key>.wav` holds the raw backend WAV, untrimmed and not
  normalized. `<key>.json` holds the key fields, for debugging. Both files are written via a temp
  file and `os.replace`, and the `.json` comes last. An entry counts only when its `.json` exists,
  so an interrupted render just re-synthesizes that sentence.
- **Raw audio:** trimming, loudness and gaps are applied at render time. Changing pacing values
  other than `speed` (gaps, fades, levels) therefore never requires re-synthesis.
- **Bypass:** `anchor render … --no-cache` synthesizes every unit again and overwrites its entry.
- **Deleting is safe.** Removing the whole directory (or any part of it) at any time loses only
  synthesis time: missing entries are synthesized again on the next render.

## 5. Rendering

```
uv run anchor validate examples/scripts/day.json          # structural check, prints every error
uv run anchor render examples/scripts/day.json -o out/day.mp3
uv run anchor render examples/scripts/short.json -o out/short.opus          # Opus by extension
uv run anchor render examples/scripts/sleep.json -o out/sleep.mp3 --no-cache # re-synthesize everything
uv run anchor --config other.toml render examples/scripts/day.json -o out/day.ogg --format opus
```

- The output is MP3 by default, or Opus when the extension is `.opus`/`.ogg` or `--format opus`
  is given. Bitrates come from `audio.mp3_bitrate` and `audio.opus_bitrate`.
- `<name>.report.json` is written next to the output (`out/day.mp3` → `out/day.report.json`).
- Exit status 0 on success. On any failure it is non-zero and the reason is printed. Invalid
  Scripts print every validation error and never reach the backend.
- **No partial output:** the encoded file is written to a temp file next to the output and only
  renamed into place on success. A failed render never leaves a file behind or overwrites an
  existing one.

### Stages

```
validate -> preflight -> plan -> synthesize misses -> prepare units -> layout -> fit
  -> mix (bed + speech + sounds, fades) -> peak limit + loudnorm (linear) -> encode -> rename -> report
```

1. **Preflight:** checks the ffmpeg build, that every `sound`/`ambience` name exists, and the
   sleep end rule. Nothing is synthesized if this fails.
2. **Plan:** splits each `speech` text (and `silent_practice` prompt) into sentences, normalizes
   them and computes cache keys. Sentence splitting knows German abbreviations (`z. B.`, `usw.`,
   `d. h.`, …) and ordinals (`3. Tag`). An ellipsis ends a sentence only before an upper-case word.
3. **Synthesize misses:** the backend health check runs only if at least one unit is not
   cached, so a fully cached Script renders without a backend. Misses are synthesized one after
   another.
4. **Prepare units:** decode to 48 kHz mono, trim silence, normalize loudness.
5. **Layout and fit:** see the audio rules below.
6. **Mix, loudness, encode, report.**

## 6. Pacing profiles

Built-in defaults live in `src/anchor/audio/pacing.yaml`. Point `audio.pacing_file` at a YAML
file to change them; it only needs the values you want to replace:

```yaml
sleep:
  sentence_gap_sec: 2.0
  fade_out_sec: 45
```

| Session Type | speed | sentence gap | Segment gap | fade-in | fade-out |
| --- | --- | --- | --- | --- | --- |
| `sleep` | 0.85 | 1.6 s | 2.5 s | 3 s | 30 s |
| `day`, `rehearsal`, `taster` | 0.9 | 1.1 s | 1.8 s | 2 s | 3 s |
| `short`, `cue_recall` | 0.95 | 0.9 s | 1.4 s | 1.5 s | 2 s |
| `pre_event` | 1.0 | 0.7 s | 1.0 s | 1 s | 1.5 s |

`speed` is sent to the TTS Backend; the mixer never time-stretches speech. With Piper, speed
0.85 lengthens speech by only about 9 % (§2.4). Changing `speed` creates new cache entries;
changing any other value reuses cached audio.

## 7. Audio rules (spec §9.1)

- **Single sample rate:** everything is mixed as 48 kHz mono float32 and output at 48 kHz.
- **Trimming:** each sentence's voiced span is detected with 10 ms RMS windows at −45 dB relative
  to its peak, and exactly 30 ms of margin is kept on both sides. Engine padding therefore never
  changes pause lengths. A 5 ms de-click ramp lies inside that margin, so voiced samples stay
  bit-identical.
- **Gaps:** the sentence gap separates sentences of one Segment. The Segment gap separates
  consecutive audible Segments (speech, sounds, prompts). A `pause` or the silence of a
  `silent_practice` replaces the Segment gap. Markers and ambience switches take no time.
- **Speech is never cut, overlapped or faded.** Fades act on the background only, and speech
  and sounds are added on top.
- **Noise Floor:** a procedural `room_tone` bed runs from start to end at
  `loudness_target + bed_level_lu` (−60 LUFS by default), so there is never digital silence. An
  `ambience` Segment (`room_tone`, `brown_noise`) switches the bed with a 2 s equal-power
  crossfade. Beds are generated with a fixed seed and are identical on every render.
- **Sounds:** `bell_soft` is synthesized (decaying partials), placed at the Segment's position
  over the background at speech level −4 LU, and occupies its full 6 s.
- **Start and end:** speech starts 0.5 s in while the background fades in over `fade_in_sec`.
  After the last Segment, the background fades to silence over `fade_out_sec`. A `sleep`
  Session whose last audible Segment is a sound is rejected in preflight.
- **Duration fitting:** with `delta = target − unfitted`, each Elastic Pause grows toward its
  `max` (or shrinks toward its `min`) in proportion to its remaining room, aiming at the exact
  target. If the result is more than ±10 % off target, the render fails and names the achievable
  range.
- **Loudness:** each sentence is normalized to `audio.speech_lufs` (BS.1770; units under 400 ms
  are measured zero-padded and corrected). The final mix gets the gain to
  `loudness_target_lufs`, then a 4× oversampled, latency-compensated true-peak limiter at
  `true_peak_dbtp` − 0.5 dB (MP3) or − 1.0 dB (Opus, whose encoder overshoots more), then ffmpeg `loudnorm` two-pass in **linear** mode. The limiter matters
  for Piper: about 10 % of its sentences peak above −1 dBTP at −18 LUFS. Without it, loudnorm
  falls back to dynamic mode and raises the Noise Floor in pauses by about 10 dB.

## 8. Render report

| Field | Meaning |
| --- | --- |
| `output`, `format`, `script`, `session_type`, `created_at` | What was rendered, and when |
| `output_duration_sec` / `target_duration_sec` | Actual vs. Script target |
| `unfitted_duration_sec` | Duration before Elastic Pause fitting |
| `integrated_loudness_lufs`, `true_peak_dbtp` | Measured on the encoded file (EBU R128) |
| `loudnorm_mode`, `loudnorm_dynamic_fallback` | `linear` expected; `true` means loudnorm fell back to dynamic mode |
| `peak_limiting_db` | Largest gain reduction applied by the peak limiter |
| `speech_units`, `speech_duration_sec` | Number and total length of trimmed speech sentences |
| `cache_hits`, `cache_misses`, `cache_bypass` | Segment Cache use (`--no-cache` → all misses) |
| `synthesis_time_sec` | Wall time spent in backend calls (0 for a fully cached render) |
| `render_time_sec` | Total wall time of the render |
| `elastic_pauses[]` | `segment_index`, nominal `seconds`, `fitted_sec`, `elastic` range |
| `markers[]` | `name`, `time_sec` (position in the output) |
| `tts` | `backend_id`, `model`, `voice`, `speed`, `sample_rate` used |
| `pacing` | The pacing profile that was applied |

## 9. Benchmarks (NFR-1/2)

Cold renders (`--no-cache`, every sentence synthesized) of the three examples, 2026-10-26.
Speaches 0.8.3 with Piper `thorsten-medium`, ffmpeg 9.0.2, Python 3.12.

**Machine:** AMD Ryzen 5 2600X (6 cores / 12 threads), 31 GB RAM. This is a development machine,
not the target server. The "4 CPU" rows limit the Speaches container to 4 CPUs and 8 GB
(`docker update --cpus 4 --memory 8g`) to approximate NFR-3. The mixer itself ran unconstrained.
Numbers from the real home server should be added here.

| Run | Script | Output | Speech units | Speech (trimmed) | Synthesis | Synthesis ÷ speech | Total render |
| --- | --- | --- | --- | --- | --- | --- | --- |
| full | `day` | 577.5 s | 49 | 93.0 s | 10.8 s | 0.12 | 39.0 s |
| full | `sleep` | 900.0 s | 39 | 63.3 s | 7.2 s | 0.11 | 48.5 s |
| full | `short` | 180.0 s | 14 | 36.4 s | 3.7 s | 0.10 | 12.9 s |
| 4 CPU | `day` | 576.6 s | 49 | 92.1 s | 21.5 s | 0.23 | 49.5 s |
| 4 CPU | `sleep` | 900.0 s | 39 | 62.5 s | 13.9 s | 0.22 | 55.0 s |
| 4 CPU | `short` | 180.0 s | 14 | 36.4 s | 7.4 s | 0.20 | 16.7 s |

Fully cached renders of the same Scripts take 9–40 s with zero synthesis time. Speaches used
about 430 MB of RAM.

**Against the sizing assumptions:**

- **Speech share is far below the assumed 40–60 %.** Trimmed speech is 16 % (`day`),
  7 % (`sleep`) and 20 % (`short`) of the output; the rest is gaps and Elastic Pauses. NFR-1's
  "≈ 120 min of speech per 6 h night" therefore covers far more Session time than assumed.
- **Piper is about 5–10× faster than real time** (synthesis ÷ speech 0.10–0.12, or 0.20–0.23
  on 4 CPUs). Synthesis is not the bottleneck for Piper. Mixing, peak limiting and encoding take
  20–40 s per Session, mostly the ffmpeg passes at 4× oversampling, which scale with output
  length rather than speech length.
- **NFR-2 (first playable ≤ 10 min, regenerate ≤ 10 min) holds comfortably for Piper:** the
  slowest cold render took 55 s.
- **Projection for Qwen3-TTS 0.6B int8 (≈ 3× slower than real time on 4 vCPU, Appendix A):**
  `day` ≈ 93 s × 3 + ~30 s ≈ 5 min, and `sleep` ≈ 63 s × 3 + ~40 s ≈ 4 min. That is within
  NFR-2, and one 6 h night would fit about 70 such Sessions. These are estimates to confirm in
  M7, not measurements.
