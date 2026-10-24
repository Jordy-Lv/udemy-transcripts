import json
from types import SimpleNamespace

import pytest

from test_download import FILES, MD, TXT, run, sections
from test_resources import RES_FILES, ON
from udemy_transcripts import cli, study
from udemy_transcripts.ai import (MODELS, AnthropicBackend, FatalStudyError, Generation,
                                  StudyError, model_info)
from udemy_transcripts.errors import UdemyError
from udemy_transcripts.ranges import make_selector, parse_ranges
from udemy_transcripts.render.common import RenderOptions
from udemy_transcripts.study import (StudyLesson, StudyOptions, StudySection, card_rows,
                                     clean_lesson_text, collect_sections, estimate,
                                     flashcards_csv, load_manifest, study_course)

DIR_GENERAL = "00 - General"
DIR_INTRO = "01 - Introducción- ¿qué es-"


@pytest.fixture
def course(make_client, tmp_path):
    """Un curso ya descargado (vídeos, artículo y recursos) en tmp_path."""
    run(make_client, tmp_path, files=RES_FILES, res=ON)
    return tmp_path


class FakeBackend:
    def __init__(self, fail=None, fatal=False):
        self.calls, self.fail, self.fatal = [], fail, fatal

    def generate(self, system, user):
        self.calls.append((system, user))
        if self.fatal:
            raise FatalStudyError("credenciales")
        if self.fail and self.fail in user:
            raise StudyError("rechazo")
        return Generation(f"## Ideas clave\n\n- idea {len(self.calls)}",
                          [{"pregunta": f"¿Pregunta {len(self.calls)}?", "respuesta": "Respuesta.",
                            "etiquetas": ["Spring Boot", "jwt"]}], 1000, 500)


def opts(**kw):
    values = dict(mode="api", model="claude-opus-5-5", assume_yes=True)
    values.update(kw)
    return StudyOptions(**values)


# ---- texto de las lecciones --------------------------------------------------------
def test_clean_markdown_lesson(course):
    raw = (course / DIR_GENERAL / "001 - Bienvenida.md").read_text(encoding="utf-8")
    assert "seccion:" in raw and "## Recursos" in raw
    assert clean_lesson_text(raw) == "Hola. Adiós."


def test_clean_keeps_code_fences_and_unescapes_markdown():
    raw = ('---\ncurso: "C"\n---\n\n# Título\n\n> 01 - Sec · 02:00\n\n'
           '[00:05](https://x/y?start=5) Usa snake\\_case y \\<div\\>.\n\n'
           '```java\nString s = "a\\nb"; // \\_\n```\n\n## Recursos\n\n- [a.pdf](x)\n')
    text = clean_lesson_text(raw)
    assert text == ('Usa snake_case y <div>.\n\n```java\nString s = "a\\nb"; // \\_\n```')


def test_clean_plain_text_lesson():
    assert clean_lesson_text("[00:01] Hola.\nAdiós.\n\n[01:10:05] Fin.\n\nRECURSOS\n- a.pdf\n") == \
        "Hola.\nAdiós.\n\nFin."
    assert clean_lesson_text("") == ""


def test_clean_only_drops_the_metadata_quote_right_under_the_title():
    raw = "# T\n\n> meta\n\n> cita real del texto\n"
    assert clean_lesson_text(raw) == "> cita real del texto"


# ---- secciones ------------------------------------------------------------------------
def test_collect_sections_from_the_manifest(course):
    sections_ = collect_sections(course, load_manifest(course))
    assert [(s.index, s.dirname, s.title) for s in sections_] == [
        (0, DIR_GENERAL, "General"), (1, DIR_INTRO, "Introducción: ¿qué es?")]
    lessons = {s.dirname: [(le.number, le.title) for le in s.lessons] for s in sections_}
    assert lessons[DIR_GENERAL] == [("001", "Bienvenida")]
    assert lessons[DIR_INTRO] == [("002", "Instalación"), ("003", "Temas puntuales")]
    article = sections_[1].lessons[1]
    assert "**negrita**" in article.text and "Tema" in article.text


