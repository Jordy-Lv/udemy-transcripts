import pytest

from conftest import FakeContext, load_json
from test_download import (ARTICLE, COURSE, FILES, INTRO, MD, TXT, VIDEO1, read, run, sections)
from udemy_transcripts import resources as R
from udemy_transcripts.curriculum import Resource, parse_curriculum, parse_resource
from udemy_transcripts.errors import UdemyError
from udemy_transcripts.manifest import MANIFEST_NAME, Manifest
from udemy_transcripts.resources import ResourceOptions
from udemy_transcripts.util import fs_path

PDF_URL = "https://att.example/5001/original.pdf?sig=1"
CSV_URL = "https://att.example/5003/original.csv?sig=2"
IMG_URL = "https://img.example/a.png"
PDF_REL = f"recursos/{INTRO}/001 - Bienvenida/Guia.pdf"
CSV_REL = "recursos/01 - Introducción- ¿qué es-/003 - Temas puntuales/datos.csv"
IMG_REL = "recursos/01 - Introducción- ¿qué es-/003 - Temas puntuales/img/a.png"
RES_FILES = dict(FILES, **{PDF_URL: (200, b"%PDF-1.4 fake"), CSV_URL: (200, b"a,b\n1,2\n"),
                           IMG_URL: (200, b"\x89PNG fake")})
ON = ResourceOptions(enabled=True, assume_yes=True)


def res(**kw):
    base = dict(id=1, kind="file", title="T", filename="doc.pdf", url="https://x/original.pdf")
    base.update(kw)
    return Resource(**base)


# ---- utilidades -----------------------------------------------------------
def test_parse_size_and_format_size():
    assert R.parse_size("200MB") == 200 * 1024 ** 2
    assert R.parse_size("1.5g") == int(1.5 * 1024 ** 3) and R.parse_size("1,5 GB") == int(1.5 * 1024 ** 3)
    assert R.parse_size("4096") == 4096 and R.parse_size("10 kb") == 10240
    for bad in ("", "mucho", "10XB", "-5MB"):
        with pytest.raises(UdemyError, match="--max-size"):
            R.parse_size(bad)
    assert R.format_size(512) == "512 B" and R.format_size(1536) == "1.5 KB"
    assert R.format_size(5 * 1024 ** 3) == "5.0 GB"


def test_parse_types():
    assert R.parse_types("pdf, .ZIP,") == {"pdf", "zip"}
    assert R.parse_types("") is None and R.parse_types(None) is None


def test_extension():
    assert R.extension("a/b/Guia.PDF") == "pdf" and R.extension("sin") == ""
    assert R.extension("raro.demasiado_largo_ext") == ""
    assert R.url_extension("https://att/x/original.tar?sig=1") == "tar"


def test_filenames_keep_the_extension_even_when_truncated():
    long = "n" * 300 + ".pdf"
    out = R.safe_filename(long)
    assert out.endswith(".pdf") and len(out) <= 120
    assert R.safe_filename('a/b:c*d.txt') == "a-b-c-d.txt"
    assert R.safe_filename("") == "archivo" and R.safe_filename("...") == "archivo"


def test_resource_filename_uses_the_cdn_extension_when_missing():
    assert R.resource_filename(res(filename="Guia.pdf")) == "Guia.pdf"
    assert R.resource_filename(res(filename="datos", url="https://c/original.csv?x=1")) == "datos.csv"
    assert R.resource_filename(res(filename="", title="Manual", url="https://c/original.pdf")) \
        == "Manual.pdf"
    assert R.resource_filename(res(filename="x.condicional_case", url="https://c/original.condicional_case")) == "x.condicional_case"
    assert R.resource_filename(res(filename="raw", url="https://c/original")) == "raw"


