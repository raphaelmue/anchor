# LLM-written Session Scripts (M2)

This document covers the LLM Provider layer, the Script Request, Script generation and the
domain validation that every Script passes on top of structural validation. Design decisions are
in `openspec/changes/add-llm-scripts/design.md` (D1–D12).

## 1. Setup

```sh
uv sync
export ANTHROPIC_API_KEY=sk-ant-...      # PowerShell: $env:ANTHROPIC_API_KEY = "sk-ant-..."
uv run anchor generate examples/requests/short.yaml -o out/short.json
uv run anchor validate out/short.json --request examples/requests/short.yaml
uv run anchor render out/short.json -o out/short.mp3      # needs Speaches and ffmpeg (M1)
```

**API keys** are read only from the environment. The `anchor` CLI also loads a git-ignored
`./.env` file at startup, and variables already set in the environment take precedence. Each
provider uses its standard variable:
`ANTHROPIC_API_KEY` for `anthropic/*` models, `OPENAI_API_KEY` for `openai/*`. For a
self-hosted **LiteLLM proxy**, use `litellm_proxy/<model name on the proxy>` and set
`LITELLM_PROXY_API_BASE` (e.g. `https://llm-proxy.example.org`) and `LITELLM_PROXY_API_KEY`.
The base URL is required: without it, LiteLLM would send the request, with the proxy key, to
api.openai.com, so `anchor generate` refuses to start. A key under
`[llm]` in `anchor.toml` is rejected when the config loads. `anchor generate` checks for the key
before any request and names the missing variable. Keys never appear in output, error messages
or generation records.

**Configuration** lives in the `[llm]` section of `anchor.toml` (see `anchor.example.toml`).
Every key can be overridden as `ANCHOR_LLM__<KEY>`:

| Key | Default | Meaning |
| --- | --- | --- |
| `model` | `litellm_proxy/glm` | LiteLLM `provider/model` id used for generation |
| `review_model` | `""` | Model for the Suggestion Review; empty means `model` |
| `effort` | `high` | Effort level, sent to `anthropic/*` (as `output_config.effort`) and `litellm_proxy/*` (as `reasoning_effort`); empty means the provider default |
| `max_tokens` | `16000` | Output limit per call, thinking included |
| `timeout_sec` | `300` | Per-request timeout |
| `retries`, `backoff_sec` | `3`, `1.0` | Retries on rate limits, timeouts, connection errors and 5xx, with exponential backoff. 4xx errors are never retried. |
| `max_attempts` | `3` | Generation attempts with error feedback (FR-16) |

`tts.chars_per_sec` (default 21.0) sets the Speech Rate for the duration estimate (§3.3).

**Switching model or provider** is configuration only. For example:

```sh
ANCHOR_LLM__MODEL=openai/<model> OPENAI_API_KEY=sk-... uv run anchor generate ...
```

A review by a different model is one line: `review_model = "openai/<model>"`. A model that
reviews its own output is more lenient than an independent reviewer.

**Tests.** All tests run offline against a fake LLM Adapter. The one paid integration test
generates the `short` example against the configured model with review. It is excluded from
plain `pytest` and runs only with `uv run pytest -m llm`, and without credentials it is skipped.

## 2. LLM Provider mechanism (LiteLLM spike)

## 2. LLM Provider mechanism (LiteLLM spike)

Spike of 2026-10-26 against **LiteLLM 1.106.4** (pinned in `pyproject.toml`). LiteLLM was
pointed at a local recording HTTP server, so the exact outgoing request bodies are known without
network access. The test `tests/test_llm_litellm.py` repeats this through LiteLLM's real
transport and asserts the request shape. Rerun it after every LiteLLM upgrade.

**Structured output is native, not a forced tool.** For `anthropic/claude-opus-5-5`, a Pydantic
`response_format` becomes:

