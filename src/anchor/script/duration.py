"""Pre-render duration estimate (design D7).

Mirrors the unfitted render layout (`render/layout.py`) without synthesizing: speech time is
characters ÷ (Speech Rate × pacing speed), and gaps, pauses, sounds, lead-in and fade-out tail
follow the pacing profile exactly. Elastic Pauses contribute their full range.
"""

from dataclasses import dataclass

from anchor.audio.pacing import PacingProfile
from anchor.audio.sentences import split_sentences
from anchor.script.models import (
    PauseSegment,
    Script,
    SilentPracticeSegment,
    SoundSegment,
    SpeechSegment,
)

TOLERANCE = 0.10
LEAD_IN_SEC = 0.5  # = render.layout.LEAD_IN_SEC
SOUND_SEC = {"bell_soft": 6.0}  # lengths of the built-in sounds (audio/beds.py)


@dataclass(frozen=True)
class DurationEstimate:
    target_sec: float
    nominal_sec: float  # all pauses at their `seconds`
    min_sec: float  # Elastic Pauses at their minimum
    max_sec: float  # Elastic Pauses at their maximum
    speech_sec: float
    speech_chars: int
    pause_sec: float  # nominal pause and silent-practice time
    gap_sec: float  # sentence and Segment gaps
    fixed_sec: float  # everything except Elastic Pauses

    @property
    def allowed(self) -> tuple[float, float]:
        return self.target_sec * (1 - TOLERANCE), self.target_sec * (1 + TOLERANCE)

    @property
    def ok(self) -> bool:
        lo, hi = self.allowed
        return self.min_sec <= hi and self.max_sec >= lo

    def describe(self) -> str:
        lo, hi = self.allowed
        return (f"estimated {self.nominal_sec:.0f} s (reachable {self.min_sec:.0f}–"
                f"{self.max_sec:.0f} s), target {self.target_sec:.0f} s (±10 %: "
                f"{lo:.0f}–{hi:.0f} s)")


def spoken_texts(script: Script) -> list[tuple[int, str]]:
    """(Segment index, text) of every spoken text: speech and silent-practice prompts."""
    out: list[tuple[int, str]] = []
    for i, seg in enumerate(script.segments):
        if isinstance(seg, SpeechSegment):
            out.append((i, seg.text))
        elif isinstance(seg, SilentPracticeSegment) and seg.prompt:
            out.append((i, seg.prompt))
    return out


def estimate(script: Script, pacing: PacingProfile, chars_per_sec: float) -> DurationEstimate:
    rate = chars_per_sec * pacing.speed
    speech = gaps = pauses = sounds = 0.0
    chars = 0
    elastic_lo = elastic_hi = elastic_nominal = 0.0
    prev_audible = False

    def add_speech(text: str) -> None:
        nonlocal speech, gaps, chars, prev_audible
        sentences = split_sentences(text)
        for n, sentence in enumerate(sentences):
            if n == 0 and prev_audible:
                gaps += pacing.segment_gap_sec
            elif n > 0:
                gaps += pacing.sentence_gap_sec
            chars += len(sentence)
            speech += len(sentence) / rate
        prev_audible = prev_audible or bool(sentences)

    for seg in script.segments:
        if isinstance(seg, SpeechSegment):
            add_speech(seg.text)
        elif isinstance(seg, SoundSegment):
            if prev_audible:
                gaps += pacing.segment_gap_sec
            sounds += SOUND_SEC.get(seg.sound, 0.0)
            prev_audible = True
        elif isinstance(seg, PauseSegment | SilentPracticeSegment):
            if isinstance(seg, SilentPracticeSegment) and seg.prompt:
                add_speech(seg.prompt)
            pauses += seg.seconds
            if seg.elastic is not None:
                elastic_nominal += seg.seconds
                elastic_lo += seg.elastic[0]
                elastic_hi += seg.elastic[1]
            prev_audible = False

    nominal = LEAD_IN_SEC + speech + gaps + pauses + sounds + pacing.fade_out_sec
    fixed = nominal - elastic_nominal
    return DurationEstimate(
        target_sec=script.target_duration_sec,
        nominal_sec=nominal,
        min_sec=fixed + elastic_lo,
        max_sec=fixed + elastic_hi,
        speech_sec=speech,
        speech_chars=chars,
        pause_sec=pauses,
        gap_sec=gaps,
        fixed_sec=fixed,
    )


@dataclass(frozen=True)
class SpeechBudget:
    chars: tuple[int, int]  # total spoken characters
    pause_sec: tuple[int, int]  # total pause and silent-practice seconds (nominal)


AVG_SENTENCE_CHARS = 40  # M1 examples: 37–42 characters per sentence


def speech_budget(target_sec: float, pacing: PacingProfile, chars_per_sec: float,
                  share: tuple[float, float]) -> SpeechBudget:
    """How much to speak and how long to pause for a Script of `target_sec`, before it exists
    (design D5). `share` is the fraction of the target spent speaking, sentence gaps included;
    the rest, minus lead-in and fade-out, is pause time."""
    sec_per_char = 1 / (chars_per_sec * pacing.speed) + pacing.sentence_gap_sec / AVG_SENTENCE_CHARS
    overhead = LEAD_IN_SEC + pacing.fade_out_sec
    lo, hi = share
    return SpeechBudget(
        chars=(round(lo * target_sec / sec_per_char), round(hi * target_sec / sec_per_char)),
        pause_sec=(max(0, round((1 - hi) * target_sec - overhead)),
                   max(0, round((1 - lo) * target_sec - overhead))),
    )
