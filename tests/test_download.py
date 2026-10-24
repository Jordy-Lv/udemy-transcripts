import json
import os

import pytest

from conftest import FakeContext, load_json
from udemy_transcripts.courses import CourseInfo
from udemy_transcripts.curriculum import parse_curriculum
from udemy_transcripts.download import download_course
from udemy_transcripts.manifest import MANIFEST_NAME, Manifest
from udemy_transcripts.errors import UdemyError
from udemy_transcripts.render.common import RenderOptions
from udemy_transcripts.util import fs_path

CRLF = "\r\n"
VTT = CRLF.join(["WEBVTT", "", "1", "00:00:01.000 --> 00:00:03.000", "Hola.", "",
                 "2", "00:00:03.000 --> 00:00:04.000", "Adiós.", ""])
VTT_LATER = CRLF.join(["WEBVTT", "", "00:01:10.000 --> 00:01:12.000", "Mucho después.", ""])
COURSE = CourseInfo("123", "Mi curso", "mi-curso", "https://seti.udemy.com")
FILES = {"https://cdn.example/900.vtt": (200, VTT), "https://cdn.example/901-en.vtt": (200, VTT)}
MD = RenderOptions()
TXT = RenderOptions(format="txt", width=0)

INTRO = "00 - General"
SECTION1 = "01 - Introducción- ¿qué es-"


def sections():
    return parse_curriculum(load_json("curriculum.json")["results"])


def run(make_client, course_dir, opts=MD, files=None, secs=None, update=False, single=False,
        manifest="auto", logs=None, context=None):
    ctx = context or FakeContext(dict(FILES if files is None else files))
    if manifest == "auto":
        manifest = None if single else Manifest.load(course_dir / MANIFEST_NAME, 123,
                                                     log=lambda *_: None)
    stats = download_course(make_client(context=ctx), COURSE, secs or sections(), ["es", "en"],
                            opts, course_dir, single, update, manifest,
                            log=(logs if logs is not None else []).append, pause=0)
    return stats, ctx


def test_markdown_course_layout(make_client, tmp_path):
    stats, _ = run(make_client, tmp_path)
    assert (stats.saved, stats.no_captions, stats.failed, stats.up_to_date) == (2, 1, 0, 0)
    lesson = tmp_path / INTRO / "001 - Bienvenida.md"
    text = lesson.read_text(encoding="utf-8")
    assert text.startswith('---\ncurso: "Mi curso"\nseccion: "General"\nleccion: "Bienvenida"\n')
    assert "[00:01](https://seti.udemy.com/course/mi-curso/learn/lecture/900?start=1) Hola. Adiós." in text
    assert (tmp_path / SECTION1 / "002 - Instalación.md").is_file()
    assert (tmp_path / "README.md").is_file() and (tmp_path / MANIFEST_NAME).is_file()


def test_index_links_to_the_written_files(make_client, tmp_path):
    run(make_client, tmp_path)
    index = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "2 de 3 lecciones con transcripción" in index
    assert "(00%20-%20General/001%20-%20Bienvenida.md)" in index
    assert "004 - leccion-004 — sin subtítulos" in index.replace("\\", "")


def test_txt_format_has_no_index_but_keeps_the_manifest(make_client, tmp_path):
    run(make_client, tmp_path, opts=TXT)
    text = (tmp_path / INTRO / "001 - Bienvenida.txt").read_text(encoding="utf-8")
    assert text == "[00:01] Hola.\nAdiós.\n"
    assert not (tmp_path / "README.md").exists() and (tmp_path / MANIFEST_NAME).is_file()


def test_no_timestamps_option(make_client, tmp_path):
    run(make_client, tmp_path, opts=RenderOptions(format="txt", width=0, timestamps=False))
    assert (tmp_path / INTRO / "001 - Bienvenida.txt").read_text(encoding="utf-8") == "Hola.\nAdiós.\n"


def test_language_note_and_progress_in_the_log(make_client, tmp_path):
    logs = []
    run(make_client, tmp_path, logs=logs)
    assert any("[1/3]" in line and "(es_LA)" in line for line in logs)
    (english,) = [line for line in logs if "Instalación" in line]
    assert "usando en_US, no hay es" in english


def test_failures_are_counted_and_not_recorded(make_client, tmp_path):
    logs = []
    stats, _ = run(make_client, tmp_path, files={"https://cdn.example/900.vtt": (403, "x")},
                   logs=logs)
    assert (stats.saved, stats.failed, stats.ok) == (0, 2, 0)
    assert any("HTTP 403" in line and "caducada" in line for line in logs)
    manifest = json.loads((tmp_path / MANIFEST_NAME).read_text(encoding="utf-8")) \
        if (tmp_path / MANIFEST_NAME).exists() else {"lectures": {}}
    assert manifest["lectures"] == {}


def test_update_skips_everything_that_is_unchanged(make_client, tmp_path):
    run(make_client, tmp_path)
    logs = []
    stats, ctx = run(make_client, tmp_path, update=True, logs=logs)
    assert (stats.saved, stats.up_to_date, stats.ok) == (0, 2, 2)
    assert ctx.requested == []                      # ni una descarga
    assert sum("sin cambios" in line for line in logs) == 2
    assert (tmp_path / "README.md").is_file()       # el índice se regenera igual


def test_without_update_everything_is_downloaded_again(make_client, tmp_path):
    run(make_client, tmp_path)
    stats, ctx = run(make_client, tmp_path)
    assert stats.saved == 2 and len(ctx.requested) == 2


