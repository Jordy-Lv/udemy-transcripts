from conftest import js, load_json
from udemy_transcripts.curriculum import fetch_curriculum, parse_curriculum


def test_parse_groups_lectures_by_section_and_skips_quizzes():
    sections = parse_curriculum(load_json("curriculum.json")["results"])
    assert [(s.index, s.title) for s in sections] == \
        [(0, "General"), (1, "Introducción: ¿qué es?"), (2, "Avanzado")]
    assert [[lec.id for lec in s.lectures] for s in sections] == [[900], [901, 902], [903]]


def test_section_dirname_is_filesystem_safe():
    sections = parse_curriculum(load_json("curriculum.json")["results"])
    assert sections[0].dirname == "00 - General"
    assert sections[1].dirname == "01 - Introducción- ¿qué es-"


def test_lecture_fields():
    lecs = [lec for s in parse_curriculum(load_json("curriculum.json")["results"])
            for lec in s.lectures]
    video, article, untitled = lecs[1], lecs[2], lecs[3]
    assert video.is_video and video.number == "002" and video.duration == 366
    assert video.captions[0]["locale_id"] == "en_US"
    assert not article.is_video
    assert untitled.title == "leccion-004"      # sin título


def test_missing_index_numbers_as_000():
    (section,) = parse_curriculum([{"_class": "lecture", "title": "x", "asset": None}])
    assert section.lectures[0].number == "000" and not section.lectures[0].is_video


def test_fetch_follows_pagination(make_client):
    from conftest import FakePage
    data = load_json("curriculum.json")
    page1 = dict(data, next="https://www.udemy.com/api-2.0/page2", results=data["results"][:2])
    page2 = dict(data, next=None, results=data["results"][2:])
    page = FakePage([js(200, page1), js(200, page2)])
    sections = fetch_curriculum(make_client(page), 123)
    assert sum(len(s.lectures) for s in sections) == 4
    assert page.calls[0].startswith("https://www.udemy.com/api-2.0/courses/123/subscriber-curriculum-items/")
    assert page.calls[1] == "https://www.udemy.com/api-2.0/page2"
