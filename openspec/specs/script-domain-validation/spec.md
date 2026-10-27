# script-domain-validation Specification

## Purpose

Defines the domain rules a structurally valid Session Script must pass, given the Script Request it was written for. These rules keep LLM-written and hand-written Scripts safe, consistent with the Program Style Sheet, and renderable at their target length.

## Requirements

### Requirement: Domain validation runs after structural validation
Domain validation SHALL run only on Scripts that pass structural validation. It SHALL report all rule violations at once, each with the Segment index (or `$` for whole-Script rules), a rule identifier and a message.

#### Scenario: Several violations
- **WHEN** a `day` Script has no Emergence and uses `Sie` although the Style Sheet says `du`
- **THEN** both violations are reported in one result, with rule identifiers and locations

### Requirement: Script matches its request
The Script's `session_type`, `language` and `target_duration_sec` SHALL equal those of the request. Its `method` SHALL also equal the request's, if the Script sets one.

#### Scenario: Session Type mismatch
- **WHEN** a request says `sleep` and the Script says `day`
- **THEN** validation fails with a mismatch error naming both values

### Requirement: Emergence rules
For `day`, `rehearsal` and `pre_event`, the last `speech` Segment SHALL have `role` `emergence`. For `sleep`, no Segment SHALL have `role` `emergence`. Other Session Types have no Emergence constraint.

#### Scenario: Day without Emergence
- **WHEN** a `day` Script's last `speech` Segment has no `role`
- **THEN** validation fails with an Emergence error

#### Scenario: Sleep with Emergence
- **WHEN** a `sleep` Script contains a `speech` Segment with `role` `emergence`
- **THEN** validation fails, and the error identifies that Segment

#### Scenario: Short without Emergence
- **WHEN** a `short` Script has no Emergence
- **THEN** the Emergence rule passes

### Requirement: Only introduced elements
A `speech` Segment's `strategy` SHALL be one of the request's `strategies`. If the request has `cue_word_introduced` false, the Style Sheet's `cue_word` SHALL NOT appear in any spoken text.

#### Scenario: Strategy not introduced
- **WHEN** a Segment has `strategy` `reframe` and the request lists only `calm_competence`
- **THEN** validation fails for that Segment

#### Scenario: Cue Word before introduction
- **WHEN** `cue_word_introduced` is false and a `speech` Segment contains the Cue Word
- **THEN** validation fails for that Segment

### Requirement: Form of address
All spoken text (`speech` text and `silent_practice` prompts) SHALL use the Style Sheet's form of address. With `du`, formal pronouns used as forms of address (`Sie`, `Ihnen`, `Ihr`, `Ihre`, … capitalized mid-sentence) SHALL be flagged. With `Sie`, informal pronouns (`du`, `dich`, `dir`, `dein`, …) SHALL be flagged.

#### Scenario: Formal address in du Script
- **WHEN** the Style Sheet says `du` and a Segment says "Atmen Sie ruhig ein."
- **THEN** validation fails for that Segment with a form-of-address error

#### Scenario: Informal address in Sie Script
- **WHEN** the Style Sheet says `Sie` and a Segment says "Lass dir Zeit."
- **THEN** validation fails for that Segment

#### Scenario: Sentence-initial pronoun not misread
- **WHEN** the Style Sheet says `du` and a Segment says "Die Hände werden warm. Sie werden schwer." (third-person "sie" at sentence start)
- **THEN** no form-of-address error is reported

### Requirement: Duration estimate
The estimated duration SHALL be computed before rendering, as the sum of:
- speech time: characters ÷ (configured Speech Rate × the Session Type's pacing speed)
- the pacing profile's sentence and segment gaps
- fixed pause lengths

Elastic Pauses contribute their full range. If the reachable range does not overlap the target ±10 %, validation SHALL fail with the estimate, the reachable range and the target.

#### Scenario: Target reachable
- **WHEN** the estimated range is 520–700 s and the target is 600 s
- **THEN** the duration rule passes, and the estimate is reported

#### Scenario: Too short
- **WHEN** the estimated range is 200–380 s and the target is 600 s
- **THEN** validation fails, naming the reachable range and the allowed range 540–660 s

### Requirement: Language consistency
All spoken text SHALL be in the request's language. For `de-DE`, a Segment whose text looks predominantly English by a stopword heuristic SHALL be flagged.

#### Scenario: English segment
- **WHEN** a `de-DE` Script contains a Segment "Take a deep breath and relax your shoulders."
- **THEN** validation fails for that Segment with a language error

### Requirement: Rule-based Suggestion Rules
All spoken text SHALL be checked against a curated, versioned lexicon for the request's language. The lexicon flags:
- guarantees and absolutes (e.g. "nie wieder", "garantiert", "du wirst bestehen")
- medical or therapeutic claims and terms (diagnoses, medication, therapy, trauma)
- commands implying loss of control
- references to other people as targets of change

Each match SHALL be reported with the Segment index, the rule category and the matched phrase.

#### Scenario: Guarantee
- **WHEN** a Segment says "Du wirst nie wieder nervös sein."
- **THEN** validation fails for that Segment in the category guarantees/absolutes, naming "nie wieder"

#### Scenario: Medical claim
- **WHEN** a Segment says "Diese Übung heilt deine Schlafstörung."
- **THEN** validation fails for that Segment in the category medical claims

#### Scenario: Harmless text
- **WHEN** a Segment says "Vielleicht bemerkst du, wie dein Atem ruhiger wird."
- **THEN** no Suggestion Rule violation is reported

### Requirement: LLM Suggestion Review
When enabled, a Script that passes all rule-based checks SHALL be reviewed by an LLM. The LLM checks every spoken Segment against the Suggestion Rules (spec §8.2), including:
- permissive language
- realistic, process-focused framing
- the Cue Word paired only with calm or helpful action
- consistency with the Style Sheet and the Suggestion Ledger

Each reported violation SHALL name a Segment index, a rule and an explanation, and SHALL count as a validation error.

#### Scenario: Review finds violation
- **WHEN** the review reports that Segment 7 pairs the Cue Word with a stressful image
- **THEN** validation fails with an error at Segment 7 citing the Cue Word rule and the explanation

#### Scenario: Review skipped after rule failure
- **WHEN** a Script fails a rule-based check
- **THEN** no review call is made for that attempt

#### Scenario: Review reports out-of-range Segment
- **WHEN** the review names a Segment index that does not exist or is not spoken text
- **THEN** that finding is discarded and recorded as a review anomaly, not reported as a Script error

### Requirement: Domain validation command
`anchor validate <script.json> --request <request.yaml>` SHALL run structural and rule-based domain validation. With `--review`, it SHALL also run the LLM Suggestion Review. It SHALL print all errors and the duration estimate, and exit non-zero on any error. Without `--request`, it SHALL behave as before (structural only).

#### Scenario: Hand-written Script checked
- **WHEN** `anchor validate examples/scripts/day.json --request examples/requests/day.yaml` runs
- **THEN** it prints the duration estimate and either "valid" or every rule violation

#### Scenario: Unchanged structural mode
- **WHEN** `anchor validate script.json` runs without `--request`
- **THEN** only structural validation runs, and no LLM is contacted
