# Proposal

## Why

Every later milestone (LLM scripts, Programs, client) produces or consumes Session audio, yet nothing turns a Session Script into a listenable file today — the repo has no code at all. M1 (`docs/spec.md` §14) establishes that foundation without LLMs or domain logic, and it is where the audio-quality risks (pacing, clipped word endings, digital silence, level jumps; spec §9.1, §13) and CPU render cost (NFR-1/2) must be settled before anything builds on top.

## What Changes

- New Python 3.12 project skeleton (`anchor` package) with a CLI command `anchor render <script.json> -o <out.mp3>`.
- Session Script format v1.2 (spec §9) as a Pydantic model with structural validation; `speech` Segments with literal `text` only (Formula references are rejected until the content base exists in M3).
- An OpenAI-compatible TTS Adapter (spec §10.1, Appendix A.3) and a Docker Compose service for Speaches with a German Piper voice.
- A content-addressed Segment Cache for rendered speech (spec §9.2, FR-51); repeated text with the same Voice settings never reaches the TTS Engine twice.
- An Audio Mixer implementing the assembly rules (spec §9.1): silence trimming, no crossfades over speech, Noise Floor under all pauses, tone-based sounds, per-Session-Type pacing, per-segment and final loudness normalization, long fade-out for `sleep`.
- Elastic Pause fitting so the rendered duration lands within ±10 % of `target_duration_sec` (FR-52), with a clear error when it cannot.
- A render report (JSON) with actual duration, loudness, cache hits/misses and synthesis time, as input for NFR-1/2 benchmarking.
- Hand-written example Scripts (`day`, `sleep`, `short`) and a documented listening-test checklist as M1 acceptance.

Out of scope: LLM generation and domain validation (M2), Formulas and content (M3), API/worker/database (M5), Qwen3-TTS and STT quality gate (M7).

## Capabilities

### New Capabilities

- `session-script`: the Session Script document format (schema version, Session Types, Segment types, Elastic Pauses) and its structural validation.
- `tts-synthesis`: synthesizing speech through pluggable TTS Adapters, starting with OpenAI-compatible backends, including Voice selection and health checks.
- `segment-cache`: content-addressed storage and reuse of rendered speech Segments.
- `audio-rendering`: assembling a validated Session Script into a final Audio Asset — pacing, pauses, Noise Floor, sounds, duration fitting, loudness, fades, output encoding and the render report — exposed via the CLI.

### Modified Capabilities

(none — no existing specs)

## Impact

- New code: `pyproject.toml`, `src/anchor/` (script, tts, cache, audio, cli), `tests/`, `examples/scripts/`.
- New runtime dependencies: Python 3.12, ffmpeg (system binary), `pydantic`, `httpx`, `typer`, `numpy`, `soundfile`, `pyloudnorm`.
- New infrastructure: `docker-compose.yml` with a `speaches` service on an internal network (no host exposure beyond localhost for the CLI).
- Local disk: cache directory (default `~/.cache/anchor/segments`) grows with rendered speech.