def test_unique_names_and_lecture_paths():
    assert R.unique_names(["a.pdf", "b.pdf", "A.pdf", "a.pdf"]) == \
        ["a.pdf", "b.pdf", "A (2).pdf", "a (3).pdf"]
    secs = sections()
    lec = secs[0].lectures[0]
    lec.resources = [res(id=1, filename="a.pdf"), res(id=2, filename="a.pdf"),
                     res(id=3, kind="link", url="https://x")]
    paths = R.lecture_file_paths(secs[0], lec)
    assert sorted(paths.values()) == [f"recursos/{INTRO}/001 - Bienvenida/a (2).pdf",
                                      f"recursos/{INTRO}/001 - Bienvenida/a.pdf"]


# ---- modelo ---------------------------------------------------------------
def test_curriculum_parses_articles_and_resources():
    secs = parse_curriculum(load_json("curriculum.json")["results"])
    video, article = secs[0].lectures[0], secs[1].lectures[1]
    assert article.is_article and "<strong>negrita</strong>" in article.body
    assert [(r.kind, r.title, r.filename) for r in video.resources] == \
        [("file", "Guía del curso", "Guia.pdf"), ("link", "Documentación", "")]
    assert video.resources[0].url == "https://att.example/5001/original.pdf?sig=1"
    assert video.resources[1].url == "https://docs.example/inicio"


def test_parse_resource_edge_cases():
    assert parse_resource(None) is None and parse_resource({"asset_type": "File"}) is None
    assert parse_resource({"asset_type": "ExternalLink", "external_url": ""}) is None
    quality = {"asset_type": "Video", "id": 9, "filename": "clip.mp4", "download_urls": {
        "Video": [{"file": "https://c/360.mp4", "label": "360"},
                  {"file": "https://c/720.mp4", "label": "720"}]}}
    assert parse_resource(quality).url == "https://c/720.mp4"
    link = parse_resource({"asset_type": "ExternalLink", "id": 2, "external_url": "https://a.dev"})
    assert (link.kind, link.title) == ("link", "https://a.dev")


# ---- tamaños y plan ---------------------------------------------------------
def test_probe_size_reads_the_content_range(make_client):
    ctx = FakeContext({"https://x/a": (200, b"0123456789"), "https://x/err": (403, "")})
    client = make_client(context=ctx)
    assert R.probe_size(client, "https://x/a") == 10
    assert ctx.calls[0][1] == {"Range": "bytes=0-0"}
    assert R.probe_size(client, "https://x/err") is None


def test_probe_size_when_the_server_ignores_range(make_client):
    class NoRange(FakeContext):
        def get(self, url, headers=None, timeout=None):
            return super().get(url, None, timeout)           # responde 200 con todo
    assert R.probe_size(make_client(context=NoRange({"https://x/a": (200, b"12345")})),
                        "https://x/a") == 5


def plan_for(make_client, tmp_path, files=None, **kw):
    secs = sections()
    selected = [(s, lec) for s in secs for lec in s.lectures if lec.resources]
    client = make_client(context=FakeContext(dict(files or RES_FILES)))
    manifest = Manifest(tmp_path / MANIFEST_NAME, 123)
    return R.plan_resources(client, selected, manifest, tmp_path, **kw), manifest


def test_plan_sizes_and_statuses(make_client, tmp_path):
    plan, manifest = plan_for(make_client, tmp_path)
    assert [(p.rel, p.size, p.status) for p in plan.items] == \
        [(PDF_REL, 13, "new"), (CSV_REL, 8, "new")]
    assert plan.total_bytes == 21 and plan.unknown_size == 0
    # un archivo completo ya descargado se reconoce por la ruta y el tamaño
    R.write_file(tmp_path, PDF_REL, b"%PDF-1.4 fake")
    manifest.set_resource(5001, {"file": PDF_REL, "size": 13})
    plan, _ = plan_for(make_client, tmp_path)
    assert [p.status for p in plan.items] == ["new", "new"]          # otro manifest, sin apunte
    secs = sections()
    client = make_client(context=FakeContext(dict(RES_FILES)))
    plan = R.plan_resources(client, [(secs[0], secs[0].lectures[0])], manifest, tmp_path)
    assert plan.items[0].status == "done" and plan.items[0].size is None     # sin pedir tamaño


