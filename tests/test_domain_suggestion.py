import pytest

from anchor.script import load_script
from anchor.script.domain import DomainContext, load_lexicon, parse_lexicon, validate_domain
from anchor.script.duration import spoken_texts
from domain_helpers import EXAMPLE_SCRIPTS, make_request, make_script

CTX = DomainContext.default()
LEXICON = load_lexicon("de-DE")


def suggestion_issues(text):
    s = make_script([text, "Öffne die Augen."])
    return [i for i in validate_domain(s, make_request(), CTX).issues
            if i.rule.startswith("suggestion.")]


def test_lexicon_is_versioned():
    assert LEXICON.version == "de-DE.1"
    assert set(LEXICON.categories) == {"absolute", "medical", "control", "others"}


def test_guarantee():
    issues = suggestion_issues("Du wirst nie wieder nervös sein.")
    assert issues and all(i.location == "segments[1]" for i in issues)
    assert any(i.rule == "suggestion.absolute" and "nie wieder" in i.message for i in issues)


def test_medical_claim():
    issues = suggestion_issues("Diese Übung heilt deine Schlafstörung.")
    assert {i.rule for i in issues} == {"suggestion.medical"}
    assert any("heilt" in i.message for i in issues)


def test_harmless_text():
    assert suggestion_issues("Vielleicht bemerkst du, wie dein Atem ruhiger wird.") == []


@pytest.mark.parametrize("text,category", [
    ("Du wirst die Prüfung bestehen.", "absolute"),
    ("Das klappt garantiert.", "absolute"),
    ("Keine Angst mehr, ab heute.", "absolute"),
    ("Nichts kann dich mehr aus der Ruhe bringen.", "absolute"),
    ("Du bist für immer angstfrei.", "absolute"),
    ("Das ist wie eine kleine Therapie.", "medical"),
    ("Du brauchst keine Medikamente mehr.", "medical"),
    ("Lass das Trauma los.", "medical"),
    ("Deine Depression wird leichter.", "medical"),
    ("Du kannst die Augen nicht mehr öffnen.", "control"),
    ("Du musst meiner Stimme folgen.", "control"),
    ("Gib die Kontrolle ganz an mich ab.", "control"),
    ("Du gehorchst jedem Wort.", "control"),
    ("Dein Chef wird sich ändern.", "others"),
    ("Alle werden dich bewundern.", "others"),
])
def test_flagged_phrasings(text, category):
    assert category in {c for c, _ in LEXICON.matches(text)}, text


# Typical permissive Suggestions per Strategy (spec §8.1) and Fading prompts.
ALLOWED = [
    "Vielleicht bemerkst du, wie dein Atem ruhiger wird.",
    "Du darfst dir Zeit lassen.",
    "Mit jedem Ausatmen kannst du ein wenig mehr loslassen.",
    "Du kannst ruhig und klar bleiben, auch wenn es spannend wird.",
    "Wenn du magst, schließe die Augen.",
    "In der Prüfung atmest du ruhig und liest die erste Frage in deinem Tempo.",
    "Wenn der Wecker klingelt, atmest du tief ein und stellst die Füße auf den Boden.",
    "Die Aufregung ist Energie, die dich wach und aufmerksam macht.",
    "Du hast schon viele schwierige Situationen gemeistert.",
    "Es gibt gerade nichts zu tun und nichts zu erreichen.",
    "Der Schlaf darf von selbst kommen, wann immer er will.",
    "Du kannst jederzeit die Augen öffnen, wenn du es möchtest.",
    "Du bleibst jederzeit wach genug, um selbst zu entscheiden.",
    "Mit etwas Übung fällt es dir leichter, ruhig zu bleiben.",
    "Auch wenn ein Gedanke stört, kehrst du ruhig zum Atem zurück.",
    "Vielleicht wird die Besprechung anstrengend, und du gehst Schritt für Schritt vor.",
    "Du weißt, was du gelernt hast, und vertraust darauf.",
    "Wenn du nervös wirst, ist das in Ordnung. Du atmest einfach weiter.",
    "Gedanken dürfen kommen und gehen, wie Wolken am Nachthimmel.",
    "Heute Abend darfst du einfach liegen und ausruhen.",
    "Du bist gut vorbereitet und gehst in deinem Tempo vor.",
    "Dein Körper weiß, wie Entspannung geht.",
    "Du bestimmst selbst, wie tief du dich entspannen möchtest.",
    "Mit der Zeit kann diese Ruhe immer vertrauter werden.",
    "Bleib jetzt eine Weile still bei diesem Gefühl.",
    "Nimm dir einen Moment, um wieder ganz anzukommen.",
    "Die Kolleginnen und Kollegen sind da, und du bleibst bei dir und deinem Atem.",
    "Diese Übung ist ein Training, das mit jedem Mal etwas leichter wird.",
]


def test_allowed_corpus_size():
    assert len(ALLOWED) >= 20


@pytest.mark.parametrize("text", ALLOWED)
def test_allowed_phrasings_have_no_match(text):
    assert LEXICON.matches(text) == []


@pytest.mark.parametrize("text", [
    t for name in ("day", "sleep", "short")
    for _, t in spoken_texts(load_script(EXAMPLE_SCRIPTS / f"{name}.json").script)
])
def test_example_speech_has_no_match(text):
    assert LEXICON.matches(text) == []


def test_matching_is_case_insensitive_and_nfc():
    decomposed = "Du wirst garantiert ruhig."
    assert LEXICON.matches(decomposed.upper())
    assert LEXICON.matches("Das ist eine Schlafsto\u0308rung.")  # o + combining diaeresis


def test_invalid_lexicon():
    with pytest.raises(ValueError, match="invalid lexicon"):
        parse_lexicon("version: x\nlanguage: de-DE\ncategories:\n  a:\n    patterns: ['(']\n",
                      "bad.yaml")