def test_collect_sections_honours_the_selector_and_missing_files(course):
    pick = make_selector(parse_ranges("1"), parse_ranges("3"))
    only = collect_sections(course, load_manifest(course), pick)
    assert [(s.dirname, [le.number for le in s.lessons]) for s in only] == [(DIR_INTRO, ["003"])]
    (course / DIR_GENERAL / "001 - Bienvenida.md").unlink()
    assert [s.dirname for s in collect_sections(course, load_manifest(course))] == [DIR_INTRO]


def test_load_manifest_requires_a_downloaded_course(tmp_path):
    with pytest.raises(UdemyError, match="no parece un curso descargado"):
        load_manifest(tmp_path)


def lesson(n, words):
    return StudyLesson(f"{n:03d}", f"L{n}", "palabra " * words, f"s/{n:03d} - L{n}.md")


def test_chunks_split_long_sections_but_never_a_lesson():
    section = StudySection(1, "01 - S", "S", [lesson(i, 300) for i in range(1, 7)])
    assert len(section.chunks()) == 1
    parts = section.chunks(max_tokens=1600)
    assert [len(p) for p in parts] == [2, 2, 2]
    huge = StudySection(1, "01 - S", "S", [lesson(1, 5000)])
    assert [len(p) for p in huge.chunks(max_tokens=100)] == [1]


# ---- prompts y salida ---------------------------------------------------------------
def test_card_range_scales_with_the_text():
    assert study.card_range(100) == (4, 9) and study.card_range(450 * 12) == (9, 15)
    assert study.card_range(10 ** 6) == (22, 28)


def test_user_prompt_and_chat_prompt():
    section = StudySection(2, "02 - Intro", "Intro", [lesson(5, 10), lesson(6, 10)])
    text = study.user_prompt(section, section.lessons)
    assert '<leccion numero="005" titulo="L5">' in text and "la sección «Intro» del curso" in text
    assert "entre 4 y 9 tarjetas" in text
    assert "(parte 2 de 3)" in study.user_prompt(section, section.lessons, 2, 3)
    chat = study.chat_prompt(section, section.lessons)
    assert chat.startswith("Eres un tutor técnico") and "```csv" in chat and "pregunta;respuesta;etiquetas" in chat
    assert text in chat


def test_titles_with_quotes_do_not_break_the_prompt_tags():
    sec = StudySection(1, "01 - S", "S", [StudyLesson("001", 'Qué es "esto"\nraro', "x", "a/b")])
    assert 'titulo="Qué es \'esto\' raro"' in study.lessons_block(sec.lessons)


def test_flashcards_csv_is_anki_ready():
    section = StudySection(3, "03 - S", "S")
    rows = card_rows([{"pregunta": "¿Qué es X; y por qué?", "respuesta": 'Dice "hola"\nen 2 líneas',
                       "etiquetas": ["Spring Boot", "JWT!", "", "seccion-03"]},
                      {"pregunta": "Q2", "respuesta": "A2", "etiquetas": []}], section)
    assert rows[0][2] == "spring-boot jwt seccion-03" and rows[1][2] == "seccion-03"
    text = flashcards_csv(rows)
    assert text.startswith("#separator:semicolon\n#html:false\n#tags column:3\n")
    body = text.split("#tags column:3\n", 1)[1]
    import csv
    import io
    parsed = list(csv.reader(io.StringIO(body), delimiter=";"))
    assert parsed[0] == ["¿Qué es X; y por qué?", 'Dice "hola"\nen 2 líneas', "spring-boot jwt seccion-03"]
    assert parsed[1] == ["Q2", "A2", "seccion-03"]


def test_estimate_and_money():
    sec = StudySection(1, "01 - S", "S", [lesson(1, 1000)])
    est = estimate([sec], "claude-opus-5-5")
    assert est.calls == 1 and est.output_tokens == 7000 and 2000 < est.input_tokens < 4000
    assert est.cost == pytest.approx((est.input_tokens * 4 + 7000 * 20) / 1e6)
    assert estimate([sec], "modelo-desconocido").cost is None
    assert study.money(0.004) == "< $0.01" and study.money(4.256) == "$4.26"