def test_update_redownloads_a_lesson_whose_subtitle_changed(make_client, tmp_path):
    run(make_client, tmp_path)
    secs = sections()
    secs[0].lectures[0].captions[0].update(file_name="nuevo.vtt",
                                           url="https://cdn.example/new.vtt")
    files = dict(FILES, **{"https://cdn.example/new.vtt": (200, VTT_LATER)})
    stats, ctx = run(make_client, tmp_path, files=files, secs=secs, update=True)
    assert (stats.saved, stats.up_to_date) == (1, 1)
    assert ctx.requested == ["https://cdn.example/new.vtt"]
    assert "Mucho después." in (tmp_path / INTRO / "001 - Bienvenida.md").read_text(encoding="utf-8")


def test_update_downloads_only_new_lessons(make_client, tmp_path):
    first = sections()
    removed = first[1].lectures.pop(0)                      # 901 aún no existe
    run(make_client, tmp_path, secs=first)
    stats, ctx = run(make_client, tmp_path, update=True)
    assert (stats.saved, stats.up_to_date) == (1, 1)
    assert ctx.requested == ["https://cdn.example/901-en.vtt"] and removed.id == 901


def test_update_regenerates_when_render_options_change(make_client, tmp_path):
    run(make_client, tmp_path)
    stats, ctx = run(make_client, tmp_path, update=True, opts=RenderOptions(timestamps=False))
    assert (stats.saved, stats.up_to_date) == (2, 0)
    assert "?start=" not in (tmp_path / INTRO / "001 - Bienvenida.md").read_text(encoding="utf-8")


def test_update_redownloads_a_deleted_file(make_client, tmp_path):
    run(make_client, tmp_path)
    (tmp_path / INTRO / "001 - Bienvenida.md").unlink()
    stats, ctx = run(make_client, tmp_path, update=True)
    assert (stats.saved, stats.up_to_date) == (1, 1)
    assert (tmp_path / INTRO / "001 - Bienvenida.md").is_file()


def test_renamed_lesson_is_rewritten_and_the_old_file_is_kept(make_client, tmp_path):
    run(make_client, tmp_path)
    secs = sections()
    secs[0].lectures[0].title = "Bienvenida al curso"
    logs = []
    stats, _ = run(make_client, tmp_path, secs=secs, update=True, logs=logs)
    assert stats.saved == 1 and stats.orphans == [f"{INTRO}/001 - Bienvenida.md"]
    assert (tmp_path / INTRO / "001 - Bienvenida.md").is_file()          # no se borra
    assert (tmp_path / INTRO / "001 - Bienvenida al curso.md").is_file()
    assert any("se conserva el archivo anterior" in line for line in logs)


def test_an_interrupted_run_can_be_resumed(make_client, tmp_path):
    class Interrupt(FakeContext):
        def get(self, url):
            if url.endswith("901-en.vtt"):
                raise KeyboardInterrupt
            return super().get(url)

    with pytest.raises(KeyboardInterrupt):
        run(make_client, tmp_path, context=Interrupt(dict(FILES)))
    assert (tmp_path / INTRO / "001 - Bienvenida.md").is_file()
    index = (tmp_path / "README.md").read_text(encoding="utf-8")        # índice parcial
    assert "1 de 3 lecciones con transcripción" in index
    stats, ctx = run(make_client, tmp_path, update=True)
    assert (stats.saved, stats.up_to_date) == (1, 1)
    assert ctx.requested == ["https://cdn.example/901-en.vtt"]


def test_single_markdown_collects_blocks_without_writing_files(make_client, tmp_path):
    stats, _ = run(make_client, tmp_path, single=True)
    assert stats.saved == 2 and len(stats.items) == 2
    assert stats.items[0][2].startswith('<a id="lec-900"></a>')
    assert list(tmp_path.iterdir()) == []


def test_single_txt_blocks_keep_the_classic_header(make_client, tmp_path):
    stats, _ = run(make_client, tmp_path, single=True, opts=TXT)
    assert stats.items[0][2].startswith("=" * 70 + "\n[001] 00 - General — Bienvenida")
    assert stats.items[0][2].endswith("[00:01] Hola.\nAdiós.")


@pytest.mark.skipif(os.name != "nt", reason="el límite de 260 caracteres es de Windows")
def test_long_output_paths_work_on_windows(make_client, tmp_path):
    deep = tmp_path.joinpath(*["carpeta-muy-larga-" + "x" * 30] * 5)
    assert len(str(deep)) > 230
    secs = sections()
    secs[0].lectures[0].title = "t" * 110                       # suma > 260 caracteres
    stats, _ = run(make_client, deep, secs=secs)
    assert stats.saved == 2 and stats.failed == 0
    assert fs_path(deep / INTRO / ("001 - " + "t" * 110 + ".md")).is_file()
    assert fs_path(deep / "README.md").is_file()
    assert Manifest.load(deep / MANIFEST_NAME, 123).entries      # el manifest también


def test_fs_path_leaves_short_paths_alone(tmp_path):
    assert fs_path(tmp_path / "a.md") == tmp_path / "a.md"


def test_write_errors_are_reported_cleanly(make_client, tmp_path):
    blocker = tmp_path / INTRO
    blocker.write_text("soy un archivo, no una carpeta", encoding="utf-8")
    with pytest.raises(UdemyError, match="No pude escribir"):
        run(make_client, tmp_path)
