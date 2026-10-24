import pytest

from udemy_transcripts.errors import UdemyError

from udemy_transcripts import cli
from udemy_transcripts.portal import Portal, portal_from_ref
from udemy_transcripts.util import safe_name

VTT = "WEBVTT\r\n\r\n1\r\n00:00:01.000 --> 00:00:02.000\r\nHola.\r\n\r\n2\r\n00:00:02.000 --> 00:00:03.000\r\nAdiós.\r\n"


def course():
    return parse_curriculum(load_json("curriculum.json")["results"])


def test_package_import_wins_over_wrapper_script():
    import udemy_transcripts
    assert udemy_transcripts.__file__.endswith("__init__.py")


def test_safe_name():
    assert safe_name('a/b\\c:d*e?f"g<h>i|j') == "a-b-c-d-e-f-g-h-i-j"
    assert safe_name("  muchos   espacios ") == "muchos espacios"
    assert safe_name("termina en punto...") == "termina en punto"
    assert safe_name("") == "sin título" and safe_name(None) == "sin título" and safe_name("...") == "sin título"
    assert len(safe_name("x" * 500)) == 120


def test_portal_detection():
    assert portal_from_ref("https://seti.udemy.com/course/x/learn/").host == "seti.udemy.com"
    assert portal_from_ref("https://SETI.udemy.com").host == "seti.udemy.com"
    assert portal_from_ref("seti.udemy.com/course/x").host == "seti.udemy.com"
    assert portal_from_ref("https://www.udemy.com/course/x/") == Portal()
    for other in ("mi-curso", "12345", "https://udemy.com/course/x", "https://evil.com/seti.udemy.com/"):
        assert portal_from_ref(other) == Portal()
    portal = Portal("seti.udemy.com")
    assert portal.api == "https://seti.udemy.com/api-2.0" and portal.is_business
    assert not Portal().is_business


def test_parser_defaults_and_help_text():
    args = cli.build_parser().parse_args(["curso"])
    assert (args.lang, args.width, args.txt, args.do_list) == ("es,en", 100, False, False)
    out_help = cli.build_parser()._option_string_actions["--out"].help
    assert "Proyectos/learning" not in out_help and "~/Udemy-Transcripts" in out_help    # B1