```json
POST /v1/messages        anthropic-beta: structured-outputs-2025-11-13
{
  "model": "claude-opus-5-5",
  "system": [{"type": "text", "text": "<system prompt>"}],
  "messages": [{"role": "user", "content": [{"type": "text", "text": "<user prompt>"}]}],
  "max_tokens": 16000,
  "output_format": {"type": "json_schema", "schema": { ... "additionalProperties": false }},
  "thinking": {"type": "adaptive", "display": "summarized"},
  "output_config": {"effort": "high"}
}
```

No `tools` or `tool_choice` are sent. The forced-tool risk from design D2 therefore does not
apply, and neither fallback (raw `output_config.format`, JSON-in-text) is needed. The answer is
still validated locally with Pydantic, so a fallback would only change the retry rate.

**Effort.** `reasoning_effort="high"` is mapped to `output_config.effort: "high"`, plus
`thinking: {"type": "adaptive"}`. Adaptive thinking is what `claude-opus-5-5` uses by default
anyway. `extra_body={"output_config": ...}` must not be used: LiteLLM 1.106.4 sends it as a
literal `extra_body` key in the JSON body. The adapter passes `reasoning_effort` only for
`anthropic/*` models and leaves it out when `llm.effort` is empty.

**OpenAI.** For `openai/<model>`, the same call goes to `/v1/chat/completions` with
`response_format: {"type": "json_schema", "json_schema": {..., "strict": true}}`.

**LiteLLM proxy.** For `litellm_proxy/<model>`, the call goes to
`$LITELLM_PROXY_API_BASE/chat/completions` in the OpenAI format, with
`Authorization: Bearer $LITELLM_PROXY_API_KEY`. It uses the same strict `json_schema`
`response_format`, and `reasoning_effort` is passed through for the proxy to map to its backend
model. If the backend model rejects `reasoning_effort`, set `llm.effort = ""`.

**Sampling parameters.** No request contains `temperature`, `top_p` or `top_k`. The adapter
never sets them.

**Refusals and errors.** These are mapped by the adapter (`src/anchor/llm/litellm_adapter.py`):

| Provider response | LiteLLM result | Adapter |
| --- | --- | --- |
| Anthropic `stop_reason: "refusal"` | `finish_reason == "content_filter"`, no content | `LLMRefusalError` |
| OpenAI `message.refusal` | `message.refusal` set | `LLMRefusalError` |
| `stop_reason: "max_tokens"` | `finish_reason == "length"`, truncated JSON | `LLMInvalidOutputError` ("truncated") |
| HTTP 429 | `RateLimitError` | retried with backoff |
| HTTP 500, 529 (overloaded) | `InternalServerError` | retried with backoff |
| Timeout, connection error | `Timeout`, `APIConnectionError` | retried with backoff |
| HTTP 400, 401, 404 | `BadRequestError`, `AuthenticationError`, `NotFoundError` | not retried |

None of LiteLLM's error messages contained the API key in the spike. The adapter still removes
any credential value from error text before raising.

**Open point.** LiteLLM still uses the beta `output_format` parameter with the
`structured-outputs-2025-11-13` header, not the GA `output_config.format`. The spike cannot show
whether the live API still accepts the beta form, because it ran without network access. The
`llm` integration test (task 5.1) is the check. If the live API rejects the request with
HTTP 400, upgrade LiteLLM, or fall back to JSON-in-text (D2 fallback 2).

## 3. Domain validation

Domain validation (`src/anchor/script/domain.py`) runs on Scripts that have passed structural
validation, for a given Script Request. It applies to hand-written and LLM-written Scripts alike:

```sh
uv run anchor validate examples/scripts/day.json --request examples/requests/day.yaml
```

The command prints the duration estimate, then either `valid` or every violation as
`location: rule: message`, and exits 1 on any error. Without `--request`, `anchor validate` runs
structural validation only, as in M1.

### 3.1 Rules

