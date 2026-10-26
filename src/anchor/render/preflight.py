"""Pre-flight checks that run before any synthesis (design D3)."""

from anchor.audio.beds import BEDS, SOUNDS
from anchor.render.errors import RenderError
from anchor.script import (
    AmbienceSegment,
    Script,
    SessionType,
    SilentPracticeSegment,
    SoundSegment,
    SpeechSegment,
)


def _is_audible(segment) -> bool:
    """Segments that produce foreground audio (pauses and markers only carry the background)."""
    if isinstance(segment, SilentPracticeSegment):
        return segment.prompt is not None
    return isinstance(segment, SpeechSegment | SoundSegment)


def preflight(script: Script) -> None:
    problems: list[str] = []
    for i, seg in enumerate(script.segments):
        if isinstance(seg, SoundSegment) and seg.sound not in SOUNDS:
            problems.append(f"segments[{i}]: unknown sound {seg.sound!r} "
                            f"(available: {', '.join(sorted(SOUNDS))})")
        if isinstance(seg, AmbienceSegment) and seg.ambience not in BEDS:
            problems.append(f"segments[{i}]: unknown ambience {seg.ambience!r} "
                            f"(available: {', '.join(sorted(BEDS))})")
    if script.session_type is SessionType.SLEEP:
        audible = [(i, s) for i, s in enumerate(script.segments) if _is_audible(s)]
        if audible and isinstance(audible[-1][1], SoundSegment):
            problems.append(
                f"segments[{audible[-1][0]}]: sleep Sessions must not end with a sound; "
                "they end with a long fade-out so the listener can fall asleep")
    if problems:
        raise RenderError("pre-flight failed:\n  " + "\n  ".join(problems))