def test_main_requires_course_or_list(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


def parse(*argv):
    return cli.build_parser().parse_args(list(argv) + ["curso"])


def test_options_defaults_are_markdown_with_timestamps():
    opts, single = cli.options_from_args(parse())
    assert (opts.format, opts.timestamps, opts.ts_every, opts.width, single) ==         ("md", True, 0, 100, False)


def test_options_flags():
    opts, single = cli.options_from_args(
        parse("--format", "txt", "--single", "--no-timestamps", "--ts-every", "60", "--width", "0"))
    assert (opts.format, opts.timestamps, opts.ts_every, opts.width, single) ==         ("txt", False, 60, 0, True)


def test_legacy_txt_flag_is_single_file_in_txt():
    opts, single = cli.options_from_args(parse("--txt"))
    assert (opts.format, single) == ("txt", True)


def test_negative_numbers_are_rejected():
    for flags in (["--width", "-1"], ["--ts-every", "-5"]):
        with pytest.raises(UdemyError):
            cli.options_from_args(parse(*flags))


def test_update_flag_and_unknown_format():
    assert parse("--update").update is True and parse().update is False
    with pytest.raises(SystemExit):
        parse("--format", "pdf")


# ---- download_one: el flujo de un curso con navegador simulado ---------------------
def course_page():
    from conftest import FakePage, js, load_json

    def handler(url):
        if "/subscriber-curriculum-items/" in url:
            return js(200, load_json("curriculum.json"))
        if "/courses/123/" in url:
            return js(200, {"title": "Mi curso", "url": "/course/mi-curso/"})
        return js(404)
    return FakePage(handler=handler)


def job(**kw):
    from udemy_transcripts.render.common import RenderOptions
    from udemy_transcripts.resources import ResourceOptions
    values = dict(langs=["es", "en"], opts=RenderOptions(), single=False, res=ResourceOptions(),
                  select=None, update=False)
    values.update(kw)
    return cli.Job(**values)


def test_download_one_writes_a_course_folder(make_client, tmp_path):
    from conftest import FakeContext
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHola.\n"
    ctx = FakeContext({"https://cdn.example/900.vtt": (200, vtt),
                       "https://cdn.example/901-en.vtt": (200, vtt)})
    logs = []
    course, stats, output = cli.download_one(make_client(course_page(), ctx), 123, job(),
                                              tmp_path, log=logs.append)
    assert (course.title, stats.saved, output) == ("Mi curso", 3, tmp_path / "Mi curso")
    assert (output / "README.md").is_file() and (output / ".udemy-transcripts.json").is_file()
    assert any("Leyendo temario" in line for line in logs)


def test_download_one_single_file_goes_next_to_the_course_folder(make_client, tmp_path):
    from conftest import FakeContext
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHola.\n"
    ctx = FakeContext({"https://cdn.example/900.vtt": (200, vtt),
                       "https://cdn.example/901-en.vtt": (200, vtt)})
    _, stats, output = cli.download_one(make_client(course_page(), ctx), 123,
                                        job(single=True), tmp_path, log=lambda *_: None)
    assert output == tmp_path / "Mi curso.md" and output.is_file()
    assert "## Contenido" in output.read_text(encoding="utf-8")
    assert not (tmp_path / "Mi curso").exists()          # sin carpeta si no hay recursos


def test_download_one_honours_an_explicit_course_dir(make_client, tmp_path):
    from conftest import FakeContext
    _, _, output = cli.download_one(make_client(course_page(), FakeContext()), 123, job(),
                                    tmp_path, course_dir=tmp_path / "ruta" / "01 - Curso",
                                    log=lambda *_: None)
    assert output == tmp_path / "ruta" / "01 - Curso" and output.is_dir()


def test_download_one_rejects_courses_without_content(make_client, tmp_path):
    from conftest import FakeContext, FakePage, js
    page = FakePage(handler=lambda url: js(200, {"count": 1, "next": None, "results": [
        {"_class": "chapter", "title": "Solo un quiz", "object_index": 1},
        {"_class": "quiz", "id": 1, "title": "Q"}]}) if "curriculum" in url
        else js(200, {"title": "Vacío", "url": "/course/v/"}))
    with pytest.raises(UdemyError, match="ni artículos"):
        cli.download_one(make_client(page, FakeContext()), 5, job(), tmp_path, log=lambda *_: None)


def test_download_one_resources_only_needs_resources(make_client, tmp_path):
    from conftest import FakeContext, FakePage, js
    from udemy_transcripts.resources import ResourceOptions
    page = FakePage(handler=lambda url: js(200, {"count": 2, "next": None, "results": [
        {"_class": "chapter", "title": "C", "object_index": 1},
        {"_class": "lecture", "id": 1, "title": "L", "object_index": 1,
         "asset": {"asset_type": "Article", "body": "<p>x</p>"}}]}) if "curriculum" in url
        else js(200, {"title": "Sin adjuntos", "url": "/course/s/"}))
    with pytest.raises(UdemyError, match="no tiene recursos"):
        cli.download_one(make_client(page, FakeContext()), 5,
                         job(res=ResourceOptions(enabled=True, only=True)), tmp_path,
                         log=lambda *_: None)


def test_summary_line():
    from udemy_transcripts.download import Stats
    from udemy_transcripts.resources import ResourceOptions
    stats = Stats(saved=3, up_to_date=2, no_captions=1, empty=1, files=4, files_done=2, failed=1)
    assert cli.summary(stats, job(update=True, res=ResourceOptions(enabled=True))) == (
        "✓ Listo: 3 lecciones, 2 sin cambios, 4 recursos (2 ya estaban), 1 sin subtítulos, "
        "1 artículos vacíos, 1 con error.")
    assert cli.summary(Stats(), job()).startswith("✗ Listo: 0 lecciones, 0 sin subtítulos")
    only = cli.summary(Stats(files=2), job(res=ResourceOptions(enabled=True, only=True)))
    assert only == "✓ Listo: 2 recursos, 0 con error."
