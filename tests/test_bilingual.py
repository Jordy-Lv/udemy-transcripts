import json

import pytest

from conftest import FakeContext
from test_download import COURSE, FILES, INTRO, MD, TXT, VIDEO1, read, run, sections
from udemy_transcripts import cli
from udemy_transcripts.captions import Cue, LangSpec, parse_lang_spec, pick_secondary
from udemy_transcripts.errors import UdemyError
from udemy_transcripts.manifest import MANIFEST_NAME
from udemy_transcripts.paragraphs import Paragraph, attach_translation, build_paragraphs
from udemy_transcripts.render.common import RenderOptions
from udemy_transcripts.render.markdown import paragraphs_to_markdown
from udemy_transcripts.render.txt import paragraphs_to_text
from udemy_transcripts.study import clean_lesson_text


# ---- --lang ---------------------------------------------------------------------------------
def test_parse_lang_spec_plain_preferences():
    assert parse_lang_spec("es,en") == LangSpec(["es", "en"], None)
    assert parse_lang_spec(" es , ,en ") == LangSpec(["es", "en"], None)
    assert parse_lang_spec("") == LangSpec([], None) and parse_lang_spec(None) == LangSpec([], None)


def test_parse_lang_spec_bilingual_pair_becomes_the_first_preference():
    assert parse_lang_spec("es+en") == LangSpec(["es"], "en")
    assert parse_lang_spec("pt, es_ES + en_US") == LangSpec(["es_ES", "pt"], "en_US")


@pytest.mark.parametrize("value", ["es+", "+en", "es+en+fr", "es+en,pt+fr", "+"])
def test_parse_lang_spec_rejects_bad_pairs(value):
    with pytest.raises(UdemyError, match="--lang"):
        parse_lang_spec(value)


def caps(*locales):
    return [{"locale_id": loc, "source": src, "url": f"https://cdn/{loc}-{src}.vtt"}
            for loc, src in locales]


def test_pick_secondary_skips_the_primary_and_prefers_manual():
    captions = caps(("es_ES", "manual"), ("en_US", "auto"), ("en_GB", "manual"))
    assert pick_secondary(captions, "en", captions[0])["locale_id"] == "en_GB"
    assert pick_secondary(captions, "es", captions[0]) is None            # solo existe la principal
    assert pick_secondary(captions, "fr", captions[0]) is None
    assert pick_secondary([{"locale_id": "en_US", "url": ""}], "en", None) is None
    assert pick_secondary(None, "en", None) is None


# ---- alineación por tiempo -------------------------------------------------------------------------
def test_paragraphs_know_where_they_end():
    paras = build_paragraphs([Cue(0, 2, "Uno."), Cue(2, 4.5, "Dos."), Cue(10, 12, "Tres.")], pause=2.5)
    assert [(p.start, p.end) for p in paras] == [(0, 4.5), (10, 12)]


def test_translation_cues_go_to_the_paragraph_they_overlap_most():
    paras = [Paragraph(0, "Hola a todos. Bienvenidos.", 6), Paragraph(10, "Vamos a empezar.", 14)]
    cues2 = [Cue(0.5, 3, "Hello everyone."), Cue(3.2, 6, "Welcome."),   # párrafo 1
             Cue(9.4, 12, "Let's start"), Cue(12, 13.5, "now."),          # párrafo 2 (9.4-12: punto medio 10.7)
             Cue(-1, 0.4, "Intro.")]                                      # antes del primero → párrafo 1
    attach_translation(paras, cues2)
    assert paras[0].other == "Hello everyone. Welcome. Intro."
    assert paras[1].other == "Let's start now."


def test_translation_with_no_matching_cues_leaves_the_paragraph_alone():
    paras = [Paragraph(0, "Uno.", 1), Paragraph(50, "Dos.", 51)]
    attach_translation(paras, [Cue(0, 1, "One.")])
    assert (paras[0].other, paras[1].other) == ("One.", "")
    assert attach_translation([], [Cue(0, 1, "x")]) == [] and attach_translation(paras, None)[1].other == ""


# ---- render -----------------------------------------------------------------------------------------
LECTURE = sections()[0].lectures[0]
PARAS = [Paragraph(5, "Hola a todos.", 8, "Hello everyone."), Paragraph(20, "Sin traducción.", 22)]


