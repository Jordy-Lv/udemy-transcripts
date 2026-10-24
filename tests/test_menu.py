import json

import pytest

from test_tui import make_ui, numbered, typed
from udemy_transcripts import cli, menu
from udemy_transcripts.manifest import MANIFEST_NAME
from udemy_transcripts.menu import (Choices, Settings, build_argv, command_line, find_courses,
                                    load_settings, manifest_course_id, run_menu, save_settings,
                                    validate_target)
from udemy_transcripts.tui import DOWN, END, ENTER, ESC, SPACE, UP

URL = "https://www.udemy.com/course/mi-curso/"


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(menu, "SETTINGS_FILE", tmp_path / "ajustes" / "menu.json")


@pytest.fixture
def calls(monkeypatch):
    """Sustituye al CLI: apunta los argumentos y devuelve el código que se le indique."""
    class Calls(list):
        codes = []

    seen = Calls()
    seen.codes = []

    def fake_main(argv=None):
        seen.append(list(argv))
        return seen.codes.pop(0) if seen.codes else 0

    monkeypatch.setattr(cli, "main", fake_main)
    return seen


# ---- argumentos ---------------------------------------------------------------------------
def test_build_argv_defaults_to_folder_plus_merged_file():
    assert build_argv(URL, Choices(), Settings()) == ["--merge", "--lang", "es,en", URL]


def test_build_argv_covers_every_option():
    choices = Choices(mode="folder", lang="es+en", resources="yes", sections="3-5",
                      study="prompt", update=True)
    settings = Settings(out="D:\\Cursos", business="seti", token="abc")
    assert build_argv("123", choices, settings) == [
        "--lang", "es+en", "--resources", "--sections", "3-5", "--study", "prompt", "--update",
        "--out", "D:\\Cursos", "--business", "seti", "--token", "abc", "123"]
    assert build_argv(URL, Choices(mode="single", resources="only", lectures="10-20"),
                      Settings())[:1] == ["--single"]
    assert "--txt" in build_argv(URL, Choices(mode="txt"), Settings())
    assert "--resources-only" in build_argv(URL, Choices(resources="only"), Settings())


def test_business_is_not_added_when_the_url_already_names_the_portal():
    settings = Settings(business="seti")
    assert "--business" not in build_argv("https://seti.udemy.com/course/x/", Choices(), settings)
    assert "--business" in build_argv("x", Choices(), settings)


def test_argv_parses_with_the_real_cli():
    argv = build_argv(URL, Choices(mode="merge", study="api", sections="1-2"),
                      Settings(token="t", business="seti"))
    args = cli.build_parser().parse_args(argv)
    assert (args.merge, args.study, args.sections, args.course) == (True, "api", "1-2", URL)


def test_command_line_hides_the_token_and_quotes_spaces():
    line = command_line(["--token", "secreto", "--out", "C:\\Mis cursos", URL])
    assert "secreto" not in line and "***" in line
    assert line.startswith("udemy ") and '"C:\\Mis cursos"' in line


def test_validate_target():
    assert validate_target(URL) is None
    assert validate_target("https://seti.udemy.com/learning-paths/12345/") is None
    assert validate_target("mi-curso") is None and validate_target("123456") is None
    assert "sin espacios" in validate_target("dos palabras")
    assert "no es de Udemy" in validate_target("https://example.com/course/x")
    assert "debe ser de un curso" in validate_target("https://www.udemy.com/")


# ---- ajustes y búsqueda de cursos ------------------------------------------------------------
def test_settings_roundtrip_never_stores_the_token(tmp_path):
    path = tmp_path / "s.json"
    save_settings(Settings(out="X", business="seti", lang="es", token="secreto"), path)
    assert "secreto" not in path.read_text(encoding="utf-8")
    loaded = load_settings(path)
    assert (loaded.out, loaded.business, loaded.lang, loaded.token) == ("X", "seti", "es", "")


def test_load_settings_ignores_missing_or_damaged_files(tmp_path):
    assert load_settings(tmp_path / "no-existe.json") == Settings()
    bad = tmp_path / "mal.json"
    bad.write_text("{no es json", encoding="utf-8")
    assert load_settings(bad) == Settings()
    bad.write_text(json.dumps({"out": 5, "business": "seti", "token": "x"}), encoding="utf-8")
    assert load_settings(bad) == Settings(business="seti")


def test_effective_out_prefers_setting_then_env(monkeypatch, tmp_path):
    monkeypatch.setenv("UDEMY_OUT", str(tmp_path / "env"))
    assert Settings().effective_out() == tmp_path / "env"
    assert Settings(out=str(tmp_path / "mio")).effective_out() == tmp_path / "mio"
    monkeypatch.delenv("UDEMY_OUT")
    assert Settings().effective_out() == cli.DEFAULT_OUT


def make_course(root, *parts, course_id="123"):
    folder = root.joinpath(*parts)
    folder.mkdir(parents=True)
    (folder / MANIFEST_NAME).write_text(json.dumps({"course_id": course_id, "lectures": {}}),
                                        encoding="utf-8")
    return folder


