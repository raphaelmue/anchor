# tts-synthesis Specification

## Purpose

Turns text into speech audio through pluggable TTS Backends behind a common interface, so the rest of the system never depends on a specific engine or server.

## Requirements

### Requirement: Configured TTS Backend
The system SHALL synthesize speech through a TTS Backend configured by base URL, optional API key, model ID and Voice ID. Configuration SHALL be possible via a config file and overridable via environment variables; API keys SHALL never be read from Session Scripts.

#### Scenario: Environment override
- **WHEN** the config file names one base URL and the environment variable for the base URL names another
- **THEN** synthesis uses the URL from the environment variable

### Requirement: OpenAI-compatible backends
The system SHALL support TTS Backends exposing an OpenAI-compatible speech endpoint (`POST /v1/audio/speech`), sending text, model, Voice, speed and requested audio format, and SHALL receive uncompressed audio.

#### Scenario: Synthesis against Speaches
- **WHEN** the Speaches backend with a German Piper voice is configured and a German sentence is synthesized
- **THEN** the system receives audio for that sentence at the backend's sample rate

### Requirement: Engine identity reporting
Each synthesis result SHALL carry the identity of what produced it: backend ID, model ID, Voice ID, speed and output sample rate, so downstream caching can distinguish outputs of different engines or versions.

#### Scenario: Different model, different identity
- **WHEN** the same text is synthesized with two different model IDs
- **THEN** the two results report different model identities

### Requirement: Synthesis failures are explicit
When the backend is unreachable, returns an error status, or returns no or undecodable audio, synthesis SHALL fail with an error naming the backend and the cause. Transient failures (connection error, HTTP 5xx) SHALL be retried a bounded number of times before failing.

#### Scenario: Backend down
- **WHEN** the configured backend is not reachable
- **THEN** synthesis fails after the configured retries with an error naming the backend URL

#### Scenario: Client error is not retried
- **WHEN** the backend responds with HTTP 400
- **THEN** synthesis fails immediately without retries and includes the backend's error message

### Requirement: Backend health check
The system SHALL offer a health check that reports whether the configured backend is reachable and whether the configured model and Voice are available.

#### Scenario: Model not installed
- **WHEN** the backend is reachable but the configured model is not available
- **THEN** the health check reports the backend as reachable and the model as missing

### Requirement: Voice listing
The system SHALL list the Voices the configured backend offers, filterable by language, where the backend supports listing.

#### Scenario: German voices
- **WHEN** Voices are listed with language "de-DE" on Speaches with Piper
- **THEN** only German Voices are returned
