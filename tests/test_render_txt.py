from udemy_transcripts.captions import Cue
from udemy_transcripts.render.txt import cues_to_text, single_file, single_part


def cues(*texts):
    return [Cue(i, i + 1, t) for i, t in enumerate(texts)]


def test_one_sentence_per_line():
    assert cues_to_text(cues("Hola a todos.", "¿Cómo están? Bien!", "Fin"), 0) == \
        "Hola a todos.\n¿Cómo están?\nBien!\nFin"


def test_wraps_to_width():
    out = cues_to_text(cues("palabra " * 30 + "final."), 40)
    assert all(len(line) <= 40 for line in out.split("\n"))
    assert len(out.split("\n")) > 1


def test_width_zero_does_not_wrap():
    out = cues_to_text(cues("x" * 50 + " " + "y" * 80), 0)
    assert "\n" not in out


def test_decimal_numbers_are_not_split():
    assert cues_to_text(cues("La versión 3.5 es estable."), 0) == "La versión 3.5 es estable."


def test_empty():
    assert cues_to_text([], 100) == ""


def test_single_file_format():
    part = single_part("007", "01 - Intro", "Bienvenida", "Hola.")
    assert part == f"{'=' * 70}\n[007] 01 - Intro — Bienvenida\n{'=' * 70}\n\nHola."
    assert single_file("Curso", [part, part]) == f"Curso\n\n{part}\n\n{part}\n"