def test_plan_filters_by_type_and_size(make_client, tmp_path):
    plan, _ = plan_for(make_client, tmp_path, types={"csv"})
    assert [(p.status) for p in plan.items] == ["type", "new"]
    plan, _ = plan_for(make_client, tmp_path, max_size=10)
    assert [(p.status) for p in plan.items] == ["big", "new"]


def test_plan_with_unknown_sizes_and_summary(make_client, tmp_path):
    plan, _ = plan_for(make_client, tmp_path, files={PDF_URL: (403, ""), CSV_URL: (200, b"abc")})
    assert [p.size for p in plan.items] == [None, 3] and plan.unknown_size == 1
    lines = R.summarize(plan)
    assert lines == ["  Recursos: 2 archivo(s) por descargar (3 B + 1 de tamaño desconocido)"]


def test_summary_warns_about_executables(make_client, tmp_path):
    secs = sections()
    secs[0].lectures[0].resources = [res(id=7, filename="setup.exe", url="https://x/original.exe")]
    client = make_client(context=FakeContext({"https://x/original.exe": (200, b"MZ")}))
    plan = R.plan_resources(client, [(secs[0], secs[0].lectures[0])],
                            Manifest(tmp_path / MANIFEST_NAME, 1), tmp_path)
    text = "\n".join(R.summarize(plan))
    assert "ejecutable" in text and ".exe" in text and "nunca se ejecutan" in text


def test_confirm_only_asks_when_the_total_is_big():
    plan = R.Plan([R.Planned(None, None, None, "a.zip", 600 * 1024 ** 2)])
    asked = []
    assert R.confirm(R.Plan([R.Planned(None, None, None, "a", 10)]),
                     input_fn=lambda *_: pytest.fail("no debía preguntar"))
    assert R.confirm(plan, assume_yes=True, input_fn=lambda *_: pytest.fail("--yes"))
    assert R.confirm(plan, input_fn=lambda p: asked.append(p) or "s") and "600.0 MB" in asked[0]
    assert not R.confirm(plan, input_fn=lambda *_: "n")
    assert not R.confirm(plan, input_fn=lambda *_: "")

    def eof(*_):
        raise EOFError
    with pytest.raises(UdemyError, match="--yes"):
        R.confirm(plan, input_fn=eof)


# ---- descarga integrada -----------------------------------------------------
def test_resources_are_downloaded_and_linked(make_client, tmp_path):
    logs = []
    stats, ctx = run(make_client, tmp_path, files=RES_FILES, res=ON, logs=logs)
    assert (stats.files, stats.files_failed, stats.saved) == (2, 0, 3)
    assert (tmp_path / PDF_REL).read_bytes() == b"%PDF-1.4 fake"
    assert fs_path(tmp_path / CSV_REL).read_bytes() == b"a,b\n1,2\n"
    assert not list(tmp_path.rglob("*.part"))                       # sin restos a medias
    text = read(tmp_path, VIDEO1)
    assert "- [Guia.pdf](../recursos/00%20-%20General/001%20-%20Bienvenida/Guia.pdf)" in text
    assert "- [Documentación](https://docs.example/inicio)" in text
    manifest = Manifest.load(tmp_path / MANIFEST_NAME, 123)
    assert manifest.resources["5001"]["size"] == 13 and manifest.resources["5001"]["file"] == PDF_REL
    assert any("✓" in line and "Guia.pdf" in line for line in logs)


def test_article_images_are_downloaded_and_rewritten(make_client, tmp_path):
    run(make_client, tmp_path, files=RES_FILES, res=ON)
    assert fs_path(tmp_path / IMG_REL).read_bytes() == b"\x89PNG fake"
    text = read(tmp_path, ARTICLE)
    assert "![esquema](../recursos/01%20-%20Introducci%C3%B3n-%20%C2%BFqu%C3%A9%20es-/" \
           "003%20-%20Temas%20puntuales/img/a.png)" in text
    assert "https://img.example/a.png" not in text


