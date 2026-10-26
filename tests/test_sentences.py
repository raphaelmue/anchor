import pytest

from anchor.audio.sentences import split_sentences


def test_two_sentences():
    assert split_sentences("Mach es dir bequem. Schließe die Augen.") == [
        "Mach es dir bequem.", "Schließe die Augen."]


@pytest.mark.parametrize("text", [
    "Spüre z. B. deine Hände. Lass sie schwer werden.",
    "Spüre z.B. deine Hände. Lass sie schwer werden.",
])
def test_z_b_is_not_a_boundary(text):
    first, second = split_sentences(text)
    assert first.endswith("deine Hände.") and second == "Lass sie schwer werden."


def test_usw_is_not_a_boundary():
    assert split_sentences("Arme, Beine usw. werden schwer. Gut so.") == [
        "Arme, Beine usw. werden schwer.", "Gut so."]


def test_d_h_and_ordinal():
    assert split_sentences("Am 3. Tag, d. h. morgen, üben wir weiter. Danke.") == [
        "Am 3. Tag, d. h. morgen, üben wir weiter.", "Danke."]


def test_ellipsis():
    assert split_sentences("Atme ein … und wieder aus.") == ["Atme ein … und wieder aus."]
    assert split_sentences("Und jetzt… Ruhe. Ganz ruhig...") == [
        "Und jetzt…", "Ruhe.", "Ganz ruhig..."]
    assert split_sentences("Warte... Spüre es.") == ["Warte...", "Spüre es."]


def test_question_and_exclamation_marks():
    assert split_sentences("Spürst du es? Gut! Weiter so?! Ja.") == [
        "Spürst du es?", "Gut!", "Weiter so?!", "Ja."]


def test_closing_quote_stays_with_sentence():
    assert split_sentences("Sag dir: „Ich bin ruhig.“ Atme aus.") == [
        "Sag dir: „Ich bin ruhig.“", "Atme aus."]


def test_no_terminal_punctuation_and_empty():
    assert split_sentences("  Ruhe  ") == ["Ruhe"]
    assert split_sentences("   ") == []


def test_content_is_preserved():
    text = "Eins. Zwei? Drei! Vier … fünf. Sechs, z. B. sieben."
    assert " ".join(split_sentences(text)) == text
