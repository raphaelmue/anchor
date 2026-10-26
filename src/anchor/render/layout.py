"""Unfitted layout: the Script as a sequence of timed blocks (design D3).

Gaps follow the pacing profile: a sentence gap between sentences of one Segment, and a Segment
gap between consecutive audible Segments (speech, sounds, prompts). A pause or silent-practice
silence replaces the Segment gap. Markers and ambience switches take no time. The background
fades in under a short lead-in and fades out over a tail after the last Segment.
"""

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from anchor.audio import SAMPLE_RATE
from anchor.audio.pacing import PacingProfile
from anchor.script import (
    AmbienceSegment,
    MarkerSegment,
    PauseSegment,
    Script,
    SilentPracticeSegment,
    SoundSegment,
    SpeechSegment,
)

LEAD_IN_SEC = 0.5

BlockKind = Literal["gap", "speech", "sound", "pause", "marker", "ambience"]


@dataclass
class Block:
    kind: BlockKind
    samples: int
    audio: np.ndarray | None = field(default=None, repr=False)
    name: str | None = None
    segment_index: int | None = None
    seconds: float | None = None  # nominal pause length
    elastic: tuple[float, float] | None = None

    @property
    def is_elastic(self) -> bool:
        return self.kind == "pause" and self.elastic is not None


@dataclass
class Layout:
    blocks: list[Block]
    lead_in: int
    tail: int  # fade-out region after the last Segment
    sample_rate: int = SAMPLE_RATE

    @property
    def total_samples(self) -> int:
        return self.lead_in + sum(b.samples for b in self.blocks) + self.tail

    @property
    def total_sec(self) -> float:
        return self.total_samples / self.sample_rate

    def positions(self) -> list[int]:
        """Start sample of every block."""
        out, pos = [], self.lead_in
        for block in self.blocks:
            out.append(pos)
            pos += block.samples
        return out

    def markers(self) -> list[tuple[str, float]]:
        return [(b.name, pos / self.sample_rate)
                for b, pos in zip(self.blocks, self.positions(), strict=True)
                if b.kind == "marker"]


def build_layout(
    script: Script,
    speech: dict[tuple[int, int], np.ndarray],
    sounds: dict[str, np.ndarray],
    pacing: PacingProfile,
    *,
    sample_rate: int = SAMPLE_RATE,
) -> Layout:
    """`speech` maps (segment index, sentence index) to prepared audio (trimmed, normalized)."""
    sec = lambda s: round(s * sample_rate)  # noqa: E731
    blocks: list[Block] = []
    prev_audible = False

    def add_speech(index: int) -> None:
        nonlocal prev_audible
        sentences = sorted((j, audio) for (i, j), audio in speech.items() if i == index)
        for n, (_, audio) in enumerate(sentences):
            if n == 0 and prev_audible:
                blocks.append(Block("gap", sec(pacing.segment_gap_sec)))
            elif n > 0:
                blocks.append(Block("gap", sec(pacing.sentence_gap_sec)))
            blocks.append(Block("speech", audio.size, audio=audio, segment_index=index))
        prev_audible = prev_audible or bool(sentences)

    for i, seg in enumerate(script.segments):
        if isinstance(seg, SpeechSegment):
            add_speech(i)
        elif isinstance(seg, SoundSegment):
            if prev_audible:
                blocks.append(Block("gap", sec(pacing.segment_gap_sec)))
            audio = sounds[seg.sound]
            blocks.append(Block("sound", audio.size, audio=audio, name=seg.sound,
                                segment_index=i))
            prev_audible = True
        elif isinstance(seg, PauseSegment | SilentPracticeSegment):
            if isinstance(seg, SilentPracticeSegment) and seg.prompt:
                add_speech(i)
            blocks.append(Block("pause", sec(seg.seconds), segment_index=i,
                                seconds=seg.seconds, elastic=seg.elastic))
            prev_audible = False
        elif isinstance(seg, MarkerSegment):
            blocks.append(Block("marker", 0, name=seg.name, segment_index=i))
        elif isinstance(seg, AmbienceSegment):
            blocks.append(Block("ambience", 0, name=seg.ambience, segment_index=i))

    return Layout(blocks, sec(LEAD_IN_SEC), sec(pacing.fade_out_sec), sample_rate)
