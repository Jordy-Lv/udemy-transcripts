import pytest

from conftest import FakePage, js
from udemy_transcripts.courses import (CourseRef, course_title, extract_course_id_candidates,
                                       parse_course_ref, resolve_course_id, url_matches_slug)
from udemy_transcripts.errors import AccessDeniedError, NotLoggedInError, UdemyError


def test_parse_course_ref():
    assert parse_course_ref("12345") == CourseRef("12345", None)
    assert parse_course_ref("https://www.udemy.com/course/mi-curso/") == CourseRef(None, "mi-curso")
    assert parse_course_ref(
        "https://seti.udemy.com/course/java-spring/learn/lecture/51621647?start=255#overview"
    ) == CourseRef(None, "java-spring")
    assert parse_course_ref("  mi-curso ") == CourseRef(None, "mi-curso")
    assert parse_course_ref("/course/mi-curso/?x=1") == CourseRef(None, "mi-curso")


def test_url_matches_slug_is_exact():
    assert url_matches_slug("/course/mi-curso/learn/", "mi-curso")
    assert url_matches_slug("/course/mi-curso", "mi-curso")
    assert not url_matches_slug("/course/mi-curso-avanzado/learn/", "mi-curso")
    assert not url_matches_slug(None, "mi-curso")


def test_candidates_prioritize_clp_attribute_and_dedupe():     # B6
    html = ('<a href="/course/999/">otro</a> <div data-clp-course-id="123"></div> '
            '{"courseId": 123} courseId: 456 /course/999/')
    assert extract_course_id_candidates(html) == ["123", "456", "999"]
    assert extract_course_id_candidates("nada") == []


def handler(routes):
    def handle(url):
        for fragment, response in routes.items():
            if fragment in url:
                return response
        return js(404)
    return handle


def test_resolve_numeric_id_needs_no_requests(make_client):
    page = FakePage()
    assert resolve_course_id(make_client(page), "777") == "777"
    assert page.calls == []


def test_resolve_via_subscribed_courses(make_client):
    page = FakePage([js(200, {"results": [
        {"id": 1, "url": "/course/otro/learn/"}, {"id": 42, "url": "/course/mi-curso/learn/"}],
        "next": None})])
    assert resolve_course_id(make_client(page), "https://www.udemy.com/course/mi-curso/") == "42"


def test_resolve_falls_back_to_landing_and_validates_candidates(make_client):     # B6
    html = '<a href="/course/999/">sugerido</a><div data-clp-course-id="123"></div>'
    page = FakePage(html=html, handler=handler({
        "subscribed-courses": js(200, {"results": [], "next": None}),
        "courses/123/": js(200, {"url": "/course/mi-curso/"}),
        "courses/999/": js(200, {"url": "/course/otro/"}),
    }))
    assert resolve_course_id(make_client(page), "mi-curso") == "123"
    assert page.visited == ["https://www.udemy.com/course/mi-curso/"]


def test_resolve_rejects_unvalidated_candidates(make_client):     # B6
    page = FakePage(html='data-clp-course-id="999"', handler=handler({
        "subscribed-courses": js(200, {"results": [], "next": None}),
        "courses/999/": js(200, {"url": "/course/otro/"}),
    }))
    with pytest.raises(UdemyError, match="udemy --list"):
        resolve_course_id(make_client(page), "mi-curso")


def test_resolve_falls_back_when_subscribed_courses_is_unavailable(make_client):
    page = FakePage(html='data-clp-course-id="5"', handler=handler({
        "subscribed-courses": js(404),
        "courses/5/": js(200, {"url": "/course/mi-curso/"}),
    }))
    assert resolve_course_id(make_client(page), "mi-curso") == "5"


def test_resolve_propagates_login_errors(make_client):
    page = FakePage([js(401)])
    with pytest.raises(NotLoggedInError):
        resolve_course_id(make_client(page), "mi-curso")


def test_course_title(make_client):
    assert course_title(make_client(FakePage([js(200, {"title": "Java"})])), 1) == "Java"
    assert course_title(make_client(FakePage([js(200, {})])), 1) == "curso-1"
    with pytest.raises(AccessDeniedError):
        course_title(make_client(FakePage([js(403, {"detail": "x"})])), 1)
