# Spec Delta

## Purpose

Turns a Script Request into a validated Session Script written by an LLM. The request describes the Session, the goal context and the Program Style Sheet. Every returned Script has passed structural and domain validation, and an invalid one never leaves the system.

## ADDED Requirements

### Requirement: Script Request document
A Script Request SHALL be a YAML document with these required fields: `session_type`, `method`, `guidance_level` (`guided`, `semi_guided`, `self_guided`), `target_duration_sec`, `language`, `goal` (Goal Pattern, optional Goal Domain, target situation, desired state) and `style_sheet`. It SHALL accept the optional fields `session_context` (default `stage`), `stage_ref`, `strategies`, `cue_word_introduced` (default false), `suggestion_ledger` and `notes`.

#### Scenario: Minimal valid request
- **WHEN** a request has all required fields and no optional ones
- **THEN** it is accepted, with `session_context` `stage`, no Strategies and the Cue Word not introduced

### Requirement: Script Request validation
Unknown fields and invalid values in a Script Request SHALL be rejected. `method` SHALL be a Method id. All errors SHALL be reported at once, each with its field path.

#### Scenario: Unknown Method
- **WHEN** a request has `method` `progressive_muscle_relaxation`
- **THEN** it is rejected with an error listing the Method ids (`pmr`, `autogenic_training`, `self_hypnosis`, `mindfulness_body_scan`, `paced_breathing`, `mental_rehearsal`, `implementation_intention`)

#### Scenario: Several errors
- **WHEN** a request has an unknown `session_type` and no `style_sheet`
- **THEN** both errors are reported with their field paths

### Requirement: Supported language only
A request whose `language` is not a Supported Language (v1: `de-DE`) SHALL be rejected before any LLM call, with an error listing the supported languages.

#### Scenario: Unsupported language
- **WHEN** a request declares `language` `en-US`
- **THEN** it is rejected without contacting the LLM Provider, and the error names `de-DE`

### Requirement: Program Style Sheet
The `style_sheet` SHALL contain these fields:
- `address` (`du` or `Sie`)
- `tone`
- optional `imagery` (list of recurring images)
- optional `cue_word` and `cue_word_phrasing`
- optional `situation_vocabulary` (list)

The whole Style Sheet SHALL be passed to the LLM for every generation.

#### Scenario: Style Sheet reaches the prompt
- **WHEN** a request's Style Sheet has `address` `Sie` and `imagery` ["Strand am Morgen"]
- **THEN** the prompt sent to the LLM contains the form of address and the imagery

#### Scenario: Cue Word without introduction
- **WHEN** a Style Sheet names a `cue_word` but `cue_word_introduced` is false
- **THEN** the request is accepted, and the prompt does not contain the Cue Word

### Requirement: Suggestion Ledger context
If a request has a `suggestion_ledger` (a list of Suggestion summaries already used in the Program), it SHALL be passed to the LLM, with the instruction to stay consistent with it and not contradict it.

#### Scenario: Ledger in prompt
- **WHEN** a request has a `suggestion_ledger` with two entries
- **THEN** both entries appear in the prompt sent to the LLM

### Requirement: Generated Script
On success, generation SHALL produce a Session Script v1.2. The fields `schema_version`, `session_type`, `session_context`, `language`, `goal_pattern`, `goal_domain`, `method`, `guidance_level`, `target_duration_sec` and `stage_ref` SHALL be taken from the request, not from the LLM. The Script SHALL be written atomically to the output path.

#### Scenario: Metadata from request
- **WHEN** a request with `session_type` `sleep` and `method` `pmr` generates successfully
- **THEN** the output Script has `session_type` `sleep` and `method` `pmr`, whatever the LLM returned

#### Scenario: Output passes validation
- **WHEN** generation succeeds
- **THEN** `anchor validate <script> --request <request>` succeeds on the output, and `anchor render` accepts it

### Requirement: Retry with error feedback
If a generated Script fails structural validation, domain validation or the Suggestion Review, generation SHALL send the errors back to the LLM and request a corrected Script. It SHALL do so up to a configured maximum number of attempts (default 3).

#### Scenario: Corrected on second attempt
- **WHEN** the first attempt lacks a required Emergence and the second attempt is valid
- **THEN** generation succeeds after two attempts, and the second request contained the Emergence error

### Requirement: Visible failure
If no attempt yields a valid Script, generation SHALL fail with a non-zero exit status. It SHALL report the errors of the last attempt and SHALL NOT write or overwrite the output Script.

#### Scenario: All attempts invalid
- **WHEN** all configured attempts produce Scripts that cannot reach the target duration
- **THEN** the command exits non-zero, prints the duration errors, and an existing output file is unchanged

### Requirement: Generation record
Every generation, successful or failed, SHALL write a generation record (JSON) next to the output path. The record SHALL contain:
- model(s) and prompt version
- a hash of the request
- per attempt: raw LLM output, validation errors, review result, token usage and duration
- the final outcome

It SHALL NOT contain API keys.

#### Scenario: Record after success
- **WHEN** generation succeeds after two attempts
- **THEN** the record lists both attempts, the errors of the first, the token usage of all calls and outcome `success`

#### Scenario: Record after failure
- **WHEN** generation fails
- **THEN** a record with outcome `failed` and all attempts is still written

### Requirement: Regenerate
Generating again from the same request SHALL produce a new variation, and SHALL NOT return a cached earlier result (FR-18).

#### Scenario: Second generation
- **WHEN** the same request is generated twice
- **THEN** two LLM generation calls are made, and each run writes its own generation record

### Requirement: Generate command
The CLI SHALL provide `anchor generate <request.yaml> -o <script.json>` with an option to skip the Suggestion Review (`--no-review`). On success it SHALL print the attempt count, the estimated duration against the target, the token usage and the record path.

#### Scenario: Successful command
- **WHEN** `anchor generate examples/requests/day.yaml -o out/day.json` succeeds
- **THEN** `out/day.json` and its generation record exist, and the summary shows attempts, estimated duration and tokens

#### Scenario: Review skipped
- **WHEN** the command runs with `--no-review`
- **THEN** no Suggestion Review call is made, and the record marks the review as skipped