def test_failed_images_keep_the_original_link(make_client, tmp_path):
    files = {k: v for k, v in RES_FILES.items() if k != IMG_URL}
    logs = []
    run(make_client, tmp_path, files=files, res=ON, logs=logs)
    assert "![esquema](https://img.example/a.png)" in read(tmp_path, ARTICLE)
    assert any("imagen a.png" in line for line in logs)


def test_links_file_lists_external_links(make_client, tmp_path):
    run(make_client, tmp_path, files=RES_FILES, res=ON)
    text = read(tmp_path, "recursos/enlaces.md")
    assert text.startswith("# Enlaces de Mi curso") and "## 00 - General" in text
    assert "### 001 - Bienvenida\n\n- [Documentación](https://docs.example/inicio)" in text


def test_index_points_to_the_resources_folder(make_client, tmp_path):
    run(make_client, tmp_path, files=RES_FILES, res=ON)
    assert "[enlaces externos](recursos/enlaces.md)" in read(tmp_path, "README.md")


def test_second_run_does_not_download_files_again(make_client, tmp_path):
    run(make_client, tmp_path, files=RES_FILES, res=ON)
    stats, ctx = run(make_client, tmp_path, files=RES_FILES, res=ON)
    assert (stats.files, stats.files_done) == (0, 2)
    assert PDF_URL not in ctx.requested and CSV_URL not in ctx.requested
    assert not any(h for url, h in ctx.calls if url in (PDF_URL, CSV_URL))   # ni siquiera sondeo


def test_a_changed_file_size_is_downloaded_again(make_client, tmp_path):
    run(make_client, tmp_path, files=RES_FILES, res=ON)
    (tmp_path / PDF_REL).write_bytes(b"truncado")                           # copia corrupta
    stats, _ = run(make_client, tmp_path, files=RES_FILES, res=ON)
    assert (stats.files, stats.files_done) == (1, 1)
    assert (tmp_path / PDF_REL).read_bytes() == b"%PDF-1.4 fake"


def test_update_adds_resource_links_to_lessons_written_without_them(make_client, tmp_path):
    run(make_client, tmp_path, files=RES_FILES)
    assert "sin descargar" in read(tmp_path, VIDEO1)
    stats, _ = run(make_client, tmp_path, files=RES_FILES, res=ON, update=True)
    assert stats.saved >= 2 and stats.files == 2                           # se reescribieron
    assert "sin descargar" not in read(tmp_path, VIDEO1)
    again, ctx = run(make_client, tmp_path, files=RES_FILES, res=ON, update=True)
    assert (again.saved, again.up_to_date) == (0, 3) and ctx.requested == []


def test_lessons_link_files_already_on_disk_even_without_the_flag(make_client, tmp_path):
    run(make_client, tmp_path, files=RES_FILES, res=ON)
    run(make_client, tmp_path, files=RES_FILES)                           # sin --resources
    assert "[Guia.pdf](../recursos" in read(tmp_path, VIDEO1)


def test_type_filter_and_size_limit(make_client, tmp_path):
    stats, _ = run(make_client, tmp_path, files=RES_FILES,
                   res=ResourceOptions(enabled=True, assume_yes=True, types={"csv"}))
    assert stats.files == 1 and not (tmp_path / PDF_REL).exists()
    assert (tmp_path / CSV_REL).exists()
    stats, _ = run(make_client, tmp_path / "otro", files=RES_FILES,
                   res=ResourceOptions(enabled=True, assume_yes=True, max_size=10))
    assert stats.files == 1 and not (tmp_path / "otro" / PDF_REL).exists()


def test_declining_the_confirmation_skips_resources_but_keeps_lessons(make_client, tmp_path):
    big = dict(RES_FILES, **{PDF_URL: (200, b"x", {"Content-Range": f"bytes 0-0/{900 * 1024 ** 2}"})})
    logs = []
    stats, ctx = run(make_client, tmp_path, files=big, logs=logs,
                     res=ResourceOptions(enabled=True, max_size=None), input_fn=lambda *_: "n")
    assert (stats.files, stats.saved) == (0, 3)
    assert not (tmp_path / "recursos").exists()
    assert any("Recursos omitidos" in line for line in logs)