def test_find_courses_looks_two_levels_deep(tmp_path):
    a = make_course(tmp_path, "A curso")
    b = make_course(tmp_path, "Ruta", "01 - B")
    (tmp_path / "otra cosa").mkdir()
    assert find_courses(tmp_path) == [a, b]
    assert find_courses(tmp_path / "no-existe") == []
    assert manifest_course_id(a) == "123" and manifest_course_id(tmp_path / "otra cosa") == ""


# ---- flujos del menú ---------------------------------------------------------------------------
def test_download_flow_asks_urls_then_runs_the_cli(calls):
    keys = ([ENTER]                                        # Descargar curso(s)
            + typed(URL) + [ENTER] + typed("987") + [ENTER] + [ENTER]      # dos destinos, vacío
            + [END, ENTER]                                 # ▶ Empezar
            + [ENTER]                                      # ¿Empezar? Sí
            + [ENTER]                                      # pausa al terminar
            + [ESC])                                       # salir
    ui = make_ui(keys)
    assert run_menu(ui, Settings()) == 0
    assert calls == [["--merge", "--lang", "es,en", URL], ["--merge", "--lang", "es,en", "987"]]
    assert ui.pending == []
    assert "udemy --merge --lang es,en" in ui.out.getvalue()      # mostró el comando equivalente


def test_download_flow_options_can_be_changed(calls):
    keys = ([ENTER] + typed(URL) + [ENTER, ENTER]
            + [ENTER, DOWN, ENTER]                         # Formato → «Carpeta por lecciones»
            + [DOWN, ENTER, DOWN, DOWN, ENTER]             # Idiomas → «Solo español»
            + [DOWN, ENTER, DOWN, ENTER]                   # Recursos → «Descargar adjuntos»
            + [DOWN, ENTER, DOWN, ENTER] + typed("2-4") + [ENTER]    # Selección → secciones 2-4
            + [DOWN, ENTER, DOWN, ENTER]                   # Estudio → prompt
            + [DOWN, ENTER, DOWN, ENTER]                   # Solo novedades → sí
            + [END, ENTER, ENTER, ENTER, ESC])
    run_menu(make_ui(keys), Settings())
    assert calls == [["--lang", "es", "--resources", "--sections", "2-4", "--study", "prompt",
                      "--update", URL]]


def test_invalid_url_is_rejected_and_asked_again(calls):
    keys = ([ENTER] + typed("dos palabras") + [ENTER] + typed(URL) + [ENTER, ENTER]
            + [END, ENTER, ENTER, ENTER, ESC])
    ui = make_ui(keys)
    run_menu(ui, Settings())
    assert calls == [["--merge", "--lang", "es,en", URL]]
    assert "sin espacios" in ui.out.getvalue()


def test_declining_the_confirmation_runs_nothing(calls):
    keys = [ENTER] + typed(URL) + [ENTER, ENTER] + [END, ENTER] + [DOWN, ENTER] + [ESC]
    ui = make_ui(keys)
    run_menu(ui, Settings())
    assert calls == [] and ui.pending == []


def test_esc_cancels_each_step_without_running(calls):
    run_menu(make_ui([ENTER, ESC, ESC]), Settings())                         # sin URL
    run_menu(make_ui([ENTER] + typed(URL) + [ENTER, ENTER, ESC, ESC]), Settings())   # sin opciones
    assert calls == []


def test_a_failing_download_does_not_stop_the_next_one(calls):
    calls.codes[:] = [1, 0]
    keys = ([ENTER] + typed("111") + [ENTER] + typed("222") + [ENTER, ENTER]
            + [END, ENTER, ENTER, ENTER, ESC])
    ui = make_ui(keys)
    run_menu(ui, Settings())
    assert [c[-1] for c in calls] == ["111", "222"]
    out = ui.out.getvalue()
    assert "✗ 111" in out and "✓ 222" in out


def test_argparse_errors_do_not_kill_the_menu(monkeypatch):
    def boom(argv=None):
        raise SystemExit(2)
    monkeypatch.setattr(cli, "main", boom)
    keys = [ENTER] + typed(URL) + [ENTER, ENTER] + [END, ENTER, ENTER, ENTER, ESC]
    assert run_menu(make_ui(keys), Settings()) == 0


def test_settings_screen_edits_and_saves(tmp_path):
    settings = Settings()
    keys = ([DOWN, DOWN, DOWN, ENTER]                      # Ajustes
            + [DOWN, ENTER] + typed("seti") + [ENTER]      # Business
            + [UP, ENTER] + typed("D:\\Cursos") + [ENTER]  # Carpeta
            + [DOWN, DOWN, DOWN, ENTER] + typed("tok") + [ENTER]   # Token
            + [ESC, ESC])
    assert run_menu(make_ui(keys), settings) == 0
    assert (settings.business, settings.out, settings.token) == ("seti", "D:\\Cursos", "tok")
    saved = json.loads(menu.SETTINGS_FILE.read_text(encoding="utf-8"))
    assert saved["business"] == "seti" and "token" not in saved


