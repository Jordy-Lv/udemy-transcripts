import pytest

from conftest import FakePage, js
from udemy_transcripts import cli
from udemy_transcripts.curriculum import Lecture, Section
from udemy_transcripts.errors import BlockedError, NotLoggedInError, UdemyError
from udemy_transcripts.paths import (fetch_learning_path, learning_path_id, parse_path_sections,
                                     path_index)
from udemy_transcripts.ranges import in_ranges, make_selector, parse_ranges
from udemy_transcripts.portal import Portal


# ---- rangos ---------------------------------------------------------------------
def test_parse_ranges():
    assert parse_ranges("3-5,8, 12-") == [(3, 5), (8, 8), (12, None)]
    assert parse_ranges(None) == [] and parse_ranges("  ") == []


@pytest.mark.parametrize("spec", ["a", "3-x", "-5", "1,,2", "5-3", "3 5", "1.5", "--2"])
def test_parse_ranges_rejects_garbage(spec):
    with pytest.raises(UdemyError, match="--sections"):
        parse_ranges(spec)


def test_range_error_names_the_flag():
    with pytest.raises(UdemyError, match="--lectures"):
        parse_ranges("x", "--lectures")


def test_in_ranges():
    ranges = parse_ranges("3-5,8,12-")
    assert [n for n in range(0, 15) if in_ranges(n, ranges)] == [3, 4, 5, 8, 12, 13, 14]
    assert in_ranges(7, []) and in_ranges(None, [])        # sin filtro: todo
    assert not in_ranges(None, ranges)                      # sin número no se puede elegir


def test_selector_combines_sections_and_lectures():
    pick = make_selector(parse_ranges("2-3"), parse_ranges("10-20"))
    lec = lambda n: Lecture(n, "x", n, "Video", [])
    assert pick(Section(2, "a"), lec(10)) and pick(Section(3, "a"), lec(20))
    assert not pick(Section(1, "a"), lec(10)) and not pick(Section(2, "a"), lec(21))
    assert make_selector([], [])(Section(9, "a"), lec(99))


def args_for(*argv):
    return cli.build_parser().parse_args(list(argv) + ["curso"])


def test_cli_builds_selector_and_resource_options():
    assert cli.selector_from_args(args_for()) is None
    pick = cli.selector_from_args(args_for("--sections", "2", "--lectures", "5-"))
    assert pick(Section(2, "s"), Lecture(1, "x", 5, "Video", []))
    assert not pick(Section(2, "s"), Lecture(1, "x", 4, "Video", []))
    with pytest.raises(UdemyError):
        cli.selector_from_args(args_for("--sections", "x"))
    opts = cli.resource_options(args_for())
    assert (opts.enabled, opts.only, opts.types, opts.max_size, opts.assume_yes) == \
        (False, False, None, 500 * 1024 ** 2, False)
    opts = cli.resource_options(args_for("--resources-only", "--resource-types", "pdf,zip",
                                         "--max-size", "2GB", "--yes"))
    assert (opts.enabled, opts.only, opts.types, opts.max_size, opts.assume_yes) == \
        (True, True, {"pdf", "zip"}, 2 * 1024 ** 3, True)
    assert cli.resource_options(args_for("--resources")).enabled
    with pytest.raises(UdemyError):
        cli.resource_options(args_for("--max-size", "grande"))


# ---- rutas de aprendizaje ---------------------------------------------------------
def test_learning_path_id():
    assert learning_path_id("https://seti.udemy.com/learning-paths/1283634/") == "1283634"
    assert learning_path_id("https://seti.udemy.com/learning-paths/1283634") == "1283634"
    assert learning_path_id("https://seti.udemy.com/learning-path/77/?x=1") == "77"
    assert learning_path_id("https://seti.udemy.com/course/learning-paths-intro/") is None
    assert learning_path_id("12345") is None and learning_path_id(None) is None


SECTION_ROWS = [
    {"id": 1, "title": "", "items": []},
    {"id": 2, "title": "Aprende", "items": [
        {"related_object_type": "course", "title": "", "is_removed": False,
         "content": {"id": 2645936, "title": "AWS Certified Cloud Practitioner",
                     "url": "/course/aws-certified-cloud-practitioner-training-course/"}},
        {"related_object_type": "course", "is_removed": True,
         "content": {"id": 9, "title": "Retirado"}},
        {"related_object_type": "course", "title": "Curso 2", "content": {"id": 2059853}},
    ]},
    {"id": 3, "title": "Practica", "items": [
        {"related_object_type": "lab", "title": "Autoescalado", "content": {"id": 226}},
        {"related_object_type": "adaptive_assessment_assessment", "content": {"title": "Examen"}},
    ]},
]


def test_parse_path_sections_keeps_courses_and_labels_the_rest():
    sections = parse_path_sections(SECTION_ROWS)
    assert [s.title for s in sections] == ["Aprende", "Practica"]          # la vacía se descarta
    first, second, lab, exam = [i for s in sections for i in s.items]
    assert (first.kind, first.course_id, first.slug, first.title) == \
        ("course", "2645936", "aws-certified-cloud-practitioner-training-course",
         "AWS Certified Cloud Practitioner")
    assert (second.course_id, second.title, second.slug) == ("2059853", "Curso 2", None)
    assert (lab.kind, lab.course_id, exam.title) == ("lab", None, "Examen")


