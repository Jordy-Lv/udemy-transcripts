import pytest

from test_download import run
from test_resources import ON, RES_FILES
from udemy_transcripts import cli
from udemy_transcripts.errors import UdemyError
from udemy_transcripts.merge import (MergeLesson, MergeSection, clean_links, collect, course_url,
                                     lesson_text, merge_course, render_part, split_front_matter,
                                     split_parts)
from udemy_transcripts.study import load_manifest


@pytest.fixture
def course(make_client, tmp_path):
    """Un curso ya descargado (vídeos, artículo y recursos) en tmp_path/Mi curso."""
    course_dir = tmp_path / "Mi curso"
    run(make_client, course_dir, files=RES_FILES, res=ON)
    return course_dir


def lessons(*words):
    return [MergeLesson(f"{n:03d}", f"L{n}", " ".join(["w"] * w)) for n, w in enumerate(words, 1)]


# ---- limpieza de una lección -----------------------------------------------------------
def test_split_front_matter_reads_the_yaml_header():
    meta, body = split_front_matter('---\ncurso: "Mi curso"\nnumero: 3\n---\n\n# T\n')
    assert meta == {"curso": "Mi curso", "numero": 3} and body == "\n# T\n"
    assert split_front_matter("# Solo texto\n") == ({}, "# Solo texto\n")


def test_clean_links_drops_local_paths_and_timestamp_urls_but_keeps_web_links():
    assert clean_links("[00:05](https://x/y?start=5) Hola") == "[00:05] Hola"
    assert clean_links("Mira [el PDF](..%2Frecursos/01/a.pdf) y [la web](https://a.b/c)") == \
        "Mira el PDF y [la web](https://a.b/c)"
    assert clean_links("![esquema](recursos/img/a.png) y ![](x.png)") == "*[imagen: esquema]* y "
    assert clean_links("![nube](https://img.example/a.png)") == "![nube](https://img.example/a.png)"
    assert clean_links("[ancla](#sec) [correo](mailto:a@b.c)") == "[ancla](#sec) [correo](mailto:a@b.c)"


def test_lesson_text_shifts_headings_but_not_inside_code():
    body = ("\n# Título\n\n> 00 - Intro · 02:00\n\n## Tema\n\ntexto\n\n```md\n# no es título\n```\n\n"
            "### Sub\n\n## Recursos\n\n- [a.pdf](../recursos/a.pdf)\n")
    text = lesson_text(body, "007")
    assert text.startswith("### 007 - Título\n\n> 00 - Intro · 02:00\n\n#### Tema")
    assert "```md\n# no es título\n```" in text
    assert "\n##### Sub\n" in text and "\n#### Recursos\n\n- a.pdf" in text
    assert lesson_text("# T\n\n###### h6\n", "001").endswith("###### h6")     # tope en h6


# ---- división en partes ------------------------------------------------------------------
def section(index, *words):
    return MergeSection(index, f"{index:02d} - S{index}", lessons(*words))


def shape(parts):
    return [[(s.index, len(s.lessons)) for s in part] for part in parts]


def test_split_parts_keeps_everything_together_when_it_fits():
    parts = split_parts([section(1, 10, 10), section(2, 10)], 100)
    assert shape(parts) == [[(1, 2), (2, 1)]]
    assert shape(split_parts([section(1, 500), section(2, 500)], 0)) == [[(1, 1), (2, 1)]]


def test_split_parts_cuts_at_section_boundaries():
    parts = split_parts([section(1, 40, 40), section(2, 40, 40), section(3, 10)], 100)
    assert shape(parts) == [[(1, 2)], [(2, 2), (3, 1)]]


def test_split_parts_splits_a_huge_section_by_lessons_and_repeats_its_heading():
    parts = split_parts([section(1, 60, 60, 60), section(2, 10)], 100)
    assert shape(parts) == [[(1, 1)], [(1, 1)], [(1, 1), (2, 1)]]
    assert parts[1][0].dirname == "01 - S1"


def test_a_lesson_bigger_than_the_limit_goes_alone():
    assert shape(split_parts([section(1, 500, 5)], 100)) == [[(1, 1)], [(1, 1)]]


def test_render_part_has_header_toc_and_sections():
    text = render_part("Mi curso", "https://u/c", [section(1, 3)], 2, 3, 9)
    assert text.startswith("# Mi curso (parte 2 de 3)\n\n[Abrir el curso en Udemy](https://u/c)\n\n"
                           "1 lecciones de 9\n\n## Contenido\n\n- 01 - S1\n  - 001 - L1\n")
    assert "\n\n## 01 - S1\n\nw w w\n" in text
    assert render_part("C", "", [section(1, 3)]).startswith("# C\n\n1 lecciones\n")


# ---- desde lo descargado -----------------------------------------------------------------
def test_collect_reads_the_downloaded_lessons_in_order(course):
    title, sections = collect(course, load_manifest(course))
    assert title == "Mi curso"
    assert [(s.index, [l.number for l in s.lessons]) for s in sections] == [
        (0, ["001"]), (1, ["002", "003"])]
    video = sections[0].lessons[0]
    assert video.text.startswith("### 001 - Bienvenida") and "Hola. Adiós." in video.text
    assert video.duration                                    # «mm:ss» de los vídeos
    article = sections[1].lessons[1]
    assert "**negrita**" in article.text and "\n##### Tema\n" in article.text
    assert article.duration == ""


