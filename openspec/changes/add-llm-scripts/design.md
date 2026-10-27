# Design

## Context

M1 (`add-render-pipeline`, implemented, not yet archived) delivered `anchor.script` (Pydantic Script v1.2, structural validation that collects every error with its location), `anchor.audio.pacing` (per-Session-Type speed and gaps), `anchor.audio.sentences` (German sentence splitting), the render pipeline and the CLI. Config is `anchor.toml` plus `ANCHOR_` env overrides via pydantic-settings, with secrets as `SecretStr`. The Script format, the CLI style and the library-first layout carry over unchanged.

Constraints:
- The user chose **LiteLLM** as the provider layer, so Anthropic and OpenAI both work through configuration.
- On the current Anthropic API, Messages requests that send `temperature`/`top_p`/`top_k` return HTTP 400 (since 2026-10-21). The `temperature=0.7` in the spec §10.1 `LLMAdapter` sketch is therefore dropped.
- Speech Rate from the M1 benchmark renders (trimmed speech): `day` 1832 chars / 93.0 s at speed 0.9, `sleep` 1208 / 63.3 s at 0.85, `short` 601 / 36.4 s at 0.95. That is ≈ 22, 22.5 and 17.4 chars/s at speed 1.0.

## Goals / Non-Goals

**Goals:**
- A library first (`anchor.llm`, `anchor.generate`, `anchor.script.domain`), reusable unchanged by M4 and the M5 worker. The CLI stays a thin layer.
- Every test runs offline and deterministically against a fake LLM Adapter.
- Domain rules are usable on their own, for hand-written Scripts too.

**Non-Goals:**
- Async or parallel generation, caching of LLM outputs, and the Batches API.
- Prompt caching tuning. Prompts are small (a few thousand tokens), so prompt caching is not worth tuning yet.
- Validators that need Blueprints or Stage history: "only introduced elements" beyond what the request lists, Formula integrity, and Fading rules per Guidance Level.
- Persisting the Suggestion Ledger or extracting Suggestions from Scripts into it (M4).

## Decisions

### D1 — Module layout
```
anchor/llm/        base.py (LLMAdapter protocol, LLMResult, errors), litellm_adapter.py, fake.py
anchor/generate/   request.py (Script Request + Style Sheet models), prompts/ (versioned .md),
                   llm_schema.py (LLM-facing segment schema), loop.py (generate/retry), record.py
anchor/script/     domain.py (rule engine), lexicon/de-DE.yaml (Suggestion Rule lexicon),
                   duration.py (estimate)
```
The domain rules live in `anchor.script` because they validate Scripts. Generation depends on them, not the other way round.

### D2 — LiteLLM adapter with Pydantic-validated output
`LLMAdapter.generate_structured(system, user, schema: type[BaseModel], *, model) -> LLMResult[T]`.

The implementation calls `litellm.completion(model=..., messages=[system, user], response_format=<JSON schema derived from the Pydantic model>, timeout=..., num_retries=0)`. It then validates the returned text locally with `schema.model_validate_json`, even when the provider enforced the schema, because a refusal or truncation (`max_tokens`) can still produce invalid output.

Errors are mapped from LiteLLM's exception types:
- `RateLimitError`, `Timeout`, `APIConnectionError`, `InternalServerError` → retry
- `BadRequestError`, `AuthenticationError`, `NotFoundError` → no retry

Retries are our own exponential backoff (same parameters as the TTS adapter). LiteLLM's `num_retries` stays 0, so one setting controls retrying.

Refusals are detected from the finish reason (`stop_reason: "refusal"` on Anthropic, a `refusal` field on OpenAI) and raised as `LLMRefusalError`.

*Alternatives:* the official Anthropic SDK with `messages.parse()` gives the most direct control and native structured outputs, but needs a second adapter for OpenAI. The user chose LiteLLM to cover both. Instructor adds a dependency on top of LiteLLM for what local Pydantic validation already does.