def test_existing_course_can_be_merged_offline(tmp_path, calls):
    course = make_course(tmp_path, "Mi curso")
    keys = [DOWN, DOWN, ENTER, ENTER, ENTER, ENTER, ESC]       # Actualizar/unificar → curso → unificar
    run_menu(make_ui(keys), Settings(out=str(tmp_path)))
    assert calls == [["--merge-from", str(course)]]


def test_existing_course_study_and_update(tmp_path, calls):
    course = make_course(tmp_path, "Mi curso", course_id="555")
    keys = [DOWN, DOWN, ENTER, ENTER, DOWN, ENTER, ENTER, ENTER, ESC]     # estudio → prompt
    run_menu(make_ui(keys), Settings(out=str(tmp_path)))
    assert calls == [["--study", "prompt", "--study-from", str(course)]]
    calls.clear()
    keys = [DOWN, DOWN, ENTER, ENTER, DOWN, DOWN, ENTER, ENTER, ENTER, ESC]  # update, regenerar sí
    run_menu(make_ui(keys), Settings(out=str(tmp_path), business="seti"))
    assert calls == [["--merge", "555", "--update", "--out", str(tmp_path), "--business", "seti"]]


def test_existing_course_update_is_refused_inside_a_path(tmp_path, calls):
    make_course(tmp_path, "Ruta", "01 - Curso")
    keys = [DOWN, DOWN, ENTER, ENTER, DOWN, DOWN, ENTER, ENTER, ESC]
    ui = make_ui(keys)
    run_menu(ui, Settings(out=str(tmp_path)))
    assert calls == [] and "Solo puedo actualizar" in ui.out.getvalue()


def test_existing_courses_screen_without_downloads(tmp_path, calls):
    ui = make_ui([DOWN, DOWN, ENTER, ENTER, ESC])
    run_menu(ui, Settings(out=str(tmp_path / "vacío")))
    assert calls == [] and "No encontré cursos descargados" in ui.out.getvalue()


def test_my_courses_lists_and_downloads_the_marked_ones(monkeypatch, calls):
    import contextlib

    @contextlib.contextmanager
    def fake_open(args, portal):
        assert args.do_list and portal.host == "seti.udemy.com"
        yield object()

    monkeypatch.setattr(cli, "open_client", fake_open)
    monkeypatch.setattr(menu, "list_courses", lambda client: [
        {"id": 1, "title": "Uno"}, {"id": 2, "title": "Dos"}, {"id": 3, "title": "Tres"}])
    keys = ([DOWN, ENTER] + [DOWN, SPACE, DOWN, SPACE, ENTER]     # marca Dos y Tres
            + [END, ENTER, ENTER, ENTER, ESC])
    run_menu(make_ui(keys), Settings(business="seti"))
    assert [c[-1] for c in calls] == ["2", "3"]
    assert all("--business" in c for c in calls)


def test_my_courses_shows_login_errors(monkeypatch, calls):
    import contextlib
    from udemy_transcripts.errors import UdemyError

    @contextlib.contextmanager
    def fake_open(args, portal):
        raise UdemyError("no hay sesión")
        yield

    monkeypatch.setattr(cli, "open_client", fake_open)
    ui = make_ui([DOWN, ENTER, ENTER, ESC])
    run_menu(ui, Settings())
    assert "no hay sesión" in ui.out.getvalue() and calls == []


def test_numbered_fallback_drives_the_whole_menu(calls):
    ui = numbered(["1", URL, "", "7", "1", "", "5"])
    # 1 Descargar · URL · vacío · opción 7 «Empezar» · 1 «Sí» · Enter (pausa) · 5 Salir
    assert run_menu(ui, Settings()) == 0
    assert calls == [["--merge", "--lang", "es,en", URL]]


def test_ctrl_c_leaves_the_menu_cleanly():
    def read_key():
        raise KeyboardInterrupt
    from udemy_transcripts.tui import Console
    import io
    ui = Console(read_key=read_key, out=io.StringIO(), interactive=True)
    assert run_menu(ui, Settings()) == 130


# ---- entrada desde el CLI ---------------------------------------------------------------------
def test_menu_flag_opens_the_menu(monkeypatch):
    monkeypatch.setattr(menu, "run_menu", lambda: 7)
    assert cli.main(["--menu"]) == 7


def test_no_arguments_without_a_terminal_is_still_an_error(monkeypatch):
    monkeypatch.setattr(cli, "_interactive", lambda: False)
    monkeypatch.setattr("sys.argv", ["udemy"])
    with pytest.raises(SystemExit):
        cli.main()


def test_no_arguments_in_a_terminal_opens_the_menu(monkeypatch):
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    monkeypatch.setattr(menu, "run_menu", lambda: 0)
    monkeypatch.setattr("sys.argv", ["udemy"])
    assert cli.main() == 0
