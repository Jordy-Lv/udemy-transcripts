from udemy_transcripts.captions import Cue
from udemy_transcripts.paragraphs import build_paragraphs, marked


def cues(*specs):
    """(inicio, fin, texto) → Cue."""
    return [Cue(s, e, t) for s, e, t in specs]


def test_pause_starts_a_new_paragraph():
    paras = build_paragraphs(cues((0, 2, "Uno."), (2, 4, "Dos."), (6, 8, "Tres.")), pause=1.5)
    assert [(p.start, p.text) for p in paras] == [(0, "Uno. Dos."), (6, "Tres.")]


def test_short_gap_does_not_split():
    paras = build_paragraphs(cues((0, 2, "Uno."), (3, 5, "Dos.")), pause=1.5)
    assert len(paras) == 1


def test_gap_exactly_at_the_threshold_splits():
    assert len(build_paragraphs(cues((0, 1, "a."), (2.5, 3, "b.")), pause=1.5)) == 2


def test_long_paragraph_splits_after_a_sentence_end():
    texts = [("frase número %d termina aquí." % i) for i in range(10)]
    stream = [(i, i + 1, t) for i, t in enumerate(texts)]
    paras = build_paragraphs(cues(*stream), pause=99, max_chars=60)
    assert len(paras) > 1
    assert all(p.text.rstrip().endswith(".") for p in paras)
    assert " ".join(p.text for p in paras) == " ".join(texts)


def test_long_paragraph_does_not_split_mid_sentence():
    stream = [(i, i + 1, "palabra seguida de otra sin punto") for i in range(12)]
    assert len(build_paragraphs(cues(*stream), pause=99, max_chars=60)) == 1


def test_unpunctuated_auto_captions_split_only_on_pauses():
    stream = [(0, 1, "hola a todos"), (1, 2, "bienvenidos al curso"), (5, 6, "vamos a empezar")]
    paras = build_paragraphs(cues(*stream), pause=1.5, max_chars=10)
    assert [p.text for p in paras] == ["hola a todos bienvenidos al curso", "vamos a empezar"]


def test_sentence_end_accepts_closing_quotes_and_ellipsis():
    stream = [(0, 1, 'dijo "basta."'), (1, 2, "luego…"), (2, 3, "y siguió")]
    assert len(build_paragraphs(cues(*stream), pause=99, max_chars=5)) == 3


def test_empty_and_overlapping_cues():
    assert build_paragraphs([]) == []
    paras = build_paragraphs(cues((0, 10, "largo."), (2, 3, "solapado.")), pause=1.5)
    assert len(paras) == 1


def test_marked_every_paragraph_by_default():
    paras = build_paragraphs(cues((0, 1, "a."), (5, 6, "b."), (10, 11, "c.")), pause=1.5)
    assert [show for _, show in marked(paras)] == [True, True, True]


def test_marked_every_n_seconds():
    paras = build_paragraphs(cues(*[(i * 10, i * 10 + 1, f"p{i}.") for i in range(7)]), pause=1.5)
    assert [show for _, show in marked(paras, every=25)] == \
        [True, False, False, True, False, False, True]     # 0, 30, 60


def test_marked_empty():
    assert list(marked([])) == []