*Risk:* how LiteLLM translates `response_format` for Anthropic (native structured outputs or a forced tool) depends on its version. Forced `tool_choice` returns HTTP 400 on `claude-opus-5-5`. Task 2.3 verifies the actual request shape against the pinned LiteLLM version before anything builds on it (see Risks).

### D3 — Model configuration
```toml
[llm]
model = "litellm_proxy/glm"           # LiteLLM provider/model id
review_model = ""                     # empty = same as model
effort = "high"                       # sent to anthropic/* and litellm_proxy/*; omitted when empty
max_tokens = 16000
timeout_sec = 300
retries = 3
backoff_sec = 1.0
max_attempts = 3                      # generation attempts with error feedback (FR-16)
```

The default model runs on the user's self-hosted LiteLLM proxy (decided 2026-10-27, after the M2 spike: no Anthropic key is available; the proxy offers `glm`, `deepseek-flash` and `claude-sonnet-5`, and `glm` passed the integration test). API keys come from the provider's standard env vars, which LiteLLM reads natively (`LITELLM_PROXY_API_KEY` plus `LITELLM_PROXY_API_BASE`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`); LiteLLM also loads a `./.env` file, which is git-ignored. `LLMSettings` has no key field, and `extra="forbid"` plus a validator rejects `api_key` under `[llm]` with a helpful message. A pre-flight check uses `litellm.validate_environment(model)` to fail before any call, and additionally requires `LITELLM_PROXY_API_BASE` for `litellm_proxy/*`: LiteLLM would otherwise send the request, with the proxy key, to api.openai.com.

`effort`: `claude-opus-5-5` always thinks, and its effort default is `medium`. Script writing is quality-sensitive, so the default is `high`. LiteLLM may not map `output_config.effort`. Task 2.3 determines how to pass it (e.g. LiteLLM's `reasoning_effort` mapping or provider-specific `extra_body`). If neither works, the setting is dropped with a warning rather than sent wrongly. Sampling parameters are never sent (spec `llm-provider`).

### D4 — The LLM writes segments only; a dedicated LLM-facing schema
The LLM returns `{"segments": [...]}` against a schema in `llm_schema.py`. That schema is close to Segment v1.2, with three differences:
- `elastic` is an object `{min, max}` instead of a tuple. Tuple schemas (`prefixItems`) are poorly supported by structured-output implementations.
- `ambience`/`marker` are omitted: the LLM has no use for them in M2.
- `sound` is limited to the built-in names (`bell_soft`).

Generation maps the result to the real `Script` model and fills all metadata from the request. Then the existing `validate_script` runs, followed by domain validation.

*Why:* the metadata must be right by construction, not by retry (spec "Metadata from request"). A smaller schema also means fewer ways to fail.

*Alternative:* let the LLM emit the full Script and overwrite the metadata. That wastes tokens and invites mismatches that look like errors.

### D5 — Prompts are versioned package files
`anchor/generate/prompts/script_system.v1.md` and `script_user.v1.md`, plus `review_system.v1.md` and `review_user.v1.md`. They are rendered with plain `str.format_map` over a context built from the request; no template engine is needed. The prompt version (`script.v1`, `review.v1`) goes into the generation record. Changing a prompt means a new file and a version bump, never an edit in place. This keeps NFR-7 and the spec §7.5 "pinned prompt versions" possible.

The system prompt is in English, because instruction following is better and easier to review. It demands that all spoken text be in the request's language. It carries:
- the Segment rules: ≤ 300 chars per speech Segment, pauses only as `pause`/`silent_practice` Segments, never written into text
- the Session Type rules: Emergence, sleep without end sound
- the Suggestion Rules (§8.2) verbatim
- the Style Sheet
- Fading guidance per Guidance Level (§7.3), as instruction only, not validated
- a **speech budget**: target speech characters derived from the duration estimate (D7), so that the first attempt is usually the right length

### D6 — Retry with error feedback as a conversation
Attempt *n* > 1 sends the original system and user prompts, the previous assistant output, and a user message listing every error as `location: rule: message`, asking for a complete corrected Script. A conversation rather than a fresh prompt lets the model fix specific Segments instead of rewriting from scratch. The history is append-only, which keeps provider-side prompt caching and thinking-block rules happy.

Invalid JSON or schema errors (D2) count as an attempt, with the parse error as feedback. Refusals and transport failures do not count as attempts: a refusal fails generation immediately, and a transport failure fails after the adapter's retries.

### D7 — Duration estimate reuses the render pacing
`estimate(script, pacing, chars_per_sec) -> (fixed_sec, min_sec, max_sec)`. It splits speech with `split_sentences` and adds:
- the speech time `len(sentence) / (chars_per_sec × profile.speed)`
- `sentence_gap_sec` between sentences and `segment_gap_sec` between Segments
- `pause`/`silent_practice` seconds, at their elastic min/max
- a `silent_practice` prompt, which counts as speech
- `bell_soft`, at its known length

Pass condition: `[min, max]` overlaps `[0.9 × target, 1.1 × target]`. This mirrors the fitting in `render/fit.py`.

`tts.chars_per_sec = 21.0` (at speed 1.0) is the default, taken from the M1 measurements (Context). It sits between the `short` and `day`/`sleep` values: `short` has more, shorter sentences, so its trim margins weigh more. The estimate is checked against the three M1 renders in a test (each within ±10 % of the measured output before fitting). The speech budget for the prompt is `(target − pauses at their seconds − gaps) × chars_per_sec × speed`, given as a range.

*Alternative:* render to measure. That is too slow for a validation loop and needs the TTS Backend.

### D8 — Rule-based checks and the lexicon
Each rule is a function `(script, request, ctx) -> list[DomainIssue]` with a stable rule id: `match.session_type`, `emergence.required`, `emergence.forbidden`, `elements.strategy`, `elements.cue_word`, `address.du`, `address.sie`, `duration.range`, `language.de`, `suggestion.absolute`, `suggestion.medical`, `suggestion.control`, `suggestion.others`. All rules run, and every issue is collected; the output matches the existing `ValidationIssue` format.

- **Form of address:** tokenize each sentence. In `du` mode, flag `Sie|Ihnen|Ihr|Ihre|Ihren|Ihrem|Ihrer|Ihres` when capitalized and not sentence-initial. Sentence-initial "Sie" is ambiguous ("Sie werden schwer" can mean "they"), so it is only flagged when the next token is a verb in the imperative/formal pattern (`<Verb> Sie` order, e.g. "Atmen Sie"). This is detected by "Sie" directly after the sentence's first token. In `Sie` mode, flag `du|dich|dir|dein*|euch|euer*` case-insensitively.
- **Language:** the ratio of English to German stopwords per Segment. Flag when English stopwords ≥ 3 and outnumber the German ones.
- **Lexicon** (`lexicon/de-DE.yaml`, with `version`): per category, a list of regex patterns with word boundaries, matched case-insensitively on NFC text. The lexicon is curated content, like the Scope Pre-Check rules later, and is reviewed as content. Its version goes into the generation record.

*Trade-off:* the lexicon is deliberately conservative (precision over recall). The LLM Review (D9) covers the subtle cases.

### D9 — LLM Suggestion Review
This is a separate call with its own prompt and schema: `{"findings": [{"segment_index": int, "rule": enum, "explanation": str}]}`. `rule` is an enum of the §8.2 rules. The input is the spoken Segments with their indices, the Style Sheet, the Ledger and the goal context. The review runs only if all rule-based checks passed (saves cost; spec scenario). Findings on non-existent or non-spoken indices are discarded and recorded as anomalies.

The review uses `review_model`, which defaults to the generation model. A model reviewing its own output is weaker than an independent reviewer, but configuring another provider is one line.

*Alternative:* let the generation model self-check in the same call. That is cheaper, but it can't be enforced or recorded separately.

### D10 — Generation record and atomic output
`<output>.generation.json` is written for every run (success or failure). It contains:
- `request_sha256` (canonical JSON of the parsed request)
- `models`, `prompt_versions`, `lexicon_version`, `chars_per_sec`
- `attempts[]` with `raw_output`, `errors[]`, `review` (`findings`/`anomalies`/`skipped`), `usage`, `duration_sec`
- `outcome`, `started_at`

The Script is written to a temp file and renamed into place only on success, following M1's `render/output.py` pattern. The record is written last. An earlier record for the same output is overwritten. Records are local files, and they contain the goal context, which is the same data that was sent to the provider.

### D11 — CLI
`anchor generate <request.yaml> -o <script.json> [--no-review]` loads settings and the request, builds the adapter, runs the loop and prints a summary. `anchor validate` gains `--request` and `--review`. Exit codes follow M1: 0 for ok, 1 for validation or generation failure. Errors print to stderr as `location: rule: message`.

### D12 — Testing
- `FakeLLMAdapter` returns queued responses (documents, raw strings, or exceptions), records every call (system, user, history, model), and reports fake usage. All loop, record and CLI tests use it.
- LiteLLM adapter tests mock `litellm.completion` to cover the error mapping, the retry policy, refusal detection, and the absence of sampling params.
- `@pytest.mark.llm` integration test: it generates the `short` example request against the configured model and validates the output. It is skipped without the provider's API key.

## Risks / Trade-offs

- **[LiteLLM translates `response_format` for Anthropic into a forced tool call, which `claude-opus-5-5` rejects with 400]** → Task 2.3 inspects the outgoing request with the pinned version first. Fallbacks, in order:
  1. pass Anthropic structured output natively (`output_config.format`) via LiteLLM's provider-specific parameters
  2. JSON-in-text with a schema in the prompt, plus local validation
  
  Local Pydantic validation keeps any of these correct. Only the retry rate changes.
- **[Duration estimate off for other Voices]** → `chars_per_sec` is configurable per installation; M7 calibrates it per Voice Profile. The estimate is a gate with ±10 % slack, and the mixer's elastic fitting still applies at render time.
- **[Lexicon false positives block good Scripts]** → Conservative patterns, a test corpus of allowed phrases (examples plus typical permissive phrasings), and rule ids in every error so a pattern can be tuned quickly. The user can run `anchor validate --request` on hand-written text to check the lexicon.
- **[Form-of-address heuristic misses or misfires on sentence-initial "Sie"]** → Explicit test cases. The LLM Review covers Style Sheet consistency as a second net.
- **[Self-review by the same model is lenient]** → The review model is configurable, and review findings are recorded, so leniency is visible in the records.
- **[Cost of retries and review on a paid API]** → `max_attempts` default 3, review only after rule-based checks pass, token usage in every summary and record.
- **[Goal context leaves the server]** → Requests carry only Goal Profile essentials and the Style Sheet (spec §12). The request model has no field for names, screening answers or logs. LLM Consent itself is an M4 flow.
- **[`add-render-pipeline` not archived]** → No dependency on archived specs: this change adds new capabilities only. Archive M1 before or after; the order does not matter.

## Migration Plan

Purely additive: new config section with defaults, new commands, and a new `--request` option on `validate`. Existing config files, Scripts and `anchor render` behave as before.

One adjustment to the examples: the example Scripts use free-form method names. They should become Method ids (spec §2.2) so that they match their example requests:
- `day.json`: `progressive_muscle_relaxation` → `pmr`
- `sleep.json`: `body_scan` → `mindfulness_body_scan`

Script Requests accept only the seven Method ids. Availability (`enabled`/`planned`) is not enforced until the Method Catalog exists (M3).

## Open Questions

- The final `chars_per_sec` default may shift once the target server and more Voices are measured. This only changes a config default.
