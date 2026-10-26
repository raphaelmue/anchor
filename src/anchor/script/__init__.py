"""Session Script format v1.2 and its structural validation."""

from anchor.script.models import (
    SCHEMA_VERSION,
    AmbienceSegment,
    MarkerSegment,
    PauseSegment,
    Script,
    Segment,
    SessionType,
    SilentPracticeSegment,
    SoundSegment,
    SpeechRole,
    SpeechSegment,
)
from anchor.script.validate import ValidationIssue, ValidationResult, load_script, validate_script

__all__ = [
    "SCHEMA_VERSION",
    "AmbienceSegment",
    "MarkerSegment",
    "PauseSegment",
    "Script",
    "Segment",
    "SessionType",
    "SilentPracticeSegment",
    "SoundSegment",
    "SpeechRole",
    "SpeechSegment",
    "ValidationIssue",
    "ValidationResult",
    "load_script",
    "validate_script",
]
