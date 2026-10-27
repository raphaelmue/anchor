"""Versioned prompts and their rendering (design D5).

Prompts are package files `prompts/<name>.v<N>.md`, rendered with `str.format_map`. A prompt is
never edited in place: a change is a new file and a version bump, recorded per generation.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from importlib import resources

from anchor.generate.request import GuidanceLevel, MethodId, ScriptRequest, Strategy
from anchor.script.domain import DomainContext, DomainIssue
from anchor.script.duration import speech_budget
from anchor.script.models import SessionType

SCRIPT_PROMPT_VERSION = "script.v1"

LANGUAGE_NAMES = {"de-DE": "German"}

# Fraction of the target spent speaking (sentence gaps included); the rest is pauses. From the
# M1 examples (speech 16 % day, 7 % sleep, 20 % short) with room for richer guidance.
SPEECH_SHARE: dict[SessionType, tuple[float, float]] = {
    SessionType.DAY: (0.15, 0.30),
    SessionType.SLEEP: (0.08, 0.18),
    SessionType.SHORT: (0.20, 0.40),
    SessionType.CUE_RECALL: (0.20, 0.45),
    SessionType.REHEARSAL: (0.25, 0.45),
    SessionType.PRE_EVENT: (0.25, 0.50),
    SessionType.TASTER: (0.25, 0.45),
}

SESSION_TYPE_RULES = {
    SessionType.DAY: (
        "`day`: a full daytime practice. Induction, the Method's core, optional deepening and "
        "Suggestions, then an Emergence that brings the listener back awake and alert. The last "
        "`speech` Segment MUST have `role` `emergence`. Starting and ending with `bell_soft` is "
        "customary."),
    SessionType.SLEEP: (
        "`sleep`: practice in bed at bedtime that lets the listener drift into sleep. There is "
        "NO Emergence: no Segment may have `role` `emergence`, and nothing wakes the listener "
        "up. The speech becomes sparser and slower towards the end, and the Script ends with a "
        "long pause. No sound at the end."),
    SessionType.SHORT: (
        "`short`: a 2–5 minute practice for the middle of the day. A brief arrival, the core "
        "exercise and a short return. An Emergence is optional."),
    SessionType.CUE_RECALL: (
        "`cue_recall`: 1–3 minutes of using the Cue Word to recall the relaxed state quickly. "
        "No Emergence constraint."),
    SessionType.REHEARSAL: (
        "`rehearsal`: Mental Rehearsal of the target situation in a relaxed state. The last "
        "`speech` Segment MUST have `role` `emergence`."),
    SessionType.PRE_EVENT: (
        "`pre_event`: very short, for use right before the event. It ends alert and ready: the "
        "last `speech` Segment MUST have `role` `emergence`."),
    SessionType.TASTER: (
        "`taster`: about 3 minutes, a first gentle experience of the practice. No Emergence "
        "constraint."),
}

METHOD_DESCRIPTIONS = {
    MethodId.PMR: "Progressive Muscle Relaxation: tense a muscle group briefly, then release "
                  "it and notice the difference, group by group.",
    MethodId.AUTOGENIC_TRAINING: "Autogenic Training: calm, repeated formulas of heaviness, "
                                 "warmth, calm breath and heartbeat.",
    MethodId.SELF_HYPNOSIS: "Self-hypnosis: focused attention, a gentle induction and "
                            "deepening, then Suggestions in the relaxed state.",
    MethodId.MINDFULNESS_BODY_SCAN: "Mindfulness body scan: move attention slowly through the "
                                    "body and notice sensations without changing them.",
    MethodId.PACED_BREATHING: "Paced breathing: slow breathing with a longer exhale, guided by "
                              "counting.",
    MethodId.MENTAL_REHEARSAL: "Mental Rehearsal: walk through the target situation step by "
                               "step with all senses, including a small difficulty handled "
                               "calmly.",
    MethodId.IMPLEMENTATION_INTENTION: "Implementation intention: rehearse concrete if-then "
                                       "plans that link a situational cue to a helpful action.",
}

STRATEGY_DESCRIPTIONS = {
    Strategy.CALM_COMPETENCE: "present-tense, realistic statements about staying calm and "
                              "capable in the target situation",
    Strategy.MENTAL_REHEARSAL: "walk through the situation step by step with senses, including "
                               "a small difficulty handled calmly",
    Strategy.IF_THEN_CUE: "link a concrete situational cue to the Cue Word or a helpful action",
    Strategy.EGO_STRENGTHENING: "general self-efficacy statements grounded in the "
                                "Practitioner's real resources",
    Strategy.REFRAME: "perceive arousal as energy/readiness rather than danger",
    Strategy.SLEEP_PERMISSION: "reduce effort to sleep (\"nothing to do, nothing to achieve "
                               "right now\")",
}

FADING = {
    GuidanceLevel.GUIDED: "Full spoken guidance throughout. `silent_practice` is optional and "
                          "short.",
    GuidanceLevel.SEMI_GUIDED: "Spoken guidance plus a growing share of `silent_practice` "
                               "Segments in which the listener continues alone (\"Continue on "
                               "your own for a minute …\").",
    GuidanceLevel.SELF_GUIDED: "Short prompts only. Most of the Session is `silent_practice`; "
                               "the voice only opens, briefly cues each step, and closes.",
}


@cache
def load_prompt(name: str) -> str:
    return resources.files("anchor.generate").joinpath(f"prompts/{name}.md").read_text("utf-8")


def _bullets(items: Sequence[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def style_sheet_text(request: ScriptRequest) -> str:
    st = request.style_sheet
    lines = [f"Form of address: {st.address} (use only this form, never the other one)",
             f"Tone: {st.tone}"]
    if st.imagery:
        lines.append("Recurring imagery: " + "; ".join(st.imagery))
    if st.situation_vocabulary:
        lines.append("Situation vocabulary: " + "; ".join(st.situation_vocabulary))
    if st.cue_word and request.cue_word_introduced:
        lines.append(f"Cue Word: {st.cue_word}")
        if st.cue_word_phrasing:
            lines.append(f"Cue Word phrasing: {st.cue_word_phrasing}")
    else:
        lines.append("Cue Word: not introduced yet. Do not use or invent a Cue Word.")
    return _bullets(lines)


def ledger_text(request: ScriptRequest) -> str:
    if not request.suggestion_ledger:
        return "No Suggestions have been used in this Program yet."
    return ("Suggestions already used in this Program. Stay consistent with them and never "
            "contradict them; you may echo them, but vary the wording:\n"
            + _bullets(request.suggestion_ledger))


@dataclass(frozen=True)
class Prompts:
    system: str
    user: str
    version: str = SCRIPT_PROMPT_VERSION


def render_script_prompts(request: ScriptRequest, ctx: DomainContext) -> Prompts:
    pacing = ctx.pacing[request.session_type]
    budget = speech_budget(request.target_duration_sec, pacing, ctx.chars_per_sec,
                           SPEECH_SHARE[request.session_type])
    strategies = [f"`{s}`: {STRATEGY_DESCRIPTIONS[s]}" for s in request.strategies]
    values = {
        "language": request.language,
        "language_name": LANGUAGE_NAMES.get(request.language, request.language),
        "session_type": request.session_type.value,
        "session_type_rules": SESSION_TYPE_RULES[request.session_type],
        "session_context": request.session_context,
        "method": request.method.value,
        "method_description": METHOD_DESCRIPTIONS[request.method],
        "strategies": _bullets(strategies) if strategies else "(none)",
        "style_sheet": style_sheet_text(request),
        "ledger": ledger_text(request),
        "guidance_level": request.guidance_level.value,
        "fading": FADING[request.guidance_level],
        "target_sec": f"{request.target_duration_sec:g}",
        "chars_per_minute": round(ctx.chars_per_sec * pacing.speed * 60),
        "sentence_gap": f"{pacing.sentence_gap_sec:g}",
        "segment_gap": f"{pacing.segment_gap_sec:g}",
        "chars_lo": budget.chars[0],
        "chars_hi": budget.chars[1],
        "pause_lo": budget.pause_sec[0],
        "pause_hi": budget.pause_sec[1],
        "goal_pattern": request.goal.pattern,
        "goal_domain": request.goal.domain or "(none)",
        "target_situation": request.goal.target_situation,
        "desired_state": request.goal.desired_state,
        "notes": f"Notes: {request.notes}\n" if request.notes else "",
    }
    return Prompts(load_prompt("script_system.v1").format_map(values),
                   load_prompt("script_user.v1").format_map(values))


def render_feedback(issues: Sequence[DomainIssue]) -> str:
    return load_prompt("script_feedback.v1").format_map(
        {"count": len(issues), "errors": "\n".join(str(i) for i in issues)})