# ---- modo prompt ----------------------------------------------------------------------
def test_prompt_mode_writes_one_file_per_section_without_an_api(course):
    logs = []
    stats = study_course(course, "Mi curso", opts(mode="prompt"), log=logs.append)
    assert stats.prompts == 2
    files = sorted(p.name for p in (course / "prompts").iterdir())
    assert files == ["00 - General.md", f"{DIR_INTRO}.md", "LEEME.md"]
    text = (course / "prompts" / f"{DIR_INTRO}.md").read_text(encoding="utf-8")
    assert text.startswith("<!-- Mi curso · 01 - Introducción- ¿qué es- ·") and '<leccion numero="002"' in text
    assert "http" not in text.split("<leccion", 1)[1].split("</leccion>")[0]        # sin enlaces ni marcas
    assert any("2 prompt(s)" in line for line in logs)


def test_prompt_mode_splits_huge_sections(course, monkeypatch):
    monkeypatch.setattr(study, "CHUNK_TOKENS", 5)
    study_course(course, "Mi curso", opts(mode="prompt"), log=lambda *_: None)
    names = sorted(p.name for p in (course / "prompts").iterdir())
    assert f"{DIR_INTRO} - parte 1.md" in names and f"{DIR_INTRO} - parte 2.md" in names


# ---- modo api ---------------------------------------------------------------------------
def test_api_mode_writes_summaries_flashcards_and_a_cache(course):
    backend = FakeBackend()
    logs = []
    stats = study_course(course, "Mi curso", opts(), backend=backend, log=logs.append)
    assert (stats.generated, stats.cached, stats.failed) == (2, 0, 0) and len(backend.calls) == 2
    summary = (course / DIR_GENERAL / "RESUMEN.md").read_text(encoding="utf-8")
    assert summary.startswith("# Resumen — 00 - General\n\n> Generado con claude-opus-5-5 a partir de 1")
    assert "## Ideas clave" in summary
    cards = (course / DIR_GENERAL / "flashcards.csv").read_text(encoding="utf-8")
    assert "¿Pregunta 1?;Respuesta.;spring-boot jwt seccion-00" in cards
    everything = (course / "flashcards.csv").read_text(encoding="utf-8")
    assert everything.count("\n") == 3 + 2                         # cabecera Anki + 2 tarjetas
    assert (course / ".estudio" / f"{DIR_GENERAL}.json").is_file()
    assert (stats.input_tokens, stats.output_tokens) == (2000, 1000)
    assert any("Tokens usados: 2,000" in line for line in logs)
    assert not (course / "01 - Introducción- ¿qué es-" / "RESUMEN.md.tmp").exists()


def test_the_system_prompt_and_lessons_reach_the_model(course):
    backend = FakeBackend()
    study_course(course, "Mi curso", opts(), backend=backend, log=lambda *_: None)
    system, user = backend.calls[1]
    assert system.startswith("Eres un tutor técnico") and 'titulo="Instalación"' in user
    assert "**negrita**" in user                          # el artículo viaja como Markdown


def test_second_run_uses_the_cache_and_regenerate_ignores_it(course):
    study_course(course, "Mi curso", opts(), backend=FakeBackend(), log=lambda *_: None)
    backend = FakeBackend()
    logs = []
    stats = study_course(course, "Mi curso", opts(), backend=backend, log=logs.append)
    assert (stats.generated, stats.cached) == (0, 2) and backend.calls == []
    assert any("en caché" in line for line in logs) and not any("coste estimado" in l for l in logs)
    stats = study_course(course, "Mi curso", opts(regenerate=True), backend=backend, log=lambda *_: None)
    assert stats.generated == 2 and len(backend.calls) == 2


def test_cache_is_rewritten_into_files_that_were_deleted(course):
    study_course(course, "Mi curso", opts(), backend=FakeBackend(), log=lambda *_: None)
    (course / DIR_GENERAL / "RESUMEN.md").unlink()
    backend = FakeBackend()
    study_course(course, "Mi curso", opts(), backend=backend, log=lambda *_: None)
    assert backend.calls == [] and (course / DIR_GENERAL / "RESUMEN.md").is_file()