def test_markdown_shows_the_second_language_under_each_paragraph():
    out = paragraphs_to_markdown(PARAS, COURSE, LECTURE, RenderOptions(second_lang="en"))
    assert out == ("[00:05](https://seti.udemy.com/course/mi-curso/learn/lecture/900?start=5) Hola a todos."
                   "\n\n> **en** · Hello everyone.\n\n"
                   "[00:20](https://seti.udemy.com/course/mi-curso/learn/lecture/900?start=20) Sin traducción.")


def test_markdown_escapes_the_second_language():
    out = paragraphs_to_markdown([Paragraph(0, "a", 1, "use snake_case <b>")], COURSE, LECTURE,
                                 RenderOptions(timestamps=False))
    assert out == "a\n\n> **→** · use snake\\_case \\<b\\>"


def test_text_format_indents_and_wraps_the_second_language():
    out = paragraphs_to_text(PARAS, RenderOptions(format="txt", width=0, second_lang="en"))
    assert out == "[00:05] Hola a todos.\n    ↳ en: Hello everyone.\n\n[00:20] Sin traducción."
    wrapped = paragraphs_to_text([Paragraph(0, "x", 1, "palabra " * 20)],
                                 RenderOptions(format="txt", width=40, timestamps=False, second_lang="en"))
    lines = wrapped.split("\n")
    assert all(len(line) <= 40 for line in lines) and len(lines) > 1
    assert lines[1].startswith("    ↳ en: palabra") and lines[2].startswith(" " * 10 + "palabra")


# ---- descarga bilingüe ----------------------------------------------------------------------------------
EN_VTT = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello.\n\n00:00:03.000 --> 00:00:04.000\nBye.\n"
BI_FILES = dict(FILES, **{"https://cdn.example/900-en.vtt": (200, EN_VTT),
                          "https://cdn.example/901-es.vtt": (200, EN_VTT)})
BI = LangSpec(["es"], "en")
BI_OPTS = RenderOptions(second_lang="en")


def bilingual_sections():
    secs = sections()
    secs[0].lectures[0].captions.append(
        {"locale_id": "en_US", "source": "manual", "file_name": "900-en.vtt",
         "url": "https://cdn.example/900-en.vtt"})
    return secs


def bilingual_run(make_client, course_dir, files, logs, update=False):
    from udemy_transcripts.download import download_course
    from udemy_transcripts.manifest import Manifest
    manifest = Manifest.load(course_dir / MANIFEST_NAME, 123, log=lambda *_: None)
    ctx = FakeContext(dict(files))
    stats = download_course(make_client(context=ctx), COURSE, bilingual_sections(), BI, BI_OPTS,
                            course_dir, False, update, manifest, log=logs.append, pause=0)
    return stats, ctx


def test_bilingual_lesson_has_both_columns_and_both_languages(make_client, tmp_path):
    logs = []
    stats, ctx = bilingual_run(make_client, tmp_path, BI_FILES, logs)
    assert stats.saved == 3
    text = read(tmp_path, VIDEO1)
    assert 'idioma: "es_LA"\nidioma_secundario: "en_US"' in text
    assert "> 00 - General · 01:00 · es_LA + en_US ·" in text
    assert "Hola. Adiós.\n\n> **en** · Hello. Bye." in text
    assert any("es_LA + en_US" in line for line in logs)
    entry = json.loads((tmp_path / MANIFEST_NAME).read_text(encoding="utf-8"))["lectures"]["900"]
    assert (entry["locale"], entry["locale2"]) == ("es_LA", "en_US")
    assert entry["caption"].endswith("+en_US:900-en.vtt")
    assert "es_LA + en_US" in read(tmp_path, "README.md")
    assert ctx.requested.count("https://cdn.example/900-en.vtt") == 1


def test_lessons_without_the_second_track_are_single_language_with_a_note(make_client, tmp_path):
    from udemy_transcripts.download import download_course
    from udemy_transcripts.manifest import Manifest
    logs = []
    manifest = Manifest.load(tmp_path / MANIFEST_NAME, 123, log=lambda *_: None)
    download_course(make_client(context=FakeContext(dict(BI_FILES))), COURSE, sections(), BI,
                    BI_OPTS, tmp_path, False, False, manifest, log=logs.append, pause=0)
    assert "**en**" not in read(tmp_path, VIDEO1) and "idioma_secundario" not in read(tmp_path, VIDEO1)
    assert any("Bienvenida" in line and "sin pista en" in line for line in logs)


