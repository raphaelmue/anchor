# Spec Delta

## Purpose

Stores rendered speech content-addressed so identical speech with identical Voice settings is synthesized once and reused, reducing CPU render time and keeping canonical phrases acoustically identical across Sessions.

## ADDED Requirements

### Requirement: Content-addressed key
Each cached speech unit SHALL be keyed by a hash over: the normalized text, the text-normalization version, backend ID, model ID, Voice ID, speed, style instruction, seed and sample rate. Any difference in one of these SHALL produce a different key.

#### Scenario: Same input, same key
- **WHEN** the same sentence is rendered twice with identical Voice settings
- **THEN** both renders use the same cache key

#### Scenario: Speed changes the key
- **WHEN** the same sentence is rendered with speed 1.0 and with speed 0.9
- **THEN** two different cache keys are used

#### Scenario: Engine upgrade changes the key
- **WHEN** the configured model ID changes
- **THEN** previously cached audio is not reused for the new model

### Requirement: Cache hit skips synthesis
Before synthesizing, the system SHALL look up the key; on a hit it SHALL use the stored audio and SHALL NOT call the TTS Backend.

#### Scenario: Second render is fully cached
- **WHEN** the same Script is rendered twice with unchanged settings
- **THEN** the second render makes no TTS Backend calls and reports only cache hits

### Requirement: Text normalization before keying
Text SHALL be normalized (Unicode NFC, collapsed whitespace, trimmed) before keying, so formatting-only differences hit the same entry.

#### Scenario: Whitespace differences
- **WHEN** "Atme  ruhig." and "Atme ruhig. " are rendered with the same Voice settings
- **THEN** both resolve to the same cache entry

### Requirement: Stored audio is raw synthesis output
The cache SHALL store the backend's audio before trimming, normalization or any mixing, so changes to assembly rules never require re-synthesis.

#### Scenario: Assembly rule change
- **WHEN** the sentence-gap setting changes and a cached Script is rendered again
- **THEN** the render uses cached audio and reflects the new sentence gap

### Requirement: Safe concurrent and interrupted writes
Cache writes SHALL be atomic: an interrupted write SHALL never leave a partial entry that is later read as valid.

#### Scenario: Interrupted render
- **WHEN** a render is killed while writing a cache entry and the Script is rendered again
- **THEN** the affected sentence is synthesized again and the render succeeds

### Requirement: Cache location and bypass
The cache directory SHALL be configurable. Rendering SHALL offer a bypass that ignores existing entries and overwrites them with fresh synthesis.

#### Scenario: Bypass
- **WHEN** a Script is rendered with cache bypass enabled
- **THEN** every speech unit is synthesized and the entries are replaced