def test_cache_depends_on_text_model_and_prompt_version(course, monkeypatch):
    study_course(course, "Mi curso", opts(), backend=FakeBackend(), log=lambda *_: None)
    for change in ("text", "model", "version"):
        backend = FakeBackend()
        if change == "text":
            path = course / DIR_GENERAL / "001 - Bienvenida.md"
            path.write_text(path.read_text(encoding="utf-8").replace(
                "\n## Recursos", "\nUna frase nueva.\n\n## Recursos"), encoding="utf-8")
        elif change == "version":
            monkeypatch.setattr(study, "PROMPT_VERSION", 2)
        stats = study_course(course, "Mi curso", opts(model="claude-sonnet-5-5" if change == "model"
                                                      else "claude-opus-5-5"),
                             backend=backend, log=lambda *_: None)
        assert stats.generated >= 1, change


def test_long_sections_are_split_and_joined(course, monkeypatch):
    monkeypatch.setattr(study, "CHUNK_TOKENS", 5)
    backend = FakeBackend()
    study_course(course, "Mi curso", opts(), backend=backend, log=lambda *_: None)
    assert len(backend.calls) == 3                          # 1 + 2 trozos
    assert "(parte 2 de 2)" in backend.calls[2][1]
    text = (course / DIR_INTRO / "RESUMEN.md").read_text(encoding="utf-8")
    assert "### Parte 1" in text and "### Parte 2" in text


def test_a_failed_section_is_reported_and_the_rest_continues(course):
    logs = []
    stats = study_course(course, "Mi curso", opts(), backend=FakeBackend(fail="Bienvenida"),
                         log=logs.append)
    assert (stats.generated, stats.failed) == (1, 1)
    assert any("✗" in line and "rechazo" in line for line in logs)
    assert not (course / DIR_GENERAL / "RESUMEN.md").exists()
    # lo que falló no queda en caché: la próxima vez se reintenta solo eso
    backend = FakeBackend()
    stats = study_course(course, "Mi curso", opts(), backend=backend, log=lambda *_: None)
    assert (stats.generated, stats.cached, len(backend.calls)) == (1, 1, 1)


def test_fatal_errors_stop_everything(course):
    with pytest.raises(FatalStudyError):
        study_course(course, "Mi curso", opts(), backend=FakeBackend(fatal=True), log=lambda *_: None)


def test_selection_limits_the_sections(course):
    backend = FakeBackend()
    study_course(course, "Mi curso", opts(), backend=backend, log=lambda *_: None,
                 select=make_selector(parse_ranges("1"), []))
    assert len(backend.calls) == 1 and (course / DIR_INTRO / "RESUMEN.md").is_file()
    with pytest.raises(UdemyError, match="en ese rango"):
        study_course(course, "Mi curso", opts(), backend=backend, log=lambda *_: None,
                     select=make_selector(parse_ranges("9"), []))


def test_confirmation_shows_the_cost_and_can_cancel(course):
    logs, asked = [], []
    with pytest.raises(UdemyError, match="Cancelado"):
        study_course(course, "Mi curso", opts(assume_yes=False), backend=FakeBackend(),
                     log=logs.append, input_fn=lambda p: asked.append(p) or "n")
    text = "\n".join(logs)
    assert "2 llamada(s) a claude-opus-5-5" in text and "coste estimado ≈ $" in text
    assert "API de Anthropic" in text and asked == ["  ¿Continuar? [s/N] "]
    backend = FakeBackend()
    study_course(course, "Mi curso", opts(assume_yes=False), backend=backend, log=lambda *_: None,
                 input_fn=lambda *_: "sí")
    assert len(backend.calls) == 2


def test_no_terminal_means_no_silent_upload(course):
    def eof(*_):
        raise EOFError
    with pytest.raises(UdemyError, match="--yes"):
        study_course(course, "Mi curso", opts(assume_yes=False), backend=FakeBackend(),
                     log=lambda *_: None, input_fn=eof)


def test_unknown_model_has_no_price_but_still_runs(course):
    logs = []
    study_course(course, "Mi curso", opts(model="otro-modelo"), backend=FakeBackend(), log=logs.append)
    assert any("no tengo el precio" in line for line in logs)


