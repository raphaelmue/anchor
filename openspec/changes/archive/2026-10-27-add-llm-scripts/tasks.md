# Tasks

## 1. Setup

- [x] 1.1 Add `litellm`, pinned to a current release, to `pyproject.toml`, and create the empty packages `anchor/llm/` and `anchor/generate/` (with `prompts/`) and the directory `anchor/script/lexicon/`. Make sure hatch includes `.md`/`.yaml` package data. Verify that `uv sync` succeeds, that `uv run python -c "import litellm, anchor.llm, anchor.generate"` works, and that a built wheel contains the prompt and lexicon files.
- [x] 1.2 Add the `llm` pytest marker to `pyproject.toml` (skipped when the provider's API key is unset). Verify that `uv run pytest -m llm` reports the test as skipped without a key.

## 2. LLM Provider (`llm-provider`)

- [x] 2.1 Add `LLMSettings` (`model`, `review_model`, `effort`, `max_tokens`, `timeout_sec`, `retries`, `backoff_sec`, `max_attempts`; D3) to `Settings`, with a validator that rejects `api_key` under `[llm]` and tells the user to use the environment. Add `tts.chars_per_sec = 21.0`. Update `anchor.example.toml`. Verify unit tests for the defaults, an env override (`ANCHOR_LLM__MODEL`), the "API key in config file" scenario and an empty `review_model` falling back to `model`.
- [x] 2.2 Define the `LLMAdapter` protocol, `LLMResult` (document, raw text, model, input/output tokens, duration) and the error types (`LLMError`, `LLMInvalidOutputError` carrying the raw output, `LLMRefusalError`). Implement `FakeLLMAdapter` with queued documents, raw strings or exceptions and a call log (D12). Verify unit tests for the fake's queueing and call recording, and for invalid raw output raising `LLMInvalidOutputError` with the raw text.
- [x] 2.3 Spike against the pinned LiteLLM version, using `litellm`'s request logging or a mocked HTTP transport. Determine the exact outgoing request for `anthropic/claude-opus-5-5` with a Pydantic `response_format`: whether it uses native structured output or a forced tool (forced tools return HTTP 400 on this model), and how to pass `effort`. Confirm that no `temperature`/`top_p`/`top_k` is sent. Record the findings and the chosen mechanism (D2/D3 fallbacks) in `docs/llm-scripts.md`. Verify a test that asserts the request shape for Anthropic and for an OpenAI model id.
- [x] 2.4 Implement `LiteLLMAdapter.generate_structured` with the mechanism from 2.3:
  - local Pydantic validation of the response
  - refusal detection
  - mapping of LiteLLM exceptions to retry/no-retry (D2) and exponential backoff
  - pre-flight `validate_environment` that names the missing env var
  - usage extraction
  - errors that name provider, model and cause, never the key

  Verify unit tests with mocked `litellm.completion` for every `llm-provider` scenario: valid output, schema mismatch, missing key, 500-then-success, 400 not retried, refusal, no sampling params, usage on success.

## 3. Domain validation (`script-domain-validation`)

- [x] 3.1 Implement the duration estimate (D7) using `load_pacing`, `split_sentences` and `chars_per_sec`, returning fixed/min/max seconds and the pass condition. Verify unit tests for the "target reachable" and "too short" scenarios, plus a test that the estimate for each M1 example Script lies within ±10 % of the unfitted durations measured in M1 (the speech durations in `docs/render-pipeline.md` §9).
- [x] 3.2 Implement the rule engine and the structural rules:
  - `match.*`
  - `emergence.required` and `emergence.forbidden`
  - `elements.strategy` and `elements.cue_word`

  It collects every `DomainIssue(location, rule, message)` in one result. Verify unit tests for "Several violations", "Session Type mismatch", all three Emergence scenarios and both introduced-element scenarios.
- [x] 3.3 Implement the form-of-address rules (D8) and the de-DE language heuristic. Verify unit tests for "formal address in du Script", "informal address in Sie Script", "sentence-initial pronoun not misread", "English segment", and a negative corpus of all speech text in the three example Scripts producing no address or language issues.
- [x] 3.4 Write the de-DE lexicon `lexicon/de-DE.yaml`. It is versioned and has the categories absolute, medical, control and others, with word-boundary regexes. Implement the `suggestion.*` rules on top of it. Verify unit tests for the "guarantee", "medical claim" and "harmless text" scenarios, and a corpus of ≥ 20 permissive German phrasings (examples plus typical Suggestions from spec §8.1) with zero matches.
- [x] 3.5 Align the example Scripts' `method` values with the Method ids (`pmr`, `mindfulness_body_scan`; design Migration Plan). Write `examples/requests/{day,sleep,short}.yaml` matching the three example Scripts, with `du` Style Sheets, goal contexts for `stress`, `sleep_onset` and `calm_in_situation`, and fitting strategies. Verify that `anchor validate` still passes structurally for all three Scripts.
- [x] 3.6 Extend `anchor validate` with `--request` (structural + rule-based domain validation, printing the duration estimate; `--review` follows in 4.4). Verify CLI tests:
  - "hand-written Script checked" with each example Script/request pair, all of which pass
  - an invalid Script listing several `location: rule: message` lines with exit code 1
  - "unchanged structural mode", where the fake adapter records no call
- [x] 3.7 Document the domain rules (rule ids, what each checks, the lexicon and how to tune it, the duration estimate and `chars_per_sec`) in `docs/llm-scripts.md`. Verify that the documented `anchor validate --request` command runs as written.

## 4. Script generation (`script-generation`)

- [x] 4.1 Implement the Script Request and Style Sheet models:
  - YAML loading
  - unknown fields rejected
  - Method id enum
  - Supported Language check
  - defaults
  - every error collected with field paths, in the same format as `validate_script`

  Verify unit tests for "minimal valid request", "unknown Method", "several errors" and "unsupported language".
- [x] 4.2 Implement the LLM-facing segment schema and its mapping to `Script` (D4). The mapping converts `elastic` from an object to a tuple, uses only built-in sound names, and fills metadata from the request. Verify unit tests for the "metadata from request" scenario and that the mapped Script passes `validate_script`.
- [x] 4.3 Write the versioned prompts `script_system.v1.md` and `script_user.v1.md` (D5). They carry the Segment and Session Type rules, the Suggestion Rules, the Style Sheet, the Ledger, Fading guidance and the speech budget computed from D7. Add a renderer. Verify unit tests:
  - "Style Sheet reaches the prompt"
  - "Cue Word without introduction": the Cue Word is absent from the prompt
  - "Ledger in prompt"
  - the speech budget is present
- [x] 4.4 Write the review prompts `review_*.v1.md` and the findings schema, and implement the LLM Suggestion Review (D9): it runs only after rule checks pass, and discards out-of-range or non-spoken indices as anomalies. Add `--review` to `anchor validate --request`. Verify fake-adapter tests for "review finds violation", "review skipped after rule failure" and "review reports out-of-range Segment".
- [x] 4.5 Implement the generation loop (D6):
  - attempts up to `max_attempts`, with the conversation-style error feedback
  - invalid output counts as an attempt; a refusal fails immediately
  - atomic Script write only on success

  Verify fake-adapter tests for "corrected on second attempt" (the second call's history contains the Emergence error), "all attempts invalid" (an existing output file is unchanged), refusal stopping without further attempts, and "second generation" (two calls).
- [x] 4.6 Implement the generation record (D10), written on success and on failure, containing no secrets. Verify tests for "record after success" (two attempts, errors, usage, outcome) and "record after failure", plus an assertion that a set `ANTHROPIC_API_KEY` value does not appear anywhere in the record.
- [x] 4.7 Add `anchor generate <request.yaml> -o <script.json> [--no-review]`, which prints attempts, the estimated duration against the target, tokens and the record path, and exits 1 on failure. Verify CLI tests with the fake adapter for "successful command", "review skipped" and a failing generation.
- [x] 4.8 Document setup (API key env vars, `[llm]` config, model switching), the Script Request format with a full example, the generate command, the record fields, cost notes and the privacy boundary in `docs/llm-scripts.md`. Verify by following the documented steps from a clean checkout with the fake adapter path covered by tests.

## 5. Integration and acceptance

- [x] 5.1 Add the `@pytest.mark.llm` integration test: generate `examples/requests/short.yaml` against the configured model with review, and check that the output passes `anchor validate --request`. Verify that it passes with a key and is skipped without one.
- [x] 5.2 Generate all three example requests against the default model (`litellm_proxy/glm`), then render each with `anchor render` against Speaches. Verify that:
  - each generation succeeds within `max_attempts`
  - each render lands within ±10 % of the target
  - the estimated duration before fitting is within ±15 % of the render's unfitted length

  Record attempts, tokens and estimate accuracy in `docs/llm-scripts.md`.
- [x] 5.3 Run the listening test (`docs/listening-test.md`) on the three generated renders, and add a short content review: Suggestions permissive and realistic, `du` consistent, no over-claiming, Emergence or no Emergence as the Session Type requires. Verify by recording the results, and any prompt, lexicon or `chars_per_sec` adjustments (with version bumps), in `docs/llm-scripts.md`.