def test_failed_resource_download_is_counted(make_client, tmp_path):
    files = dict(RES_FILES)
    del files[PDF_URL]                                                  # 404 al descargar
    logs = []
    stats, _ = run(make_client, tmp_path, files=dict(files, **{PDF_URL: (200, b"%PDF")}),
                   res=ON, logs=logs)
    assert stats.files == 2
    class Broken(FakeContext):
        def get(self, url, headers=None, timeout=None):
            if url == PDF_URL and not headers:
                return super().get("https://nada", headers, timeout)
            return super().get(url, headers, timeout)
    stats, _ = run(make_client, tmp_path / "x", context=Broken(dict(RES_FILES)), res=ON, logs=logs)
    assert (stats.files, stats.files_failed) == (1, 1)
    assert any("Guia.pdf: HTTP 404" in line for line in logs)
    assert "[Guia.pdf](" not in read(tmp_path / "x", VIDEO1)           # no se enlaza lo que falló


def test_resources_only_writes_no_lessons(make_client, tmp_path):
    stats, ctx = run(make_client, tmp_path, files=RES_FILES,
                     res=ResourceOptions(enabled=True, only=True, assume_yes=True))
    assert (stats.files, stats.saved) == (2, 0)
    assert (tmp_path / PDF_REL).exists() and (tmp_path / "recursos" / "enlaces.md").exists()
    assert not (tmp_path / "README.md").exists() and not (tmp_path / VIDEO1).exists()
    assert "https://cdn.example/900.vtt" not in ctx.requested          # ni un subtítulo


def test_single_mode_links_files_relative_to_the_single_file(make_client, tmp_path):
    course_dir = tmp_path / "Mi curso"
    manifest = Manifest(course_dir / MANIFEST_NAME, 123)
    course_dir.mkdir()
    stats, _ = run(make_client, course_dir, files=RES_FILES, res=ON, single=True,
                   manifest=manifest)
    assert stats.files == 2 and len(stats.items) == 3
    assert "(Mi%20curso/recursos/00%20-%20General/001%20-%20Bienvenida/Guia.pdf)" in stats.items[0][2]
    assert (course_dir / PDF_REL).exists() and not (course_dir / "README.md").exists()


def test_txt_lessons_list_local_paths(make_client, tmp_path):
    run(make_client, tmp_path, files=RES_FILES, res=ON, opts=TXT)
    assert f"RECURSOS\n- {PDF_REL}\n- Documentación: https://docs.example/inicio" in \
        read(tmp_path, VIDEO1.replace(".md", ".txt"))
    assert "[imagen: esquema]" in read(tmp_path, ARTICLE.replace(".md", ".txt"))


def test_same_name_files_in_one_lesson_get_numbered(make_client, tmp_path):
    secs = sections()
    secs[0].lectures[0].resources = [
        res(id=11, filename="a.pdf", url="https://x/1.pdf"), res(id=12, filename="a.pdf", url="https://x/2.pdf")]
    files = dict(RES_FILES, **{"https://x/1.pdf": (200, b"uno"), "https://x/2.pdf": (200, b"dos")})
    run(make_client, tmp_path, files=files, secs=secs, res=ON)
    base = tmp_path / "recursos" / INTRO / "001 - Bienvenida"
    assert (base / "a.pdf").read_bytes() == b"uno" and (base / "a (2).pdf").read_bytes() == b"dos"


def test_executables_are_saved_with_a_warning_and_never_run(make_client, tmp_path):
    secs = sections()
    secs[0].lectures[0].resources = [res(id=21, filename="setup.exe", url="https://x/s.exe")]
    logs = []
    run(make_client, tmp_path, files=dict(RES_FILES, **{"https://x/s.exe": (200, b"MZ")}),
        secs=secs, res=ON, logs=logs)
    assert (tmp_path / "recursos" / INTRO / "001 - Bienvenida" / "setup.exe").exists()
    assert any("ejecutable" in line for line in logs)