# ---- backend de Anthropic con un cliente simulado ---------------------------------------
class FakeAnthropic:
    def __init__(self, text=None, stop="end_turn", error=None, beta_type_error=False):
        self.text, self.stop, self.error, self.beta_type_error = text, stop, error, beta_type_error
        self.calls = []
        self.messages = SimpleNamespace(create=lambda **kw: self._create("plain", kw))
        self.beta = SimpleNamespace(messages=SimpleNamespace(
            create=lambda **kw: self._create("beta", kw)))

    def _create(self, kind, kwargs):
        if kind == "beta" and self.beta_type_error:
            raise TypeError("unexpected keyword argument 'fallbacks'")
        self.calls.append((kind, kwargs))
        if self.error:
            raise self.error
        text = self.text if self.text is not None else json.dumps({
            "resumen": "## Ideas clave\n- a", "flashcards": [
                {"pregunta": "¿P?", "respuesta": "R", "etiquetas": ["x"]},
                {"pregunta": " ", "respuesta": "vacía", "etiquetas": []}]})
        return SimpleNamespace(content=[SimpleNamespace(type="thinking"),
                                        SimpleNamespace(type="text", text=text)],
                               stop_reason=self.stop, stop_details=None, model="claude-opus-5-5",
                               usage=SimpleNamespace(input_tokens=1200, output_tokens=800))


def test_backend_request_uses_structured_output_and_server_fallback():
    client = FakeAnthropic()
    gen = AnthropicBackend("claude-opus-5-5", client=client, log=lambda *_: None).generate("SYS", "USER")
    kind, kwargs = client.calls[0]
    assert kind == "beta" and kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert kwargs["fallbacks"] == "default" and kwargs["model"] == "claude-opus-5-5"
    assert kwargs["system"] == "SYS" and kwargs["messages"] == [{"role": "user", "content": "USER"}]
    assert kwargs["output_config"]["effort"] == "low"
    schema = kwargs["output_config"]["format"]
    assert schema["type"] == "json_schema" and schema["schema"]["required"] == ["resumen", "flashcards"]
    assert kwargs["max_tokens"] == 16000 and "temperature" not in kwargs and "thinking" not in kwargs
    assert (gen.resumen, len(gen.flashcards), gen.input_tokens, gen.output_tokens) == \
        ("## Ideas clave\n- a", 1, 1200, 800)                  # la tarjeta vacía se descarta


def test_backend_without_fallback_support_uses_the_plain_endpoint():
    client = FakeAnthropic()
    AnthropicBackend("claude-haiku-5-5", client=client, log=lambda *_: None).generate("S", "U")
    kind, kwargs = client.calls[0]
    assert kind == "plain" and "betas" not in kwargs and kwargs["output_config"]["effort"] == "low"
    client = FakeAnthropic()
    AnthropicBackend("claude-haiku-4-5", client=client, log=lambda *_: None).generate("S", "U")
    assert "effort" not in client.calls[0][1]["output_config"]       # ese modelo no lo admite
    client = FakeAnthropic()
    AnthropicBackend("modelo-nuevo", client=client, log=lambda *_: None).generate("S", "U")
    assert client.calls[0][0] == "plain"


def test_backend_falls_back_to_the_plain_endpoint_when_the_sdk_is_old():
    client = FakeAnthropic(beta_type_error=True)
    backend = AnthropicBackend("claude-opus-5-5", client=client, log=lambda *_: None)
    backend.generate("S", "U")
    backend.generate("S", "U")
    assert [kind for kind, _ in client.calls] == ["plain", "plain"]


def test_backend_announces_the_fallback():
    logs = []
    AnthropicBackend("claude-opus-5-5", client=FakeAnthropic(), log=logs.append)
    assert any("Fallback del servidor" in line for line in logs)
    logs.clear()
    AnthropicBackend("claude-haiku-5-5", client=FakeAnthropic(), log=logs.append)
    assert logs == []


@pytest.mark.parametrize("kwargs, error, match", [
    (dict(stop="refusal"), StudyError, "rechazó"),
    (dict(stop="max_tokens"), StudyError, "se cortó"),
    (dict(text="no es json"), StudyError, "JSON"),
    (dict(text='{"flashcards": []}'), StudyError, "resumen"),
])
def test_backend_response_problems_are_section_errors(kwargs, error, match):
    backend = AnthropicBackend("claude-opus-5-5", client=FakeAnthropic(**kwargs), log=lambda *_: None)
    with pytest.raises(error, match=match):
        backend.generate("S", "U")


