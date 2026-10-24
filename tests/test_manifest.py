import json

from udemy_transcripts.curriculum import Lecture, Section
from udemy_transcripts.manifest import MANIFEST_NAME, Manifest, caption_signature

LEC = Lecture(7, "Bienvenida", 1, "Video", [])
SEC = Section(1, "Intro")
CAP = {"locale_id": "es_LA", "file_name": "abc.vtt", "url": "https://cdn/x/abc.vtt?secure=1"}
ENTRY = {"file": "01 - Intro/001 - Bienvenida.md", "caption": caption_signature(CAP),
         "render": "md|v1", "title": "Bienvenida", "section": "Intro"}


def test_caption_signature_uses_file_name_and_ignores_the_signed_query():
    assert caption_signature(CAP) == "es_LA:abc.vtt"
    assert caption_signature({"locale_id": "en_US", "url": "https://cdn/e/z.vtt?secure=9"}) \
        == "en_US:https://cdn/e/z.vtt"


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / MANIFEST_NAME
    m = Manifest(path, 6737997)
    m.set(7, ENTRY)
    m.save()
    assert not (tmp_path / (MANIFEST_NAME + ".tmp")).exists()
    again = Manifest.load(path, "6737997")
    assert again.get(7) == ENTRY and again.get("7") == ENTRY
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_load_missing_returns_empty(tmp_path):
    assert Manifest.load(tmp_path / MANIFEST_NAME, 1).entries == {}


def test_load_corrupt_or_foreign_manifests_start_empty_and_warn(tmp_path):
    path, logs = tmp_path / MANIFEST_NAME, []
    path.write_text("{no es json", encoding="utf-8")
    assert Manifest.load(path, 1, log=logs.append).entries == {}
    path.write_text('["lista"]', encoding="utf-8")
    assert Manifest.load(path, 1, log=logs.append).entries == {}
    path.write_text(json.dumps({"course_id": 2, "lectures": {"7": ENTRY}}), encoding="utf-8")
    assert Manifest.load(path, 1, log=logs.append).entries == {}
    assert len(logs) == 3 and "curso 2" in logs[2]


def test_up_to_date_requires_everything_to_match(tmp_path):
    (tmp_path / "01 - Intro").mkdir()
    (tmp_path / ENTRY["file"]).write_text("x", encoding="utf-8")
    m = Manifest(tmp_path / MANIFEST_NAME, 1, {"7": dict(ENTRY)})

    def check(**over):
        lec = over.pop("lec", LEC)
        sec = over.pop("sec", SEC)
        cap = over.pop("cap", CAP)
        args = dict(rel=ENTRY["file"], render="md|v1")
        args.update(over)
        return m.up_to_date(lec, sec, cap, args["rel"], args["render"], tmp_path)

    assert check()
    assert not check(cap=dict(CAP, file_name="nuevo.vtt"))          # subtítulo cambiado
    assert not check(cap=dict(CAP, locale_id="en_US"))              # otro idioma
    assert not check(render="md|v2")                                # otras opciones
    assert not check(rel="01 - Intro/001 - Otro.md")                # lección renombrada
    assert not check(lec=Lecture(7, "Otro título", 1, "Video", []))
    assert not check(sec=Section(1, "Otra sección"))
    assert not check(lec=Lecture(99, "Bienvenida", 1, "Video", []))  # lección nueva
    (tmp_path / ENTRY["file"]).unlink()
    assert not check()                                              # archivo borrado


def test_lecture_without_id_is_never_up_to_date(tmp_path):
    m = Manifest(tmp_path / MANIFEST_NAME, 1, {"None": dict(ENTRY)})
    assert not m.up_to_date(Lecture(None, "Bienvenida", 1, "Video", []), SEC, CAP,
                            ENTRY["file"], "md|v1", tmp_path)