def test_fetch_learning_path(make_client):
    page = FakePage([js(200, {"title": "AWS CCP", "description": "Ruta de prueba"}),
                     js(200, {"results": SECTION_ROWS, "next": None})])
    path = fetch_learning_path(make_client(page, portal=Portal("seti.udemy.com")), 1283634)
    assert (path.id, path.title, len(path.courses)) == ("1283634", "AWS CCP", 2)
    assert page.calls[0] == "https://seti.udemy.com/api-2.0/learning-paths/1283634/"
    assert "/learning-paths/1283634/sections/?page_size=9999" in page.calls[1]
    assert "fields%5Blearning_path_section_has_item%5D" in page.calls[1]


def test_fetch_learning_path_without_courses_is_an_error(make_client):
    page = FakePage([js(200, {"title": "Solo labs"}),
                     js(200, {"results": SECTION_ROWS[2:], "next": None})])
    with pytest.raises(UdemyError, match="no tiene cursos"):
        fetch_learning_path(make_client(page, portal=Portal("seti.udemy.com")), 5)


def test_path_index_lists_courses_and_non_downloadable_items():
    sections = parse_path_sections(SECTION_ROWS)
    sections[0].items[0].status, sections[0].items[0].folder = "ok", "01 - AWS Certified"
    sections[0].items[1].status = "error: sin acceso"
    from udemy_transcripts.paths import LearningPath
    index = path_index(LearningPath("7", "Mi ruta", "Una descripción.", sections),
                       "https://seti.udemy.com")
    assert index.startswith("# Mi ruta\n\n[Abrir la ruta en Udemy](https://seti.udemy.com/learning-paths/7/)")
    assert "Una descripción." in index
    assert "- [AWS Certified Cloud Practitioner](01%20-%20AWS%20Certified/)" in index
    assert "- Curso 2 — error: sin acceso" in index
    assert "- Autoescalado — laboratorio: no se descarga" in index
    assert "- Examen — evaluación: no se descarga" in index


# ---- descarga de una ruta (con download_one sustituido) ------------------------------
class FakeStats:
    def __init__(self, ok):
        self.ok, self.errors, self.saved = ok, 0, ok
        self.up_to_date = self.no_captions = self.empty = self.files = self.files_done = 0
        self.orphans = []


def make_job():
    from udemy_transcripts.render.common import RenderOptions
    from udemy_transcripts.resources import ResourceOptions
    return cli.Job(["es"], RenderOptions(), False, ResourceOptions(), None, False)


def path_client(make_client):
    return make_client(FakePage([js(200, {"title": "Mi/Ruta: AWS", "description": ""}),
                                 js(200, {"results": SECTION_ROWS, "next": None})]),
                       portal=Portal("seti.udemy.com"))


def test_download_path_puts_each_course_in_a_numbered_folder(make_client, tmp_path, monkeypatch):
    seen = []

    def fake_download_one(client, course_id, job, base, course_dir=None, log=print):
        seen.append((course_id, course_dir))
        if course_id == "2059853":
            raise UdemyError("El curso no tiene lecciones de vídeo ni artículos.")
        return None, FakeStats(5), course_dir

    monkeypatch.setattr(cli, "download_one", fake_download_one)
    code = cli.download_path(path_client(make_client), "7", make_job(), tmp_path)
    path_dir = tmp_path / "Mi-Ruta- AWS"
    assert code == 0
    assert seen == [("2645936", path_dir / "01 - AWS Certified Cloud Practitioner"),
                    ("2059853", path_dir / "02 - Curso 2")]
    index = (path_dir / "README.md").read_text(encoding="utf-8")
    assert "- [AWS Certified Cloud Practitioner](01%20-%20AWS%20Certified%20Cloud%20Practitioner/)" in index
    assert "- Curso 2 — error: El curso no tiene lecciones" in index


def test_download_path_fails_when_nothing_was_downloaded(make_client, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "download_one", lambda *a, **k: (None, FakeStats(0), None))
    assert cli.download_path(path_client(make_client), "7", make_job(), tmp_path) == 1


@pytest.mark.parametrize("error", [NotLoggedInError("sesión"), BlockedError("cloudflare")])
def test_download_path_stops_when_the_session_is_lost(make_client, tmp_path, monkeypatch, error):
    calls = []

    def fake(client, course_id, *a, **k):
        calls.append(course_id)
        raise error
    monkeypatch.setattr(cli, "download_one", fake)
    with pytest.raises(type(error)):
        cli.download_path(path_client(make_client), "7", make_job(), tmp_path)
    assert calls == ["2645936"]                                    # no sigue con el resto
    assert (tmp_path / "Mi-Ruta- AWS" / "README.md").exists()      # y deja el índice


def test_paths_require_a_business_portal():
    args = cli.build_parser().parse_args(["https://www.udemy.com/learning-paths/12/"])
    with pytest.raises(UdemyError, match="Udemy Business"):
        cli.run(args)