@pytest.mark.parametrize("name, fatal", [
    ("AuthenticationError", True), ("PermissionDeniedError", True), ("BadRequestError", True),
    ("NotFoundError", True), ("RateLimitError", False), ("InternalServerError", False),
    ("APIConnectionError", False)])
def test_backend_error_classification(name, fatal):
    exc = type(name, (Exception,), {})("detalle")
    backend = AnthropicBackend("claude-opus-5-5", client=FakeAnthropic(error=exc), log=lambda *_: None)
    with pytest.raises(FatalStudyError if fatal else StudyError) as info:
        backend.generate("S", "U")
    assert isinstance(info.value, FatalStudyError) == fatal and "detalle" in str(info.value)


def test_missing_credentials_are_explained():
    exc = TypeError('"Could not resolve authentication method. Expected api_key to be set."')
    backend = AnthropicBackend("claude-haiku-5-5", client=FakeAnthropic(error=exc), log=lambda *_: None)
    with pytest.raises(FatalStudyError, match="ANTHROPIC_API_KEY"):
        backend.generate("S", "U")


def test_missing_sdk_is_explained(monkeypatch):
    import builtins
    real = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "anthropic":
            raise ImportError("no hay")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(UdemyError, match=r"udemy-transcripts\[ai\]"):
        AnthropicBackend("claude-opus-5-5", log=lambda *_: None)


def test_model_table_is_consistent():
    assert model_info("claude-opus-5-5")[:2] == (4.00, 20.00) and model_info("nope") is None
    assert all(len(v) == 4 and v[0] < v[1] for v in MODELS.values())


# ---- CLI --------------------------------------------------------------------------------------
def parse(*argv):
    return cli.build_parser().parse_args(list(argv))


def test_cli_study_flags_and_validation():
    args = parse("--study", "api", "--ai-model", "claude-sonnet-5-5", "--regenerate", "--yes", "x")
    options = cli.study_options(args)
    assert (options.mode, options.model, options.regenerate, options.assume_yes) == \
        ("api", "claude-sonnet-5-5", True, True)
    assert cli.study_options(parse("x")) is None
    assert parse("--study", "prompt", "x").ai_model == "claude-opus-5-5"
    with pytest.raises(UdemyError, match="--single"):
        cli.study_options(parse("--study", "api", "--single", "x"))
    with pytest.raises(UdemyError, match="--single"):
        cli.study_options(parse("--study", "api", "--txt", "x"))
    with pytest.raises(UdemyError, match="--study-from necesita"):
        cli.study_options(parse("--study-from", "carpeta"))
    with pytest.raises(SystemExit):
        parse("--study", "otro", "x")


def test_study_from_runs_without_a_browser(course, capsys):
    assert cli.main(["--study", "prompt", "--study-from", str(course)]) == 0
    assert (course / "prompts" / "LEEME.md").is_file()
    assert "2 prompt(s)" in capsys.readouterr().out


def test_study_from_respects_ranges_and_reports_errors(course, tmp_path_factory, capsys):
    assert cli.main(["--study", "prompt", "--study-from", str(course), "--sections", "1"]) == 0
    assert sorted(p.name for p in (course / "prompts").iterdir()) == [f"{DIR_INTRO}.md", "LEEME.md"]
    empty = tmp_path_factory.mktemp("vacio")
    assert cli.main(["--study", "prompt", "--study-from", str(empty)]) == 1
    assert "no parece un curso descargado" in capsys.readouterr().err


def test_study_runs_after_the_download(make_client, tmp_path, monkeypatch):
    from test_cli import course_page, job
    from conftest import FakeContext
    seen = []
    monkeypatch.setattr(cli, "study_course",
                        lambda course_dir, title, options, **kw: seen.append((course_dir, title, options)))
    ctx = FakeContext(dict(FILES))
    cli.download_one(make_client(course_page(), ctx), 123, job(study=opts(mode="prompt")), tmp_path,
                     log=lambda *_: None)
    assert seen == [(tmp_path / "Mi curso", "Mi curso", opts(mode="prompt"))]
    seen.clear()
    cli.download_one(make_client(course_page(), FakeContext()), 123,
                     job(study=opts(mode="prompt"), select=lambda s, lec: lec.index == 1),
                     tmp_path / "otro", log=lambda *_: None)      # su subtítulo da 404
    assert seen == []                                   # nada descargado → nada que estudiar
