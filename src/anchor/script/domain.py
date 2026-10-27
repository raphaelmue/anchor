"""Domain validation: the rules a structurally valid Script must pass for its Script Request
(spec `script-domain-validation`, FR-17, design D8).

Each rule is a function `(script, request, ctx) -> list[DomainIssue]` with a stable rule id.
All rules run and every issue is collected.
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from anchor.audio.pacing import PacingProfile, load_pacing
from anchor.audio.sentences import split_sentences
from anchor.script.duration import DurationEstimate, estimate, spoken_texts
from anchor.script.models import Script, SessionType, SpeechRole, SpeechSegment
from anchor.script.validate import ValidationIssue

if TYPE_CHECKING:
    from anchor.config import Settings
    from anchor.generate.request import ScriptRequest

EMERGENCE_REQUIRED = {SessionType.DAY, SessionType.REHEARSAL, SessionType.PRE_EVENT}
EMERGENCE_FORBIDDEN = {SessionType.SLEEP}


@dataclass(frozen=True)
class DomainIssue:
    location: str  # "segments[3]" or "$" for whole-Script rules
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.location}: {self.rule}: {self.message}"

    @classmethod
    def structural(cls, issue: ValidationIssue) -> "DomainIssue":
        return cls(issue.location, "structure", issue.message)

    def as_dict(self) -> dict:
        return {"location": self.location, "rule": self.rule, "message": self.message}


def _loc(index: int) -> str:
    return f"segments[{index}]"


# -- lexicon -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Lexicon:
    version: str
    language: str
    categories: dict[str, list[re.Pattern[str]]]

    def matches(self, text: str) -> list[tuple[str, str]]:
        """(category, matched phrase) for every pattern match in `text`."""
        text = unicodedata.normalize("NFC", text)
        found = []
        for category, patterns in self.categories.items():
            for pattern in patterns:
                found += [(category, m.group(0)) for m in pattern.finditer(text)]
        return found


class LexiconError(ValueError):
    pass


def parse_lexicon(text: str, source: str) -> Lexicon:
    try:
        data = yaml.safe_load(text)
        categories = {
            name: [re.compile(p, re.IGNORECASE) for p in spec["patterns"]]
            for name, spec in data["categories"].items()
        }
        return Lexicon(str(data["version"]), data["language"], categories)
    except (yaml.YAMLError, KeyError, TypeError, re.error) as exc:
        raise LexiconError(f"invalid lexicon {source}: {exc}") from exc


@cache
def load_lexicon(language: str) -> Lexicon:
    path = resources.files("anchor.script").joinpath(f"lexicon/{language}.yaml")
    if not path.is_file():
        raise LexiconError(f"no Suggestion Rule lexicon for language {language!r}")
    return parse_lexicon(path.read_text("utf-8"), f"{language}.yaml")


# -- context -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainContext:
    pacing: dict[SessionType, PacingProfile]
    chars_per_sec: float
    lexicons: dict[str, Lexicon] = field(default_factory=dict)

    @classmethod
    def from_settings(cls, settings: "Settings") -> "DomainContext":
        return cls(load_pacing(settings.audio.pacing_file), settings.tts.chars_per_sec)

    @classmethod
    def default(cls, pacing_file: Path | None = None) -> "DomainContext":
        return cls(load_pacing(pacing_file), 21.0)

    def lexicon(self, language: str) -> Lexicon:
        return self.lexicons.get(language) or load_lexicon(language)

    def estimate(self, script: Script) -> DurationEstimate:
        return estimate(script, self.pacing[script.session_type], self.chars_per_sec)


Rule = Callable[[Script, "ScriptRequest", DomainContext], list[DomainIssue]]


# -- rules: request match, Emergence, introduced elements -----------------------------------


def match_request(script: Script, request: "ScriptRequest", ctx: DomainContext):
    issues = []
    pairs = [("session_type", script.session_type, request.session_type),
             ("language", script.language, request.language),
             ("target_duration_sec", script.target_duration_sec, request.target_duration_sec)]
    if script.method is not None:
        pairs.append(("method", script.method, request.method))
    for name, actual, expected in pairs:
        if actual != expected:
            issues.append(DomainIssue(name, f"match.{name}",
                                      f"Script has {actual!s}, request has {expected!s}"))
    return issues


def _speech(script: Script) -> list[tuple[int, SpeechSegment]]:
    return [(i, s) for i, s in enumerate(script.segments) if isinstance(s, SpeechSegment)]


def emergence(script: Script, request: "ScriptRequest", ctx: DomainContext):
    speech = _speech(script)
    if request.session_type in EMERGENCE_REQUIRED:
        if not speech:
            return [DomainIssue("$", "emergence.required",
                                f"a {request.session_type} Script must end with an Emergence")]
        i, last = speech[-1]
        if last.role != SpeechRole.EMERGENCE:
            return [DomainIssue(_loc(i), "emergence.required",
                                f"the last speech Segment of a {request.session_type} Script "
                                "must have role 'emergence'")]
    if request.session_type in EMERGENCE_FORBIDDEN:
        return [DomainIssue(_loc(i), "emergence.forbidden",
                            f"a {request.session_type} Script must not contain an Emergence")
                for i, s in speech if s.role == SpeechRole.EMERGENCE]
    return []


def _contains_phrase(text: str, phrase: str) -> bool:
    pattern = r"(?<!\w)" + r"\s+".join(map(re.escape, phrase.split())) + r"(?!\w)"
    return re.search(pattern, unicodedata.normalize("NFC", text), re.IGNORECASE) is not None


def introduced_elements(script: Script, request: "ScriptRequest", ctx: DomainContext):
    issues = []
    allowed = {str(s) for s in request.strategies}
    for i, seg in _speech(script):
        if seg.strategy is not None and seg.strategy not in allowed:
            listed = ", ".join(sorted(allowed)) or "none"
            issues.append(DomainIssue(_loc(i), "elements.strategy",
                                      f"Strategy {seg.strategy!r} is not introduced "
                                      f"(request allows: {listed})"))
    cue = request.style_sheet.cue_word
    if cue and not request.cue_word_introduced:
        for i, text in spoken_texts(script):
            if _contains_phrase(text, cue):
                issues.append(DomainIssue(_loc(i), "elements.cue_word",
                                          f"the Cue Word {cue!r} is not introduced yet"))
    return issues


# -- rules: form of address and language ----------------------------------------------------

_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")
_FORMAL = {"Sie", "Ihnen", "Ihr", "Ihre", "Ihren", "Ihrem", "Ihrer", "Ihres"}
_INFORMAL = re.compile(r"^(?:du|dich|dir|dein\w*|euch|euer|eur(?:e|em|en|er|es))$", re.I)


def _sentence_words(text: str) -> list[list[str]]:
    return [_WORD.findall(s) for s in split_sentences(unicodedata.normalize("NFC", text))]


def formal_pronouns(text: str) -> list[str]:
    """Capitalized formal pronouns that are not sentence-initial. A sentence-initial "Sie" is
    ambiguous ("Sie werden schwer" = "they") and never counted; "Atmen Sie" is non-initial."""
    return [w for words in _sentence_words(text) for w in words[1:] if w in _FORMAL]


def informal_pronouns(text: str) -> list[str]:
    return [w for words in _sentence_words(text) for w in words if _INFORMAL.match(w)]


def form_of_address(script: Script, request: "ScriptRequest", ctx: DomainContext):
    address = request.style_sheet.address
    find, rule, other = ((formal_pronouns, "address.du", "formal")
                         if address == "du" else (informal_pronouns, "address.sie", "informal"))
    issues = []
    for i, text in spoken_texts(script):
        if words := find(text):
            issues.append(DomainIssue(
                _loc(i), rule, f"Style Sheet says {address!r}, but the text uses {other} "
                f"address: {', '.join(dict.fromkeys(words))}"))
    return issues


# Words that are also common German words ("in", "an", "die", "will", "also", "her") are left out.
_EN_STOPWORDS = frozenset("""
    the a and you your yours to of is are be been it its this that these those with for on at as
    from my me we our they them their he she his not or if can just now let into out up down
    how what when where which while there here take breathe relax feel yourself
