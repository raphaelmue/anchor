# Tasks

## 1. Project setup

- [x] 1.1 Create `pyproject.toml` (uv, Python 3.12) with `src/anchor/` package, dependencies (pydantic, pydantic-settings, httpx, typer, numpy, soundfile, pyloudnorm, pyyaml) and dev dependencies (pytest, ruff); verify `uv sync` succeeds and `uv run python -c "import anchor"` works
- [x] 1.2 Add `anchor` console entry point with an empty typer app; verify `uv run anchor --help` prints the command list
- [x] 1.3 Add ruff and pytest config; verify `uv run ruff check` and `uv run pytest` run green on the empty project
- [x] 1.4 Add an ffmpeg capability check (version ≥ 6, libmp3lame, libopus, soxr) with a clear error message; verify with a unit test that mocks `ffmpeg -version`/`-encoders` output for both a passing and a failing build

## 2. Session Script format (`session-script`)

- [x] 2.1 Implement Pydantic models for Script v1.2 (required fields, Session Type enum, discriminated Segment union with per-type fields, 300-char speech limit, `role`/`style`/`strategy`, preserved optional metadata); verify unit tests for each scenario in `specs/session-script/spec.md`
- [x] 2.2 Implement Elastic Pause validation (`0 <= min <= seconds <= max`) and the Formula-reference rejection; verify unit tests for valid range, out-of-range and formula scenarios
- [x] 2.3 Implement validation that collects all errors with locations (field path / Segment index) into one result; verify the multi-error scenario test
- [x] 2.4 Add `anchor validate <script.json>` command printing all errors and exiting non-zero on failure; verify with CLI tests (typer `CliRunner`) for valid and invalid files

## 3. TTS synthesis (`tts-synthesis`)

- [x] 3.1 Implement config loading (`anchor.toml` + `ANCHOR_` env overrides, D11); verify a unit test where an env var overrides the file's base URL
- [x] 3.2 Define the `TTSAdapter` Protocol and result type carrying backend/model/voice/speed/sample-rate identity (D9); implement `FakeTTSAdapter` producing deterministic tone bursts with configurable leading/trailing silence and level; verify unit tests for identity fields and fake output properties
- [x] 3.3 Implement `OpenAICompatibleAdapter` (`POST /v1/audio/speech`, wav response, retries with backoff on connection errors/5xx, no retry on 4xx, errors naming backend and cause); verify unit tests with `httpx.MockTransport` for success, 5xx-then-success, 400 and unreachable
- [x] 3.4 Add `docker-compose.yml` with a pinned Speaches CPU image, model volume, API key and port bound to 127.0.0.1 (D12); look up and pin the Speaches image tag, the health/model/voice-listing endpoints and the German Piper model ID; verify `docker compose up -d speaches` starts and the health endpoint answers
- [x] 3.5 Implement the Speaches subclass with health check (reachable, model available, voice available) and voice listing filtered by language; add `anchor tts health` and `anchor tts voices --language de-DE`; verify mocked unit tests plus a manual run against the running container
- [x] 3.6 Add the `@pytest.mark.speaches` integration test (synthesize a German sentence; compare durations at speed 0.85 vs 1.0 and record whether `speed` is honored); verify it passes with the container running and is skipped without it
- [x] 3.7 Document backend setup (compose, model download, config keys, env vars) in `docs/render-pipeline.md`; verify by following the steps from a clean checkout

## 4. Segment Cache (`segment-cache`)

- [x] 4.1 Implement text normalization (NFC, collapse whitespace, trim; `text_norm_version = "1"`) and the SHA-256 key over canonical JSON of all key fields (D10); verify unit tests for same-key, speed-changes-key, model-changes-key and whitespace scenarios
- [x] 4.2 Implement filesystem storage (`<dir>/<key[:2]>/<key>.wav` + `.json` written last, temp file + `os.replace`); verify unit tests that a leftover temp file or a `.wav` without `.json` is treated as a miss
- [x] 4.3 Implement a caching wrapper around any `TTSAdapter` with hit/miss counters and a bypass flag that overwrites entries; verify unit tests with `FakeTTSAdapter` that a second lookup makes zero adapter calls and bypass makes calls again
- [x] 4.4 Add cache location to config and document it (including that deleting the cache is safe) in `docs/render-pipeline.md`; verify the configured directory is used in a unit test

## 5. Audio building blocks (`audio-rendering`)

- [x] 5.1 Implement ffmpeg-based decode + resample to 48 kHz mono float32 (D2); verify a unit test decoding a 22.05 kHz WAV yields the expected length at 48 kHz
- [x] 5.2 Implement sentence splitting with the protected German abbreviation list (D3); verify unit tests for two sentences, `z. B.`, `usw.`, ellipsis and question marks
- [x] 5.3 Implement silence trimming to a 30 ms margin with a 5 ms de-click ramp inside the margin only (D4); verify unit tests that units with 50 ms and 400 ms trailing silence end up with identical margins and that voiced samples are unchanged
- [x] 5.4 Implement per-unit loudness normalization including the < 400 ms fallback (D5); verify unit tests that fake units at different levels end within 2 LU short-term loudness of each other
- [x] 5.5 Implement procedural beds (`room_tone`, `brown_noise`) at target −42 LU with 2 s crossfades, and the synthesized `bell_soft` (D6); verify unit tests for bed level, no zero-runs > 10 ms, and determinism (same seed → same samples)
- [x] 5.6 Implement the pacing profile loader (`anchor/audio/pacing.yaml` with D8 defaults, config override); verify unit tests that `sleep` has lower speed and longer gaps than `pre_event`, and that an override file replaces values

## 6. Render pipeline and CLI (`audio-rendering`)

- [x] 6.1 Implement preflight (sound/ambience names exist, sleep-must-not-end-with-sound rule) and the plan stage (sentences, normalized text, cache keys, miss count); verify unit tests for the unknown-sound and sleep-end-bell scenarios, and that no adapter call happens when preflight fails
- [x] 6.2 Implement synthesis of misses (sequential) with the backend health check only when misses exist; verify unit tests that a fully cached plan makes no health or synthesis calls
- [x] 6.3 Implement the unfitted layout (speech units with sentence/segment gaps, pauses, `silent_practice` prompt + silence, sounds, markers) producing a timeline with sample positions; verify unit tests for the silent-practice-with-prompt and marker-timestamp scenarios
- [x] 6.4 Implement elastic duration fitting (D7) including the achievable-range error; verify unit tests for the fits-by-stretching, shrinking and cannot-fit scenarios
- [x] 6.5 Implement mixing (bed over full length, speech, sounds), start fade-in, end fade-out per Session Type (long fade for `sleep`); verify unit tests for the sleep fade-out scenario and that voiced samples are not attenuated by any fade
- [x] 6.6 Implement final loudness (ffmpeg `loudnorm` two-pass linear, −18 LUFS, TP −1 dBTP, dynamic-fallback flag) and encoding to MP3/Opus by option or extension; verify tests that output loudness is −18 ± 1 LUFS, true peak ≤ −1 dBTP, and `.opus` output is Opus
- [x] 6.7 Implement atomic output (temp file + rename, no overwrite on failure) and the JSON render report with all fields from the spec; verify tests that a failure mid-render leaves an existing output file unchanged and that the report contains every field
- [x] 6.8 Add `anchor render <script.json> -o <out> [--no-cache] [--format mp3|opus]` wiring all stages, printing validation errors and exiting non-zero on failure; verify CLI tests with `FakeTTSAdapter` for success, invalid script and backend failure
- [x] 6.9 Document rendering, pacing profiles, report fields and audio rules in `docs/render-pipeline.md`; verify the documented commands run as written

## 7. Examples, acceptance and benchmarks

- [x] 7.1 Write hand-written German example Scripts in `examples/scripts/` (`day` ≈ 10 min PMR-style with Emergence, `sleep` ≈ 15 min without end sound, `short` ≈ 3 min paced breathing with `silent_practice`), each with Elastic Pauses; verify `anchor validate` passes for all three
- [x] 7.2 Render all three examples against Speaches; verify each render succeeds, durations are within ±10 % of target, and a second render reports 100 % cache hits with zero synthesis time
- [x] 7.3 Write `docs/listening-test.md` (checklist: no clipped word endings, no dropouts/digital silence, even pause lengths, no level jumps, calm pacing per type, sleep ends without sound, bell clean) and run it on the three renders; verify by recording results and any tuned pacing/bed/voice values in the doc and in `pacing.yaml`/config
- [x] 7.4 Record render reports (synthesis time vs. speech duration, total render time) for the three examples on the target hardware in `docs/render-pipeline.md`; verify the numbers are present and compared against NFR-1/2 sizing assumptions
