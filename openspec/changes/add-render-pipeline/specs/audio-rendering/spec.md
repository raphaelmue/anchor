# Spec Delta

## Purpose

Assembles a validated Session Script into a final, listenable Audio Asset — with natural pacing, uninterrupted background, consistent loudness and a duration close to the target — and exposes this as a command-line render.

## ADDED Requirements

### Requirement: Render command
The system SHALL provide a command that renders a Session Script file to an audio file at a given output path. It SHALL exit with status 0 on success and non-zero on any failure, printing the reason.

#### Scenario: Successful render
- **WHEN** the render command is run with a valid Script and an output path
- **THEN** an audio file is written to the output path and the command exits with status 0

#### Scenario: Invalid script
- **WHEN** the render command is run with a Script that fails validation
- **THEN** all validation errors are printed, no TTS Backend call is made, no output file is written and the exit status is non-zero

### Requirement: No partial output
A failed render SHALL NOT leave an output file at the output path, and SHALL NOT overwrite an existing file there.

#### Scenario: Backend fails mid-render
- **WHEN** synthesis fails for the fifth speech Segment and a file already exists at the output path
- **THEN** the existing file is unchanged and the command exits non-zero

### Requirement: Pre-flight resource check
Before any synthesis, the system SHALL verify that every referenced `sound` and `ambience` name exists and that the TTS Backend passes its health check.

#### Scenario: Unknown sound
- **WHEN** a Script references `sound` "gong_xl" which does not exist
- **THEN** the render fails before any synthesis with an error naming "gong_xl"

### Requirement: Sentence-level synthesis and gaps
Each `speech` Segment SHALL be split into sentences that are synthesized and cached individually, joined with a sentence gap defined by the Session Type's pacing profile.

#### Scenario: Two sentences
- **WHEN** a `speech` Segment contains "Mach es dir bequem. Schließe die Augen."
- **THEN** two speech units are synthesized and joined with the Session Type's sentence gap

### Requirement: Pacing profiles per Session Type
Each Session Type SHALL have a pacing profile with at least a speaking-rate factor, a sentence gap and a gap between consecutive Segments. Profiles SHALL be configurable; defaults SHALL be slower with longer gaps for `sleep` and tighter for `pre_event` and `short`.

#### Scenario: Sleep is slower than pre_event
- **WHEN** the same text is rendered once in a `sleep` and once in a `pre_event` Script with default profiles
- **THEN** the `sleep` render uses a lower speaking rate and a longer sentence gap

### Requirement: Consistent silence trimming
Leading and trailing silence of every synthesized speech unit SHALL be trimmed to a fixed margin, so that audible pause lengths are determined only by the Script and the pacing profile, not by engine padding.

#### Scenario: Engine padding differs
- **WHEN** two speech units come back from the engine with 50 ms and 400 ms of trailing silence
- **THEN** both are followed by the same audible gap in the rendered output

### Requirement: Speech is never cut or crossfaded
Speech audio SHALL NOT be shortened, overlapped or faded within its voiced part. Fades SHALL only be applied inside silence margins or to the background.

#### Scenario: Word ending preserved
- **WHEN** a speech unit ends with a soft consonant
- **THEN** the voiced tail of the unit is present in full in the output, with no fade or overlap applied to it

### Requirement: Continuous Noise Floor
The output SHALL carry a continuous, very quiet background bed from start to end, so silence never drops to digital zero. The bed SHALL default to a built-in room tone and SHALL be switchable by `ambience` Segments from that point on.

#### Scenario: No digital silence
- **WHEN** a Script with a 60-second `pause` is rendered
- **THEN** the output contains no run of exactly-zero samples longer than 10 ms

#### Scenario: Ambience switch
- **WHEN** an `ambience` Segment selects a different built-in bed mid-Script
- **THEN** the background changes to that bed with a crossfade from that point on

### Requirement: Pauses and silent practice
`pause` Segments SHALL render as background-only audio of their (fitted) length. `silent_practice` Segments SHALL render their optional `prompt` as speech, followed by background-only audio of their (fitted) length.