def test_failed_second_track_is_a_warning_and_is_retried_by_update(make_client, tmp_path):
    from udemy_transcripts.download import download_course
    from udemy_transcripts.manifest import Manifest
    files = {k: v for k, v in BI_FILES.items() if "900-en" not in k}      # 404
    logs = []

    def go(files_, update):
        manifest = Manifest.load(tmp_path / MANIFEST_NAME, 123, log=lambda *_: None)
        ctx = FakeContext(dict(files_))
        stats = download_course(make_client(context=ctx), COURSE, bilingual_sections(), BI, BI_OPTS,
                                tmp_path, False, update, manifest, log=logs.append, pause=0)
        return stats, ctx

    stats, _ = go(files, False)
    assert stats.failed == 0 and any("no se pudo bajar la pista en_US" in line for line in logs)
    assert "**en**" not in read(tmp_path, VIDEO1)
    stats, ctx = go(BI_FILES, True)                                   # ahora la pista sí existe
    assert stats.saved == 1 and "https://cdn.example/900-en.vtt" in ctx.requested
    assert "> **en** · Hello. Bye." in read(tmp_path, VIDEO1)
    stats, ctx = go(BI_FILES, True)                                   # y ya está vigente
    assert (stats.saved, ctx.requested) == (0, [])


def test_switching_between_bilingual_and_single_rewrites_the_lesson(make_client, tmp_path):
    from udemy_transcripts.download import download_course
    from udemy_transcripts.manifest import Manifest

    def go(spec, opts, update=True):
        manifest = Manifest.load(tmp_path / MANIFEST_NAME, 123, log=lambda *_: None)
        return download_course(make_client(context=FakeContext(dict(BI_FILES))), COURSE,
                               bilingual_sections(), spec, opts, tmp_path, False, update, manifest,
                               log=lambda *_: None, pause=0)

    go(LangSpec(["es"]), MD, update=False)
    assert go(LangSpec(["es"]), MD).saved == 0
    assert go(BI, BI_OPTS).saved >= 1                                  # se pidió el bilingüe
    assert go(LangSpec(["es"]), MD).saved >= 1                         # y se volvió al normal
    assert "**en**" not in read(tmp_path, VIDEO1)


def test_bilingual_text_files_and_single_mode(make_client, tmp_path):
    from udemy_transcripts.download import download_course
    txt = RenderOptions(format="txt", width=0, second_lang="en")
    stats = download_course(make_client(context=FakeContext(dict(BI_FILES))), COURSE,
                            bilingual_sections(), BI, txt, None, True, False, None,
                            log=lambda *_: None, pause=0)
    assert "[00:01] Hola.\nAdiós.\n    ↳ en: Hello. Bye." in stats.items[0][2]


# ---- CLI y estudio -------------------------------------------------------------------------------------
def test_cli_passes_the_second_language_to_the_renderer():
    args = cli.build_parser().parse_args(["--lang", "es+en", "x"])
    opts, _ = cli.options_from_args(args)
    assert opts.second_lang == "en"
    assert cli.options_from_args(cli.build_parser().parse_args(["x"]))[0].second_lang == ""
    with pytest.raises(UdemyError):
        cli.options_from_args(cli.build_parser().parse_args(["--lang", "es+", "x"]))


def test_the_translation_is_not_sent_to_the_ai():
    md = ("---\ncurso: \"C\"\n---\n\n# T\n\n> meta\n\n[00:05](https://x/y?start=5) Hola a todos.\n\n"
          "> **en** · Hello everyone.\n\n[00:20](https://x/y?start=20) Adiós.\n\n> **en** · Bye.\n")
    assert clean_lesson_text(md) == "Hola a todos.\n\nAdiós."
    text = "[00:05] Hola a todos.\n    ↳ en: Hello everyone, this is a long\n          translated line.\n\n[00:20] Adiós.\n"
    assert clean_lesson_text(text) == "Hola a todos.\n\nAdiós."
    code = "Config:\n    name: valor\n    otro: cosa"
    assert clean_lesson_text(code) == code                           # YAML indentado no se confunde
