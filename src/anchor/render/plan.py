"""Plan stage: split speech into sentences, normalize, compute cache keys (design D3)."""

from dataclasses import dataclass

from anchor.audio.pacing import PacingProfile
from anchor.audio.sentences import split_sentences
from anchor.cache import CachingSynthesizer, normalize_text
from anchor.script import Script, SilentPracticeSegment, SpeechSegment


@dataclass(frozen=True)
class PlannedUnit:
    segment_index: int
    sentence_index: int
    text: str  # normalized
    style: str | None
    key: str
    cached: bool


@dataclass(frozen=True)
class Plan:
    units: list[PlannedUnit]
    speed: float

    @property
    def misses(self) -> int:
        # Repeated sentences within one Script are synthesized once.
        return len({u.key for u in self.units if not u.cached})

    def for_segment(self, index: int) -> list[PlannedUnit]:
        return [u for u in self.units if u.segment_index == index]


def make_plan(script: Script, pacing: PacingProfile, synth: CachingSynthesizer) -> Plan:
    units: list[PlannedUnit] = []
    for i, seg in enumerate(script.segments):
        if isinstance(seg, SpeechSegment):
            text, style = seg.text, seg.style
        elif isinstance(seg, SilentPracticeSegment) and seg.prompt:
            text, style = seg.prompt, None
        else:
            continue
        for j, sentence in enumerate(split_sentences(text)):
            normalized = normalize_text(sentence)
            key = synth.key_for(normalized, speed=pacing.speed, style=style)
            units.append(PlannedUnit(i, j, normalized, style, key, synth.is_cached(key)))
    return Plan(units, pacing.speed)
