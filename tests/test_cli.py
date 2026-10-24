import pytest

from conftest import FakeContext, load_json
from udemy_transcripts import cli
from udemy_transcripts.curriculum import parse_curriculum
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
    help_text = cli.build_parser().format_help()
    assert "Proyectos/learning" not in help_text and "~/Udemy-Transcripts" in help_text    # B1


def test_main_requires_course_or_list(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


def test_download_writes_one_file_per_video_in_section_folders(make_client, tmp_path):
    ctx = FakeContext({"https://cdn.example/900.vtt": (200, VTT),
                       "https://cdn.example/901-en.vtt": (200, VTT)})
    logs = []
    stats = cli.download_transcripts(make_client(context=ctx), course(), ["es", "en"],
                                     tmp_path, 100, False, log=logs.append, pause=0)
    assert (stats.saved, stats.no_captions, stats.failed) == (2, 1, 0)
    assert (tmp_path / "00 - General" / "001 - Bienvenida.txt").read_text(encoding="utf-8") \
        == "Hola.\nAdiós.\n"
    assert (tmp_path / "01 - Introducción- ¿qué es-" / "002 - Instalación.txt").exists()
    assert any("[3/3]" in line and "sin subtítulos" in line for line in logs)    # progreso


def test_download_warns_when_language_differs(make_client, tmp_path):     # B5
    ctx = FakeContext({"https://cdn.example/900.vtt": (200, VTT),
                       "https://cdn.example/901-en.vtt": (200, VTT)})
    logs = []
    cli.download_transcripts(make_client(context=ctx), course(), ["es", "en"],
                             tmp_path, 100, False, log=logs.append, pause=0)
    assert not any("no hay" in line for line in logs if "Bienvenida" in line)
    (english,) = [line for line in logs if "Instalación" in line]
    assert "usando en_US, no hay es" in english


def test_download_counts_failures_instead_of_pretending_success(make_client, tmp_path):   # B3
    ctx = FakeContext({"https://cdn.example/900.vtt": (403, "denied")})
    logs = []
    stats = cli.download_transcripts(make_client(context=ctx), course(), ["es"],
                                     tmp_path, 100, False, log=logs.append, pause=0)
    assert stats.saved == 0 and stats.failed == 2
    assert any("HTTP 403" in line and "caducada" in line for line in logs)


def test_download_single_mode_collects_parts_without_files(make_client, tmp_path):
    ctx = FakeContext({"https://cdn.example/900.vtt": (200, VTT),
                       "https://cdn.example/901-en.vtt": (200, VTT)})
    stats = cli.download_transcripts(make_client(context=ctx), course(), ["es"],
                                     None, 0, True, log=lambda *_: None, pause=0)
    assert stats.saved == 2 and len(stats.parts) == 2
    assert stats.parts[0].startswith("=" * 70 + "\n[001] General — Bienvenida")
    assert list(tmp_path.iterdir()) == []
