from udemy_transcripts.curriculum import Lecture, Section
from udemy_transcripts.courses import CourseInfo
from udemy_transcripts.paragraphs import Paragraph
from udemy_transcripts.render.common import RenderOptions, fmt_time
from udemy_transcripts.render.txt import (paragraphs_to_text, single_document, single_file,
                                          single_part, table_of_contents)

TXT = RenderOptions(format="txt", width=0)


def test_fmt_time():
    assert fmt_time(0) == "00:00" and fmt_time(255.9) == "04:15"
    assert fmt_time(3600) == "1:00:00" and fmt_time(3725) == "1:02:05"
    assert fmt_time(None) == ""


def test_one_sentence_per_line_with_timestamp_on_first_line():
    paras = [Paragraph(255, "Hola a todos. ¿Cómo están? Bien!")]
    assert paragraphs_to_text(paras, TXT) == "[04:15] Hola a todos.\n¿Cómo están?\nBien!"


def test_paragraphs_are_separated_by_a_blank_line():
    paras = [Paragraph(0, "Uno."), Paragraph(65, "Dos.")]
    assert paragraphs_to_text(paras, TXT) == "[00:00] Uno.\n\n[01:05] Dos."


def test_no_timestamps_gives_the_classic_text():
    paras = [Paragraph(0, "Hola a todos. Adiós.")]
    out = paragraphs_to_text(paras, RenderOptions(format="txt", width=0, timestamps=False))
    assert out == "Hola a todos.\nAdiós."


def test_ts_every_hides_intermediate_marks():
    paras = [Paragraph(0, "a."), Paragraph(20, "b."), Paragraph(70, "c.")]
    out = paragraphs_to_text(paras, RenderOptions(format="txt", width=0, ts_every=60))
    assert out == "[00:00] a.\n\nb.\n\n[01:10] c."


def test_wraps_to_width_including_the_mark():
    out = paragraphs_to_text([Paragraph(0, "palabra " * 30 + "final.")],
                             RenderOptions(format="txt", width=40))
    assert all(len(line) <= 40 for line in out.split("\n")) and out.startswith("[00:00] palabra")


def test_decimal_numbers_are_not_split_and_empty_is_safe():
    assert paragraphs_to_text([Paragraph(0, "La versión 3.5 es estable.")],
                              RenderOptions(format="txt", width=0, timestamps=False)) \
        == "La versión 3.5 es estable."
    assert paragraphs_to_text([], TXT) == ""


def test_single_file_format_and_toc():
    part = single_part("007", "01 - Intro", "Bienvenida", "Hola.")
    assert part == f"{'=' * 70}\n[007] 01 - Intro — Bienvenida\n{'=' * 70}\n\nHola."
    assert single_file("Curso", [part, part]) == f"Curso\n\n{part}\n\n{part}\n"
    toc = table_of_contents([("01 - Intro", [("001", "Bienvenida", "06:06"), ("002", "Setup", "")])])
    assert toc == "CONTENIDO\n\n01 - Intro\n  001 - Bienvenida  (06:06)\n  002 - Setup"


def test_single_document_includes_a_table_of_contents():
    course = CourseInfo("1", "Curso", "curso", "https://www.udemy.com")
    s1, s2 = Section(1, "Intro"), Section(2, "Fin")
    lec = lambda i, t, d: Lecture(i, t, i, "Video", [], d)
    items = [(s1, lec(1, "Uno", 60), "BLOQUE1"), (s1, lec(2, "Dos", None), "BLOQUE2"),
             (s2, lec(3, "Tres", 5), "BLOQUE3")]
    doc = single_document(course, items)
    assert doc.startswith("Curso\n\nCONTENIDO\n\n01 - Intro\n  001 - Uno  (01:00)\n  002 - Dos\n\n02 - Fin")
    assert doc.index("BLOQUE1") < doc.index("BLOQUE2") < doc.index("BLOQUE3")