def test_collect_respects_the_selection(course):
    from types import SimpleNamespace
    select = lambda s, lec: s.index == 1 and lec.index == 3
    _, sections = collect(course, load_manifest(course), select)
    assert [(s.index, [l.number for l in s.lessons]) for s in sections] == [(1, ["003"])]


def test_merge_course_writes_one_clean_file_next_to_the_folder(course):
    logs = []
    paths = merge_course(course, log=logs.append)
    assert paths == [course.parent / "Mi curso.md"]
    text = paths[0].read_text(encoding="utf-8")
    assert text.startswith("# Mi curso\n\n") and "## Contenido" in text
    assert "curso: " not in text and "<a id=" not in text           # sin YAML ni anclas
    assert "](recursos" not in text and "](../recursos" not in text and "..%2F" not in text
    assert text.index("### 001 - Bienvenida") < text.index("### 002 - Instalación") \
        < text.index("### 003 - Temas puntuales")
    assert "[00:01] Hola. Adiós." in text                            # marca sin URL
    assert "#### Recursos" in text
    assert any("Mi curso.md" in line for line in logs)


def test_merge_course_includes_the_course_link_from_the_readme(course):
    (course / "README.md").write_text("# Mi curso\n\n[Abrir el curso en Udemy](https://u.example/c)\n",
                                      encoding="utf-8")
    assert course_url(course) == "https://u.example/c"
    text = merge_course(course)[0].read_text(encoding="utf-8")
    assert "[Abrir el curso en Udemy](https://u.example/c)" in text


def test_merge_course_splits_and_cleans_up_stale_files(course):
    paths = merge_course(course, max_words=20)
    assert len(paths) > 1 and paths[0].name == f"Mi curso (parte 1 de {len(paths)}).md"
    assert all(p.is_file() for p in paths)
    assert f"(parte 1 de {len(paths)})" in paths[0].read_text(encoding="utf-8").split("\n")[0]
    logs = []
    single = merge_course(course, max_words=0, log=logs.append)
    assert single == [course.parent / "Mi curso.md"]
    assert not any(p.exists() for p in paths)                       # las partes viejas se borran
    assert not any("dividió" in line for line in logs)


def test_merge_course_warns_when_it_splits(course):
    logs = []
    merge_course(course, max_words=20, log=logs.append)
    assert any("se dividió en" in line for line in logs)


def test_merge_course_errors(tmp_path, course):
    with pytest.raises(UdemyError, match="no parece un curso descargado"):
        merge_course(tmp_path / "vacio")
    with pytest.raises(UdemyError, match="negativo"):
        merge_course(course, max_words=-1)
    with pytest.raises(UdemyError, match="Markdown"):
        merge_course(course, select=lambda s, lec: False)


# ---- CLI ---------------------------------------------------------------------------------
def parse(*argv):
    return cli.build_parser().parse_args(list(argv))


def test_cli_merge_flags_and_conflicts():
    assert cli.merge_options(parse("x")) is False
    assert cli.merge_options(parse("--merge", "x")) is True
    assert cli.merge_options(parse("--merge-from", "carpeta")) is True
    assert parse("x").merge_words == 400_000 and parse("--merge-words", "0", "x").merge_words == 0
    for bad in (["--merge", "--single"], ["--merge", "--txt"], ["--merge", "--format", "txt"]):
        with pytest.raises(UdemyError, match="Markdown"):
            cli.merge_options(parse(*bad, "x"))
    with pytest.raises(UdemyError, match="negativo"):
        cli.merge_options(parse("--merge", "--merge-words", "-5", "x"))


def test_merge_from_runs_without_a_browser(course, capsys):
    assert cli.main(["--merge-from", str(course)]) == 0
    assert (course.parent / "Mi curso.md").is_file()
    assert "Mi curso.md" in capsys.readouterr().out


def test_merge_from_respects_ranges_and_reports_errors(course, tmp_path_factory, capsys):
    assert cli.main(["--merge-from", str(course), "--sections", "1"]) == 0
    text = (course.parent / "Mi curso.md").read_text(encoding="utf-8")
    assert "### 001 - Bienvenida" not in text and "### 002 - Instalación" in text
    empty = tmp_path_factory.mktemp("vacio")
    assert cli.main(["--merge-from", str(empty)]) == 1
    assert "no parece un curso descargado" in capsys.readouterr().err
    assert cli.main(["--merge-from", str(course), "--txt"]) == 1


def test_merge_runs_after_the_download_and_is_reported(make_client, tmp_path, capsys):
    from test_cli import course_page, job
    from test_download import FILES
    from conftest import FakeContext
    ctx = FakeContext(dict(FILES))
    course_, stats, output = cli.download_one(make_client(course_page(), ctx), 123,
                                               job(merge=True, merge_words=400_000), tmp_path,
                                               log=lambda *_: None)
    assert stats.merged == [tmp_path / "Mi curso.md"] and stats.merged[0].is_file()
    assert output == tmp_path / "Mi curso" and (output / "README.md").is_file()
    cli.report(stats, output, job(merge=True))
    assert "Unificado:" in capsys.readouterr().out


def test_merge_is_skipped_when_nothing_was_downloaded(make_client, tmp_path):
    from test_cli import course_page, job
    from conftest import FakeContext
    _, stats, _ = cli.download_one(make_client(course_page(), FakeContext()), 123,
                                   job(merge=True, select=lambda s, lec: lec.index == 1),
                                   tmp_path, log=lambda *_: None)     # su subtítulo da 404
    assert stats.merged == [] and not (tmp_path / "Mi curso.md").exists()
