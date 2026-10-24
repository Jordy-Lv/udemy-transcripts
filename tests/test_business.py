import pytest

from conftest import FakePage, js
from udemy_transcripts import cli
from udemy_transcripts.courses import list_courses
from udemy_transcripts.curriculum import fetch_curriculum
from udemy_transcripts.errors import AccessDeniedError, UdemyError
from udemy_transcripts.portal import (Portal, choose_portal, host_from_ref,
                                      portal_from_org, token_cookie)

SETI = Portal("seti.udemy.com")


def test_host_from_ref():
    assert host_from_ref("https://seti.udemy.com/course/x/") == "seti.udemy.com"
    assert host_from_ref("https://www.udemy.com/course/x/") == "www.udemy.com"
    assert host_from_ref("mi-curso") is None and host_from_ref(None) is None
    assert host_from_ref("12345") is None


@pytest.mark.parametrize("org", ["seti", "SETI", " seti ", "seti.udemy.com",
                                 "https://seti.udemy.com/course/x/learn/"])
def test_portal_from_org_accepts_several_spellings(org):
    assert portal_from_org(org) == SETI


@pytest.mark.parametrize("org", ["", "   ", "se ti", "../x", "a.b.c", "-x"])
def test_portal_from_org_rejects_garbage(org):
    with pytest.raises(UdemyError, match="Organización no válida"):
        portal_from_org(org)


def test_choose_portal_precedence():
    assert choose_portal("https://seti.udemy.com/course/x/", "otra") == SETI   # la URL manda
    assert choose_portal("https://www.udemy.com/course/x/", "seti") == Portal()
    assert choose_portal("mi-curso", "seti") == SETI
    assert choose_portal("12345", "seti") == SETI
    assert choose_portal(None, "seti") == SETI
    assert choose_portal("mi-curso", None) == Portal()
    assert choose_portal(None, None) == Portal()


def test_token_cookie_is_scoped_to_the_portal():
    business = token_cookie("tok", SETI)
    assert business == {"name": "access_token", "value": "tok",
                        "url": "https://seti.udemy.com"}
    assert token_cookie("tok", Portal()) == {          # sin cambios para www
        "name": "access_token", "value": "tok", "domain": ".udemy.com",
        "path": "/", "secure": True}


def test_cli_parses_business_flag_and_env(monkeypatch):
    assert cli.build_parser().parse_args(["--business", "seti", "--list"]).business == "seti"
    monkeypatch.setenv("UDEMY_BUSINESS", "acme")
    assert cli.build_parser().parse_args(["--list"]).business == "acme"


def test_api_calls_use_the_portal_host(make_client):
    page = FakePage([js(200, {"results": [], "next": None})])
    list_courses(make_client(page, portal=SETI))
    assert page.calls[0].startswith("https://seti.udemy.com/api-2.0/users/me/subscribed-courses/")


def test_list_courses_on_www_only_uses_subscribed_courses(make_client):
    page = FakePage([js(200, {"results": [{"id": 1, "title": "A"}], "next": None})])
    assert list_courses(make_client(page)) == [{"id": 1, "title": "A"}]
    assert len(page.calls) == 1


def test_list_courses_business_merges_enrollments_without_duplicates(make_client):
    page = FakePage([
        js(200, {"results": [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}], "next": None}),
        js(200, {"results": [
            {"id": 2, "title": "B"},                              # duplicado
            {"course": {"id": 3, "title": "C", "url": "/course/c/"}},   # anidado
            {"id": 4, "title": "D"},
            {"id": 5},                                            # sin título: se ignora
        ], "next": None})])
    rows = list_courses(make_client(page, portal=SETI))
    assert [c["id"] for c in rows] == [1, 2, 3, 4]
    assert "subscription-course-enrollments" in page.calls[1]


@pytest.mark.parametrize("failure", [js(404), js(403, {"detail": "x"}), js(500)])
def test_list_courses_business_ignores_a_failing_enrollments_endpoint(make_client, failure):
    page = FakePage([js(200, {"results": [{"id": 1, "title": "A"}], "next": None})]
                    + [failure] * 4)
    assert [c["id"] for c in list_courses(make_client(page, portal=SETI))] == [1]


def test_business_403_on_curriculum_explains_how_to_enroll(make_client):
    page = FakePage([js(403, {"detail": "no"})])
    with pytest.raises(AccessDeniedError, match="Empezar curso") as exc:
        fetch_curriculum(make_client(page, portal=SETI), 123)
    assert "https://seti.udemy.com" in str(exc.value)


def test_www_403_on_curriculum_keeps_the_generic_message(make_client):
    page = FakePage([js(403, {"detail": "no"})])
    with pytest.raises(AccessDeniedError, match="inscrito") as exc:
        fetch_curriculum(make_client(page), 123)
    assert "Empezar curso" not in str(exc.value)


def test_business_login_and_course_flow_use_the_org_host(make_client):
    from udemy_transcripts.client import ensure_login
    page = FakePage([js(200, {"id": 7, "title": "Ana"})])
    ensure_login(make_client(page, portal=SETI))
    assert page.visited == ["https://seti.udemy.com/"]
    assert page.calls[0].startswith("https://seti.udemy.com/api-2.0/users/me/")