""".split())  # noqa: SIM905
_DE_STOPWORDS = frozenset("""
    und der die das den dem des ein eine einen einem einer du dich dir dein deine deinen deinem
    ist sind bist nicht mit zu auf es sich wie noch nur jetzt ganz wird werden im ins von bei
    für auch lass dann wenn oder aber kannst sie ihr ihre ihnen wir uns mein meine kein keine
    nichts alles was so da hier dabei ruhig einfach immer schon mehr weiter langsam
""".split())  # noqa: SIM905


def language_counts(text: str) -> tuple[int, int]:
    words = [w.lower() for w in _WORD.findall(text)]
    return (sum(w in _EN_STOPWORDS for w in words), sum(w in _DE_STOPWORDS for w in words))


def language(script: Script, request: "ScriptRequest", ctx: DomainContext):
    if request.language != "de-DE":
        return []
    issues = []
    for i, text in spoken_texts(script):
        en, de = language_counts(text)
        if en >= 3 and en > de:
            issues.append(DomainIssue(_loc(i), "language.de",
                                      f"text looks English ({en} English vs {de} German "
                                      "stopwords); all spoken text must be in de-DE"))
    return issues


# -- rules: duration and Suggestion lexicon -------------------------------------------------


def duration(script: Script, request: "ScriptRequest", ctx: DomainContext):
    est = ctx.estimate(script)
    if est.ok:
        return []
    lo, hi = est.allowed
    return [DomainIssue("$", "duration.range",
                        f"reachable duration {est.min_sec:.0f}–{est.max_sec:.0f} s "
                        f"(estimated {est.nominal_sec:.0f} s) does not overlap the allowed range "
                        f"{lo:.0f}–{hi:.0f} s for target {est.target_sec:.0f} s")]


def suggestion_lexicon(script: Script, request: "ScriptRequest", ctx: DomainContext):
    lexicon = ctx.lexicon(request.language)
    issues = []
    for i, text in spoken_texts(script):
        for category, phrase in lexicon.matches(text):
            description = LEXICON_CATEGORY_NAMES.get(category, category)
            issues.append(DomainIssue(_loc(i), f"suggestion.{category}",
                                      f"{description}: {phrase!r}"))
    return issues


LEXICON_CATEGORY_NAMES = {
    "absolute": "guarantee or absolute",
    "medical": "medical or therapeutic claim",
    "control": "command implying loss of control",
    "others": "other people as targets of change",
}

RULES: tuple[Rule, ...] = (match_request, emergence, introduced_elements, form_of_address,
                           language, duration, suggestion_lexicon)


@dataclass(frozen=True)
class DomainResult:
    issues: list[DomainIssue]
    estimate: DurationEstimate

    @property
    def ok(self) -> bool:
        return not self.issues


def validate_domain(script: Script, request: "ScriptRequest", ctx: DomainContext) -> DomainResult:
    """Run every rule on a structurally valid Script and collect all issues."""
    issues = [issue for rule in RULES for issue in rule(script, request, ctx)]
    return DomainResult(issues, ctx.estimate(script))
