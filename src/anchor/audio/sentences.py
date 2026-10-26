"""Sentence splitting for German Script text (design D3).

Splits after `.`, `!`, `?` or an ellipsis followed by whitespace. It does not split after a
protected abbreviation (`z. B.`, `usw.`, …) or an ordinal number (`3. Tag`), and an ellipsis only
ends a sentence when an upper-case letter follows (`Atme ein … und aus` stays one sentence).
Mis-splits only move gaps; they never change the spoken content.
"""

import re

ABBREVIATIONS = (
    "z. B.", "z.B.", "d. h.", "d.h.", "u. a.", "u.a.", "z. T.", "u. U.", "o. ä.", "s. o.",
    "s. u.", "v. a.", "i. d. R.", "usw.", "bzw.", "ca.", "evtl.", "ggf.", "vgl.", "etc.",
    "bspw.", "inkl.", "sog.", "Dr.", "Prof.", "Nr.", "Hr.", "Fr.", "St.", "Std.", "Min.",
    "Sek.", "Abs.", "Kap.", "S.", "Mio.", "Mrd.",
)

# Candidate boundary: terminal punctuation (+ closing quotes/brackets), then whitespace.
_BOUNDARY = re.compile(r"(\.\.\.|…|[.!?]+)([\"»«“”'’)\]]*)(\s+)")
_ABBR_PATTERNS = [
    re.compile(r"(?<![\wÄÖÜäöüß])" + re.escape(a).replace(r"\ ", r"\s*")) for a in ABBREVIATIONS
]


def _protected_spans(text: str) -> list[tuple[int, int]]:
    return [m.span() for p in _ABBR_PATTERNS for m in p.finditer(text)]


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    protected = _protected_spans(text)
    sentences: list[str] = []
    start = 0
    for m in _BOUNDARY.finditer(text):
        punct_end = m.end(2)
        if any(lo < punct_end <= hi for lo, hi in protected):
            continue
        punct = m.group(1)
        before = text[start:m.start(1)]
        after = text[m.end():]
        if punct == "." and re.search(r"(?:^|\s)\d+$", before):
            continue  # ordinal number: "am 3. Tag"
        if punct in ("...", "…") and not (after[:1].isupper()):
            continue
        sentences.append(text[start:punct_end].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences
