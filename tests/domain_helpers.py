"""Builders shared by the domain-validation and generation tests."""

from pathlib import Path

from anchor.generate.request import ScriptRequest, parse_request
from anchor.script import validate_script

ROOT = Path(__file__).parent.parent
EXAMPLE_SCRIPTS = ROOT / "examples" / "scripts"
EXAMPLE_REQUESTS = ROOT / "examples" / "requests"

BASE_REQUEST = {
    "session_type": "day",
    "method": "pmr",
    "guidance_level": "guided",
    "target_duration_sec": 120,
    "language": "de-DE",
    "goal": {"pattern": "calm_in_situation", "domain": "stress",
             "target_situation": "Arbeitstag", "desired_state": "ruhig bleiben"},
    "style_sheet": {"address": "du", "tone": "warm"},
    "strategies": ["calm_competence"],
}


def make_request(**overrides) -> ScriptRequest:
    style = {**BASE_REQUEST["style_sheet"], **overrides.pop("style_sheet", {})}
    request, errors = parse_request({**BASE_REQUEST, "style_sheet": style, **overrides})
    assert request is not None, errors
    return request


def make_script(texts, *, session_type="day", target=120, last_role="emergence",
                pause=(60, 30, 120), **meta):
    """A Script with one speech Segment per text and one elastic pause that keeps the
    duration reachable; the last speech Segment gets `last_role`."""
    segments = [{"type": "speech", "text": t} for t in texts]
    if last_role:
        segments[-1]["role"] = last_role
    seconds, lo, hi = pause
    segments.insert(0, {"type": "pause", "seconds": seconds, "elastic": [lo, hi]})
    doc = {"schema_version": "1.2", "session_type": session_type, "language": "de-DE",
           "target_duration_sec": target, "segments": segments, **meta}
    result = validate_script(doc)
    assert result.ok, result.errors
    return result.script


def segments_doc(segments, **meta):
    doc = {"schema_version": "1.2", "session_type": "day", "language": "de-DE",
           "target_duration_sec": 120, "segments": segments, **meta}
    result = validate_script(doc)
    assert result.ok, result.errors
    return result.script


def llm_doc(texts=("Atme ruhig ein.", "Öffne die Augen."), *, last_role="emergence",
            pause=(60, 30, 120)):
    """A generation answer in the LLM-facing schema (see make_script for the shape)."""
    segments = [{"type": "speech", "text": t, "role": None, "strategy": None} for t in texts]
    if last_role:
        segments[-1]["role"] = last_role
    seconds, lo, hi = pause
    segments.insert(0, {"type": "pause", "seconds": seconds,
                        "elastic": {"min": lo, "max": hi}})
    return {"segments": segments}
