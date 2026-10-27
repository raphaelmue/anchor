# Spec Delta

## Purpose

Defines the Session Script document — the machine-readable, ordered list of Segments that describes one Session — and the structural validation every Script must pass before it can be rendered.

## ADDED Requirements

### Requirement: Script document structure
A Session Script SHALL be a JSON document with `schema_version`, `session_type`, `language`, `target_duration_sec` and a non-empty ordered `segments` list. Optional metadata fields (`session_context`, `goal_pattern`, `goal_domain`, `method`, `guidance_level`, `stage_ref`, `content_snapshot`) SHALL be accepted and preserved but not interpreted by rendering.

#### Scenario: Minimal valid script
- **WHEN** a Script contains `schema_version` "1.2", `session_type` "day", `language` "de-DE", `target_duration_sec` 300 and one `speech` Segment
- **THEN** validation succeeds

#### Scenario: Missing required field
- **WHEN** a Script has no `target_duration_sec`
- **THEN** validation fails with an error naming the missing field

#### Scenario: Empty segment list
- **WHEN** a Script has an empty `segments` list
- **THEN** validation fails

### Requirement: Supported schema version
The system SHALL accept Scripts with `schema_version` "1.2" and SHALL reject any other version with an error stating the supported version.

#### Scenario: Unsupported version
- **WHEN** a Script declares `schema_version` "1.1"
- **THEN** validation fails with an error that names "1.2" as the supported version

### Requirement: Session Types
`session_type` SHALL be one of `day`, `sleep`, `short`, `cue_recall`, `rehearsal`, `pre_event`, `taster`. Unknown values SHALL be rejected.

#### Scenario: Unknown session type
- **WHEN** a Script declares `session_type` "nap"
- **THEN** validation fails with an error listing the allowed Session Types

### Requirement: Segment types
Each Segment SHALL have a `type` of `speech`, `pause`, `silent_practice`, `sound`, `ambience` or `marker`, and SHALL carry the fields its type requires: `speech` → `text`; `pause` → `seconds`; `silent_practice` → `seconds` and optional `prompt`; `sound` → `sound`; `ambience` → `ambience`; `marker` → `name`.

#### Scenario: Pause without seconds
- **WHEN** a `pause` Segment has no `seconds`
- **THEN** validation fails and the error identifies the Segment by its index

#### Scenario: Unknown segment type
- **WHEN** a Segment has `type` "music"
- **THEN** validation fails

### Requirement: Speech segment text limits
A `speech` Segment's `text` SHALL be non-empty after trimming and at most 300 characters. Optional `style`, `role` (`induction`, `deepening`, `emergence`) and `strategy` fields SHALL be accepted.

#### Scenario: Speech text too long
- **WHEN** a `speech` Segment's `text` has 301 characters
- **THEN** validation fails and the error identifies the Segment by its index

#### Scenario: Speech with role
- **WHEN** a `speech` Segment has `role` "emergence"
- **THEN** validation succeeds

### Requirement: Formula references not yet supported
A `speech` Segment that references a `formula` instead of literal `text` SHALL be rejected with an error stating that Formula references require the content base.

#### Scenario: Formula reference
- **WHEN** a `speech` Segment contains `formula` "at.rest.01" and no `text`
- **THEN** validation fails with an error mentioning that Formulas are not yet supported

### Requirement: Elastic Pauses
`pause` and `silent_practice` Segments MAY carry `elastic: [min, max]` in seconds. The range SHALL satisfy `0 <= min <= seconds <= max`; otherwise validation SHALL fail.

#### Scenario: Valid elastic range
- **WHEN** a `pause` Segment has `seconds` 15 and `elastic` [10, 25]
- **THEN** validation succeeds

#### Scenario: Seconds outside elastic range
- **WHEN** a `pause` Segment has `seconds` 30 and `elastic` [10, 25]
- **THEN** validation fails

### Requirement: Validation error reporting
Validation SHALL report all structural errors found in a Script at once, each with its location (field path or Segment index), rather than stopping at the first error.

#### Scenario: Multiple errors
- **WHEN** a Script has an unknown `session_type` and a `pause` Segment without `seconds`
- **THEN** both errors are reported in a single validation result
