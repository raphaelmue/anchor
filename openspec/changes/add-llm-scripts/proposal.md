# Proposal

## Why

M1 renders hand-written Session Scripts, but the product depends on Scripts written by an LLM within strict guardrails (`docs/spec.md` §1, FR-15–FR-17, §8). M2 (§14) has to show that an LLM can produce Scripts that are valid, safe and the right length, before Goal Analysis and Programs (M4) start generating them in bulk. The risks are invalid JSON, drift in tone and form of address, unsafe or over-claiming Suggestions, and Scripts that cannot reach their target duration (§13 "LLM").

## What Changes

- A provider-agnostic **LLM Adapter** (spec §10.1) for structured JSON generation, built on LiteLLM so Anthropic and OpenAI models both work through configuration. The default model is `litellm_proxy/glm` on the self-hosted LiteLLM proxy; Anthropic (`anthropic/claude-opus-5-5`) and OpenAI models are one config line away. API keys come from the environment only.
- A hand-written **Script Request** (YAML). It holds everything M4 will later supply: Session Type, Session Context, Method, Guidance Level, target duration, language, Goal Profile essentials, allowed Suggestion Strategies, whether the Cue Word has been introduced, and the **Program Style Sheet** (FR-49). An optional **Suggestion Ledger** summary (FR-50) can be added.
- **Script generation**: Script Request → versioned prompt → LLM → Session Script v1.2. Metadata is filled in deterministically, never by the LLM. Domain validation runs next. An invalid Script is retried with the error feedback, up to a configurable limit, and then fails visibly with all errors (FR-16).
- A **domain validator** (FR-17) that runs on top of the existing structural validation:
  - Emergence rules per Session Type
  - only introduced elements (Strategies, Cue Word)
  - form of address matching the Style Sheet (`du`/`Sie`)
  - a pre-render duration estimate (speech characters ÷ Speech Rate + gaps + fixed and Elastic Pauses), checked against the target ±10 %
  - a language-consistency heuristic
  - rule-based Suggestion Rule checks (§8.2) from a curated de-DE lexicon
- An **LLM Suggestion Review**: a second LLM call checks the spoken text against the Suggestion Rules (§8.2) and reports violations per Segment. Violations count as validation errors, so they go through the same retry loop.
- A **generation record** next to every generated Script: model, prompt version, request hash, attempts, errors per attempt, token usage and raw outputs. It serves reproducibility (NFR-7) and debugging.
- CLI:
  - `anchor generate <request.yaml> -o <script.json>`
  - `anchor validate <script.json> --request <request.yaml> [--review]` runs domain validation on any Script, including hand-written ones.
- A configurable **Speech Rate** (`chars_per_sec` at speed 1.0) for the configured Voice. The default (≈ 21) is derived from the M1 benchmark renders; calibration on preview is M7.
- Example Script Requests (`day`, `sleep`, `short`), and documentation in `docs/llm-scripts.md`.

Out of scope:
- Goal Analysis, Scope Pre-Check, LLM Consent and Program generation, including generating the Style Sheet itself (M4)
- Formulas and the Content Snapshot (M3): Formula references stay rejected
- Persistence beyond files (M5)
- Speech Rate calibration (M7)
- Validator rules that need Blueprints or Stage history (M3/M4)

## Capabilities

### New Capabilities

- `llm-provider`: structured JSON generation through a configurable LLM Provider, including model selection, credentials, retries on transient errors, error reporting and usage reporting.
- `script-generation`: the Script Request document (including the Program Style Sheet and Suggestion Ledger inputs) and turning it into a validated Session Script, with retry with error feedback, a visible failure and a generation record.
- `script-domain-validation`: the domain rules a Session Script must pass on top of structural validation, given a Script Request. This covers Emergence, introduced elements, form of address, duration estimate, language and the Suggestion Rules, both rule-based and as an LLM review.

### Modified Capabilities

(none — the Session Script format is unchanged. `session-script` from `add-render-pipeline` is not yet archived into `openspec/specs/`, and this change does not alter its requirements.)

## Impact

- New code: `src/anchor/llm/` (adapter, fake adapter), `src/anchor/generate/` (request model, prompts, generation loop, record), `src/anchor/script/domain.py` (domain rules), and the CLI commands in `src/anchor/cli.py`. Prompts and the de-DE Suggestion Rule lexicon are added as versioned package data.
- Config: a new `[llm]` section, and `tts.chars_per_sec` in `anchor.toml` / `anchor.example.toml`.
- New runtime dependency: `litellm`, pinned.
- External calls: the Script Request's goal context and the generated Script text are sent to the configured LLM Provider. This matches spec §12: only Goal Profile essentials, Style Sheet and Ledger, and no names. Safety Screening answers, Practice Logs and Outcome Measures are never part of a request.
- Costs: each generation makes 1–N generation calls plus 1–N review calls against a paid API.
- Tests: a fake LLM Adapter keeps every test offline. One opt-in integration test (`@pytest.mark.llm`) runs only when an API key is set.