#### Scenario: Silent practice with prompt
- **WHEN** a `silent_practice` Segment has `seconds` 60 and a `prompt`
- **THEN** the prompt is spoken and followed by 60 seconds of background-only audio

### Requirement: Sounds
`sound` Segments SHALL insert a built-in sound (at least `bell_soft`), mixed over the background.

#### Scenario: Bell at start
- **WHEN** a Script begins with `sound` "bell_soft"
- **THEN** the output begins with the bell sound over the background

### Requirement: Markers
`marker` Segments SHALL produce no audio and SHALL be recorded with their timestamp in the render report.

#### Scenario: Marker timestamp
- **WHEN** a `marker` named "deepening_start" follows 90 seconds of audio
- **THEN** the render report lists "deepening_start" at about 90 seconds

### Requirement: Duration fitting
After synthesis, the system SHALL adjust Elastic Pauses within their ranges, proportionally to their flexibility, so the output duration is within ±10 % of `target_duration_sec`. If even the extreme ranges cannot reach the tolerance, the render SHALL fail with an error stating the achievable duration range.

#### Scenario: Fits by stretching
- **WHEN** the unfitted render is 15 % shorter than the target and Elastic Pauses can absorb the difference
- **THEN** the output duration is within ±10 % of the target

#### Scenario: Cannot fit
- **WHEN** a Script without Elastic Pauses renders 30 % longer than its target
- **THEN** the render fails with an error giving the achievable range and the target

### Requirement: Loudness and peaks
Speech units SHALL be loudness-normalized individually before mixing, and the final output SHALL be normalized to a configurable integrated loudness target (default −18 LUFS) with true peak at or below −1 dBTP. Peaks that would exceed the true-peak limit MAY be reduced by a latency-compensated peak limiter; the final normalization SHALL be a linear gain, so the Noise Floor is not raised relative to speech.

#### Scenario: Default target
- **WHEN** a Script is rendered with default settings
- **THEN** the output's integrated loudness is −18 LUFS ± 1 LU and its true peak is at most −1 dBTP

#### Scenario: Peaky speech stays linear
- **WHEN** speech units peak above −1 dBTP after per-unit normalization
- **THEN** those peaks are limited, the final normalization is linear, and the background level in pauses keeps its configured distance from speech

#### Scenario: Cached and fresh units match
- **WHEN** a render mixes cached and newly synthesized speech units
- **THEN** their short-term loudness differs by no more than 2 LU

### Requirement: Single sample rate
All audio SHALL be resampled to one internal sample rate before mixing, and the output SHALL use that rate.

#### Scenario: Mixed sources
- **WHEN** speech at 22.05 kHz is mixed with a built-in sound at 48 kHz
- **THEN** the output is produced at the single internal sample rate without errors

### Requirement: Session start and end
The output SHALL start with a short fade-in of the background. Non-`sleep` Sessions SHALL end with a short fade-out. `sleep` Sessions SHALL end with a long fade-out (configurable, default 30 s) of the background after the last Segment, and a `sleep` Script whose last audible Segment is a `sound` SHALL be rejected.

#### Scenario: Sleep fade-out
- **WHEN** a `sleep` Script is rendered with defaults
- **THEN** the output ends with a 30-second fade to silence after the last Segment

#### Scenario: End bell in sleep session
- **WHEN** a `sleep` Script ends with `sound` "bell_soft"
- **THEN** the render fails before synthesis with an error explaining that sleep Sessions must not end with a sound

### Requirement: Output encoding
The output SHALL be encoded as MP3 by default, with Opus selectable, chosen by option or output file extension.

#### Scenario: Opus by extension
- **WHEN** the output path ends with ".opus"
- **THEN** the file is encoded as Opus

### Requirement: Render report
Each successful render SHALL write a JSON report next to the output containing: output duration, target duration, integrated loudness, true peak, number of speech units, cache hits and misses, total synthesis time, total render time, the fitted length of each Elastic Pause, and marker timestamps.

#### Scenario: Report after render
- **WHEN** a render succeeds for "session.mp3"
- **THEN** "session.report.json" exists next to it with all listed fields
