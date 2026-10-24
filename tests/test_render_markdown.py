import pytest

from udemy_transcripts.courses import CourseInfo
from udemy_transcripts.curriculum import Lecture, Section
from udemy_transcripts.paragraphs import Paragraph
from udemy_transcripts.render.common import RenderOptions
from udemy_transcripts.render.markdown import (course_index, lecture_document, md_escape,
                                               paragraphs_to_markdown, single_document,
                                               single_part)

COURSE = CourseInfo("6737997", 'Java: "Spring" Boot', "java-spring", "https://seti.udemy.com")
SECTION = Section(1, "Introducción")
LECTURE = Lecture(51621151, "Bienvenida", 1, "Video", [], 366)
CAPTION = {"locale_id": "es_LA", "source": "manual", "url": "https://cdn/x.vtt"}
OPTS = RenderOptions()
PARAS = [Paragraph(255, "Hola a todos."), Paragraph(300.9, "Segundo párrafo.")]
LINK = "https://seti.udemy.com/course/java-spring/learn/lecture/51621151"


@pytest.mark.parametrize("raw, escaped", [
    ("snake_case y *negrita*", r"snake\_case y \*negrita\*"),
    ("usa <div> y [x](y)", r"usa \<div\> y \[x\](y)"),
    ("cuesta $5 y `code`", r"cuesta \$5 y \`code\`"),
    ("3. no es lista", r"3\. no es lista"),
    ("# no es título", r"\# no es título"),
    ("- no es viñeta", r"\- no es viñeta"),
    ("texto normal, con tildes: áé.", "texto normal, con tildes: áé."),
    ("a \\ b", "a \\\\ b"),
])
def test_md_escape(raw, escaped):
    assert md_escape(raw) == escaped


def test_timestamps_are_links_to_the_exact_second():
    out = paragraphs_to_markdown(PARAS, COURSE, LECTURE, OPTS)
    assert out == (f"[04:15]({LINK}?start=255) Hola a todos.\n\n"
                   f"[05:00]({LINK}?start=300) Segundo párrafo.")


def test_no_timestamps_and_ts_every():
    plain = RenderOptions(timestamps=False)
    assert paragraphs_to_markdown(PARAS, COURSE, LECTURE, plain) == \
        "Hola a todos.\n\nSegundo párrafo."
    every = RenderOptions(ts_every=60)
    out = paragraphs_to_markdown(PARAS, COURSE, LECTURE, every)
    assert out.count("](") == 1 and "Segundo párrafo." in out


def test_without_slug_timestamps_are_plain_marks():
    course = CourseInfo("1", "C", None, "https://www.udemy.com")
    out = paragraphs_to_markdown(PARAS[:1], course, LECTURE, OPTS)
    assert out == "`[04:15]` Hola a todos."


def test_lecture_document_front_matter_and_body():
    doc = lecture_document(COURSE, SECTION, LECTURE, CAPTION, PARAS, OPTS)
    head, body = doc.split("\n---\n", 1)
    assert head.splitlines() == [
        "---",
        'curso: "Java: \\"Spring\\" Boot"',
        'seccion: "Introducción"',
        'leccion: "Bienvenida"',
        "numero: 1",
        'tipo: "video"',
        f'url: "{LINK}"',
        'duracion: "06:06"',
        'idioma: "es_LA"',
        "subtitulo_automatico: false"]
    assert body.startswith("\n# Bienvenida\n\n> 01 - Introducción · 06:06 · es_LA · "
                           f"[Abrir en Udemy]({LINK})\n\n[04:15]")
    assert doc.endswith("Segundo párrafo.\n")


def test_front_matter_marks_automatic_captions():
    auto = dict(CAPTION, source="auto")
    doc = lecture_document(COURSE, SECTION, LECTURE, auto, PARAS, OPTS)
    assert "subtitulo_automatico: true" in doc and "es_LA (automático)" in doc


def test_front_matter_is_valid_yaml_for_awkward_titles():
    yaml = pytest.importorskip("yaml")
    lec = Lecture(5, 'Qué es: "esto" # y\\aquello', 2, "Video", [], None)
    doc = lecture_document(COURSE, Section(1, "A: B"), lec, CAPTION, PARAS, OPTS)
    data = yaml.safe_load(doc.split("---\n")[1])
    assert data["leccion"] == lec.title and data["seccion"] == "A: B" and data["numero"] == 2


def entries_for(*lectures):
    return {str(lec.id): {"file": f"01 - Introducción/{lec.number} - {lec.title}.md",
                          "locale": "es_LA", "source": "manual"} for lec in lectures}


def test_course_index_lists_links_durations_and_gaps():
    done = Lecture(1, "Bienvenida", 1, "Video", [CAPTION], 366)
    auto = Lecture(2, "Con auto", 2, "Video", [CAPTION], 60)
    pending = Lecture(3, "Pendiente", 3, "Video", [CAPTION], 30)
    nocap = Lecture(4, "Sin subs", 4, "Video", [], 10)
    article = Lecture(5, "Un artículo", 5, "Article", [], None)
    sections = [Section(1, "Introducción", [done, auto, pending, nocap, article]),
                Section(2, "Solo artículos", [article])]
    entries = entries_for(done, auto)
    entries["2"]["source"] = "auto"
    index = course_index(COURSE, sections, entries)
    assert index.startswith('# Java: "Spring" Boot\n\n[Abrir el curso en Udemy]'
                            "(https://seti.udemy.com/course/java-spring/)\n\n"
                            "2 de 6 lecciones descargadas · 07:46 de vídeo")
    assert "- [001 - Bienvenida](01%20-%20Introducci%C3%B3n/001%20-%20Bienvenida.md)" \
        " — 06:06 · es_LA" in index
    assert "es_LA (automático)" in index
    assert "- 003 - Pendiente — 00:30 · pendiente de descargar" in index
    assert "- 004 - Sin subs — 00:10 · sin subtítulos" in index
    assert "- 005 - Un artículo — artículo · vacío" in index
    assert "Solo artículos" in index


def test_single_document_has_toc_anchors_and_sections():
    s1, s2 = Section(1, "Intro"), Section(2, "Fin")
    l1 = Lecture(11, "Uno", 1, "Video", [], 60)
    l2 = Lecture(12, "Dos", 2, "Video", [], None)
    items = [(s1, l1, single_part(COURSE, s1, l1, CAPTION, PARAS, OPTS)),
             (s2, l2, single_part(COURSE, s2, l2, CAPTION, PARAS[:1], OPTS))]
    doc = single_document(COURSE, items)
    assert "## Contenido" in doc
    assert "- [01 - Intro](#sec-1)\n  - [001 - Uno](#lec-11) (01:00)" in doc
    assert '<a id="sec-1"></a>\n\n## 01 - Intro' in doc
    assert '<a id="lec-11"></a>\n\n### 001 - Uno' in doc
    assert doc.index("### 001 - Uno") < doc.index("## 02 - Fin") < doc.index("### 002 - Dos")
    assert "---\ncurso" not in doc          # sin cabecera YAML por lección
