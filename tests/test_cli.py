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
    help_text = cli.build_parser().format_help()
    assert "Proyectos/learning" not in help_text and "~/Udemy-Transcripts" in help_text    # B1


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