All rules run, and all issues are reported at once. The location is `segments[i]` for Segment
rules and `$` (or the metadata field) for whole-Script rules. "Spoken text" means `speech` text
and `silent_practice` prompts.

| Rule id | Checks |
| --- | --- |
| `match.session_type`, `match.language`, `match.target_duration_sec` | The Script's value equals the request's. |
| `match.method` | If the Script sets `method`, it equals the request's Method id. |
| `emergence.required` | `day`, `rehearsal`, `pre_event`: the last `speech` Segment has `role: emergence`. |
| `emergence.forbidden` | `sleep`: no `speech` Segment has `role: emergence`. Other types have no constraint. |
| `elements.strategy` | A `speech` Segment's `strategy` is one of the request's `strategies`. |
| `elements.cue_word` | If `cue_word_introduced` is false, the Style Sheet's `cue_word` does not appear in spoken text (case-insensitive, whole words). |
| `address.du` | Style Sheet `du`: no capitalized `Sie`/`Ihnen`/`Ihr…` after the first word of a sentence. A sentence-initial "Sie" is ambiguous ("Sie werden schwer" = "they") and is never flagged. "Atmen Sie" is flagged. |
| `address.sie` | Style Sheet `Sie`: no `du`/`dich`/`dir`/`dein…`/`euch`/`euer…`, in any case. |
| `language.de` | `de-DE`: a spoken text with ≥ 3 English stopwords and more English than German stopwords is flagged. |
| `duration.range` | The reachable duration range overlaps the target ±10 % (§3.3). |
| `suggestion.absolute`, `suggestion.medical`, `suggestion.control`, `suggestion.others` | Spoken text matches no pattern of the lexicon category (§3.2). |

The LLM Suggestion Review (`--review`, §5) runs only if all of these rules pass.

### 3.2 The Suggestion Rule lexicon

`src/anchor/script/lexicon/de-DE.yaml` holds regex patterns for the four categories of the
Suggestion Rules (spec §8.2):

- `absolute`: guarantees and absolutes ("nie wieder", "garantiert", "du wirst bestehen")
- `medical`: medical or therapeutic claims and terms (healing, therapy, diagnoses, medication,
  trauma, named disorders)
- `control`: commands implying loss of control ("du kannst die Augen nicht mehr öffnen",
  "gehorche", "gib die Kontrolle ab")
