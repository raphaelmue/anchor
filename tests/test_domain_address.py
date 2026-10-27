import pytest

from anchor.script import load_script
from anchor.script.domain import (
    DomainContext,
    formal_pronouns,
    informal_pronouns,
    language_counts,
    validate_domain,
)
from anchor.script.duration import spoken_texts
from domain_helpers import EXAMPLE_SCRIPTS, make_request, make_script

CTX = DomainContext.default()


def rules(texts, address="du"):
    s = make_script([*texts, "Öffne die Augen."])
    req = make_request(style_sheet={"address": address})
    return [(i.location, i.rule) for i in validate_domain(s, req, CTX).issues]


def test_formal_address_in_du_script():
    assert rules(["Atmen Sie ruhig ein."]) == [("segments[1]", "address.du")]


def test_informal_address_in_sie_script():
    found = rules(["Lass dir Zeit."], address="Sie")
    assert ("segments[1]", "address.sie") in found


def test_sentence_initial_pronoun_not_misread():
    assert rules(["Die Hände werden warm. Sie werden schwer."]) == []


@pytest.mark.parametrize("text,expected", [
    ("Spüren Sie Ihre Hände.", ["Sie", "Ihre"]),
    ("Ich danke Ihnen.", ["Ihnen"]),
    ("Sie atmen ruhig.", []),  # sentence-initial: ambiguous, not flagged
    ("Ihre Hände werden warm.", []),
    ("Die Arme sind schwer, und sie werden warm.", []),  # lower-case third person
    ("Ihr Atem fließt, und Ihr Körper ruht.", ["Ihr"]),
])
def test_formal_pronoun_detection(text, expected):
    assert formal_pronouns(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Lass dir Zeit.", ["dir"]),
    ("Du darfst deine Augen schließen.", ["Du", "deine"]),
    ("Spüren Sie Ihre Hände.", []),
    ("Dirigieren Sie den Atem.", []),  # word boundary
])
def test_informal_pronoun_detection(text, expected):
    assert informal_pronouns(text) == expected


def test_sie_script_with_formal_text_passes():
    s = make_script(["Atmen Sie ruhig ein.", "Öffnen Sie die Augen."])
    req = make_request(style_sheet={"address": "Sie"})
    assert validate_domain(s, req, CTX).issues == []


def test_english_segment():
    found = rules(["Take a deep breath and relax your shoulders."])
    assert ("segments[1]", "language.de") in found


def test_german_with_english_word_is_fine():
    assert rules(["Gönn dir eine kurze Pause, ein kleines Time-out für dich."]) == []


EXAMPLE_TEXTS = [
    (name, i, text)
    for name in ("day", "sleep", "short")
    for i, text in spoken_texts(load_script(EXAMPLE_SCRIPTS / f"{name}.json").script)
]


@pytest.mark.parametrize("name,index,text", EXAMPLE_TEXTS)
def test_example_speech_has_no_address_or_language_issue(name, index, text):
    assert formal_pronouns(text) == []
    en, de = language_counts(text)
    assert not (en >= 3 and en > de)


def test_corpus_is_not_empty():
    assert len(EXAMPLE_TEXTS) == 40  # every spoken text of the three examples