- `others`: other people as targets of change ("dein Chef wird sich ändern", "alle werden dich
  bewundern")

Patterns are matched case-insensitively on NFC-normalized text, one spoken text at a time.
Every match is reported with its Segment, category and matched phrase.

The lexicon aims for precision over recall: a false positive blocks a good Script and costs a
retry, while subtle violations are left to the LLM Review. To tune it:

1. Check a phrasing with `anchor validate <script> --request <request>`. The rule id names the
   category, and the message quotes the matched phrase.
2. Edit the pattern in `de-DE.yaml` and bump `version` (e.g. `de-DE.1` → `de-DE.2`). The version
   is written into every generation record.
3. Add the phrasing to `tests/test_domain_suggestion.py`: to `ALLOWED` for a false positive, or
   to `test_flagged_phrasings` for a missed violation. `ALLOWED` and all example speech must stay
   match-free.

### 3.3 Duration estimate and `chars_per_sec`

`src/anchor/script/duration.py` mirrors the unfitted render layout without synthesizing:

- speech time: characters of each sentence ÷ (`tts.chars_per_sec` × the Session Type's pacing
  `speed`)
- gaps: `sentence_gap_sec` between sentences, and `segment_gap_sec` between audible Segments
  (a pause replaces the gap)
- pause and `silent_practice` seconds. Elastic Pauses count with their whole `[min, max]` range,
  and the nominal estimate uses `seconds`.
- `bell_soft` (6 s), 0.5 s lead-in, and the profile's `fade_out_sec` tail

The rule passes when `[min, max]` overlaps `[0.9 × target, 1.1 × target]`, which is the range the
mixer's elastic fitting can reach at render time.

`tts.chars_per_sec` (default **21.0**) is the Speech Rate of the configured Voice at speed 1.0.
It comes from the M1 benchmark renders (Piper `thorsten-medium`). Measured on the three M1
examples, against their unfitted durations (measured trimmed speech plus the deterministic
gaps, pauses and sounds):

| Script | Estimate (nominal) | Measured unfitted | Error | Speech only: est. / measured |
| --- | --- | --- | --- | --- |
| `day` | 377.8 s | 375.5 s | +0.6 % | 95.3 s / 93.0 s (+2.5 %) |
| `sleep` | 601.3 s | 598.3 s | +0.5 % | 66.3 s / 63.3 s (+4.7 %) |
| `short` | 129.2 s | 135.8 s | −4.9 % | 29.8 s / 36.4 s (−18 %) |

On its own, the speech-time estimate for `short` is 18 % low. Its sentences are short
("Ein, zwei, drei, vier."), and Piper reads counted numbers slowly. Speech is only 20 % of that
Session, so the total stays within 5 %. If a Voice or style is consistently off, change
`tts.chars_per_sec` in `anchor.toml`. M7 calibrates it per Voice Profile.

## 4. The Script Request

A Script Request (YAML) describes one Session. M4 will produce requests from the Goal Profile
and the Program. In M2 they are written by hand. Unknown fields are rejected, and all errors are
reported at once with their field paths. A request whose `language` is not a Supported Language
(v1: `de-DE`) is rejected before any LLM call.

```yaml
session_type: day                 # day, sleep, short, cue_recall, rehearsal, pre_event, taster
session_context: stage            # stage (default), orientation, library
stage_ref: stage-1                # optional
method: pmr                       # pmr, autogenic_training, self_hypnosis, mindfulness_body_scan,
                                  # paced_breathing, mental_rehearsal, implementation_intention
guidance_level: guided            # guided, semi_guided, self_guided (Fading, spec §7.3)
target_duration_sec: 600
language: de-DE
goal:                             # Goal Profile essentials only, no names
  pattern: calm_in_situation
  domain: stress                  # optional
  target_situation: Stressige Arbeitstage mit vielen Unterbrechungen und Terminen
  desired_state: Ruhiger und gelassener durch den Arbeitstag gehen
strategies: [calm_competence, ego_strengthening]   # allowed Suggestion Strategies; default none
cue_word_introduced: false        # default false: the Cue Word stays out of prompt and Script
suggestion_ledger:                # optional: Suggestions already used in the Program
  - Ruhig bleiben, auch wenn viele E-Mails kommen
notes: Optional free text for the LLM
style_sheet:                      # Program Style Sheet (FR-49), passed to every generation
  address: du                     # du or Sie
  tone: warm, ruhig, freundlich, nicht belehrend
  imagery: [ein ruhiger See am Morgen]
  cue_word: Gelassen
  cue_word_phrasing: Mit dem Wort „Gelassen“ kehrt die Ruhe zurück.
  situation_vocabulary: [Arbeitstag, Termine, E-Mails, Besprechung]
```

`examples/requests/{day,sleep,short}.yaml` match the three example Scripts. Each pair passes
`anchor validate <script> --request <request>`.

## 5. Generating a Script

```sh
uv run anchor generate examples/requests/day.yaml -o out/day.json [--no-review]
```

1. The request is loaded and validated. The prompts `script.v1` (system and user,
   `src/anchor/generate/prompts/`) are rendered from it. They contain the Session Type rules,
   the Suggestion Rules (spec §8.2), the Style Sheet, the Ledger, the Fading guidance and a
   speech budget. The budget is a range of spoken characters and pause seconds derived from the
   target duration, the pacing profile and `chars_per_sec`.
2. The LLM returns segments only. The schema is in `src/anchor/generate/llm_schema.py`.
   All metadata (`session_type`, `method`, `language`, `target_duration_sec`, …) is filled in
   from the request, never by the LLM.
3. The Script goes through structural validation, then the domain rules (§3), then the LLM
   Suggestion Review (`review.v1`). The review runs only if every rule passed, and `--no-review`
   skips it.
4. On any error, the errors go back to the LLM in the same conversation, as
   `location: rule: message` lines, with a request for a complete corrected Script. Invalid JSON
   counts as an attempt too. This repeats up to `llm.max_attempts` times.
5. On success, the Script is written atomically to `-o`. On failure, the command exits 1, prints
   the errors of the last attempt, and leaves an existing output file unchanged. A refusal or a
   transport failure ends the run immediately.

The summary shows the attempts, the estimated duration against the target, the token usage and
the record path. Generating again from the same request makes new LLM calls and gives a new
variation. Nothing is cached (FR-18).

**Review findings** name a Segment, a rule (`positive_realistic`, `permissive_language`,
`no_absolutes`, `no_medical`, `goal_only`, `cue_word_pairing`, `style_sheet`, `ledger`) and an
explanation. Each finding is reported as `segments[i]: review.<rule>: <explanation>`. A finding
on a Segment that does not exist or is not spoken text is discarded, and kept in the record as an
anomaly. `anchor validate <script> --request <request> --review` runs the same review on any
Script.

## 6. The generation record

Every run writes `<output stem>.generation.json` next to the output (`out/day.json` →
`out/day.generation.json`), on success and on failure. A later run for the same output
overwrites it.

| Field | Content |
| --- | --- |
| `outcome` | `success`, `failed` (all attempts invalid), `refused` or `error` (transport or review failure) |
| `started_at`, `finished_at` | UTC timestamps |
| `request_sha256` | SHA-256 of the parsed request as canonical JSON |
| `models` | `generation` and `review` model ids (`review` is null with `--no-review`) |
| `prompt_versions` | `script` and `review` prompt versions |
| `lexicon_version`, `chars_per_sec` | Versions of the inputs to the domain rules |
| `review` | `enabled` or `skipped` |
| `usage` | Total LLM calls, input tokens and output tokens |
| `errors` | The errors that ended a failed run |
| `attempts[]` | Per attempt: `raw_output` (the LLM's JSON), `errors` (`location`/`rule`/`message`), `review` (findings, anomalies, raw output and usage, or `skipped` with a reason), `usage` per call, `duration_sec`, the duration `estimate`, and `failure` for a refusal or transport error |

## 7. Costs and privacy

**Costs.** One generation makes 1 to `max_attempts` generation calls. With review, it also makes
up to as many review calls, since the review runs only on attempts that passed the rules. Prompts
are a few thousand tokens. A Script answer is a few thousand output tokens, plus thinking at
`effort = "high"`. The record's `usage` shows the actual numbers. `--no-review` and a lower
`effort` reduce the cost.

**Privacy boundary** (spec §12). A request sends the Goal Profile essentials (Pattern, Domain,
target situation, desired state), the Style Sheet, the Ledger and the notes to the configured
LLM Provider, together with the generated Script text during review. The request model has no
field for names, Safety Screening answers, Practice Logs or Outcome Measures, and unknown fields
are rejected, so such data cannot be added by accident. Do not write personal names into
free-text fields. Generation records are local files that hold the same data that was sent.
LLM Consent itself is an M4 flow.

## 8. Acceptance runs (tasks 5.2, 5.3)

### 8.1 Generation, 2026-10-27

Model `litellm_proxy/glm` (self-hosted LiteLLM proxy), for generation and review, with
`effort = "high"`, prompts `script.v1`/`review.v1` and lexicon `de-DE.1`. Commands:
`anchor generate examples/requests/<name>.yaml -o out/<name>.json`.

| Request | Attempts | Errors before success | Review | Calls | Tokens in / out | Estimate (reachable) | Target ±10 % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `short` | 1 | none | 0 findings | 2 | 1742 / 2273 | 144 s (103–200 s) | 162–198 s |
| `day` | 2 | attempt 1: `elements.cue_word` | 0 findings | 3 | 4436 / 12250 | 570 s (403–767 s) | 540–660 s |
| `sleep` | 1 | none | 0 findings | 2 | 2121 / 5247 | 963 s (838–1228 s) | 810–990 s |

`claude-sonnet-5` on the proxy could not be tested: the proxy has no Anthropic key configured for
it. `deepseek-flash` passed a structured-output probe but was not used for generation.

**First impressions** (a short content check, not the listening test):

- `du` is used consistently, the tone is calm, and the suggestions are permissive ("darfst du kurz
  innehalten"). `day` and `short` end with an Emergence. `sleep` has none, ends in a long silent
  practice, and has no end sound.
- The `day` retry was caused by the example request: its Cue Word "Gelassen" is also an everyday
  adjective, so "ruhig und gelassen bleiben" counts as the Cue Word before it is introduced. Real Cue Words
  should be distinctive.
- Borderline phrasing to watch for in the listening test: "Du kommst gut durch diesen Tag."
  (`day`) is close to a promise. The review accepted it.

### 8.2 Render and estimate accuracy, 2026-10-27

Cold renders of the generated Scripts with `anchor render out/<name>.json -o out/<name>.mp3`.
Speaches 0.8.3 with Piper `thorsten-medium` and ffmpeg 9.0.2 (Gyan full build), on the
development machine. The estimate uses `tts.chars_per_sec = 21.0`.

| Script | Output / target | Estimate (nominal) | Render unfitted | Error | Speech est. / measured | Loudness, true peak | Render time |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `short` | 180.0 / 180 s | 143.5 s | 143.7 s | −0.1 % | 29.2 / 29.4 s (−0.6 %) | −18.4 LUFS, −1.9 dBTP | 17.8 s |
| `day` | 600.0 / 600 s | 570.2 s | 565.8 s | +0.8 % | 78.1 / 73.7 s (+6.1 %) | −18.4 LUFS, −1.8 dBTP | 52.1 s |
| `sleep` | 900.0 / 900 s | 963.4 s | 956.7 s | +0.7 % | 90.3 / 83.6 s (+8.0 %) | −18.4 LUFS, −1.9 dBTP | 69.9 s |

All acceptance criteria of task 5.2 hold. Every generation succeeded within `max_attempts`
(1–2 attempts). Every render hit its target exactly, and the fitter had room to spare. The
estimate before fitting is within 1 % of the unfitted render length, where ±15 % is allowed.

The speech-only estimate runs 6–8 % high for `day` and `sleep`. The LLM-written sentences there
are longer than in the hand-written M1 examples, and Piper at speed 0.85–0.9 reads them faster
than 21 characters per second implies. The total stays accurate, because speech is only 13–20 %
of a Session. `chars_per_sec` stays at 21.0.

### 8.3 Listening test and content review, 2026-10-27

**Listener:** the project owner. **Renders:** `out/short.mp3`, `out/day.mp3` and
`out/sleep.mp3` from §8.2. The checklist is the one in `docs/listening-test.md`, plus the
content review from task 5.3 (permissive and realistic Suggestions, `du` throughout, no
over-claiming, Emergence as the Session Type requires).

**Verdict:** passed, for both assembly and content. **Remark:** the voice still sounds generic.
As in M1, this is voice quality and outside the test's scope: an accepted risk that the M7
engine addresses.

**Adjustments:** none. The prompts stay at `script.v1`/`review.v1`, the lexicon at `de-DE.1`,
and `tts.chars_per_sec` at 21.0. The example Cue Word "Gelassen" stays as it is: it caused one
retry in `day` (§8.1), and Practitioners choose their own Cue Word later (M4).

