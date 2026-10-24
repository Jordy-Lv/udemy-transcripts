import pytest

from conftest import FakeContext, FakePage, js
from udemy_transcripts.client import (ApiResult, current_user, ensure_login, is_retryable,
                                      raise_for_status, retry_delay, with_retries)
from udemy_transcripts.errors import (AccessDeniedError, ApiError, BlockedError,
                                      NotFoundError, NotLoggedInError)

CLOUDFLARE = "<html><title>Just a moment...</title></html>"


def test_retryable_statuses():
    assert all(is_retryable(ApiResult(s)) for s in (0, 429, 500, 502, 503, 599))
    assert not any(is_retryable(ApiResult(s)) for s in (200, 401, 403, 404, 400))
    assert not is_retryable(ApiResult(503, CLOUDFLARE))     # challenge: no reintentar


def test_retry_delay_exponential_capped_and_retry_after():
    assert [retry_delay(n, ApiResult(500)) for n in range(4)] == [1, 2, 4, 8]
    assert retry_delay(10, ApiResult(500)) == 30
    assert retry_delay(0, ApiResult(429, retry_after="7")) == 7
    assert retry_delay(0, ApiResult(429, retry_after="9999")) == 60
    assert retry_delay(1, ApiResult(429, retry_after="mañana")) == 2


def test_with_retries_recovers_after_transient_failures(sleeps):
    results = iter([ApiResult(429), ApiResult(0, "red"), ApiResult(200, "{}")])
    out = with_retries(lambda: next(results), sleep=sleeps.append)
    assert out.status == 200 and sleeps == [1, 2]


def test_with_retries_gives_up_and_returns_last_result(sleeps):
    calls = []
    out = with_retries(lambda: calls.append(1) or ApiResult(500), attempts=3,
                       sleep=sleeps.append)
    assert out.status == 500 and len(calls) == 3 and sleeps == [1, 2]


def test_with_retries_does_not_retry_client_errors(sleeps):
    calls = []
    out = with_retries(lambda: calls.append(1) or ApiResult(403), sleep=sleeps.append)
    assert out.status == 403 and len(calls) == 1 and sleeps == []


def test_with_retries_logs(sleeps):
    msgs = []
    results = iter([ApiResult(503), ApiResult(200)])
    with_retries(lambda: next(results), sleep=sleeps.append, log=msgs.append, what="el temario")
    assert "el temario" in msgs[0] and "HTTP 503" in msgs[0] and "1/3" in msgs[0]


@pytest.mark.parametrize("status, text, error", [
    (401, "", NotLoggedInError),
    (403, "{}", AccessDeniedError),
    (403, CLOUDFLARE, BlockedError),
    (404, "", NotFoundError),
    (0, "net::ERR", ApiError),
    (500, "", ApiError),
])
def test_raise_for_status_maps_errors(status, text, error):    # B3
    with pytest.raises(error):
        raise_for_status(ApiResult(status, text), "el temario")


def test_raise_for_status_message_mentions_resource_and_enrollment():
    with pytest.raises(AccessDeniedError, match="el temario.*inscrito"):
        raise_for_status(ApiResult(403), "el temario")


def test_raise_for_status_ok_is_silent():
    raise_for_status(ApiResult(204), "x")


def test_get_retries_and_survives_evaluate_exceptions(make_client, sleeps):
    page = FakePage([RuntimeError("Execution context was destroyed"), js(502), js(200, {"a": 1})])
    assert make_client(page).get_json("https://x/api", "algo") == {"a": 1}
    assert sleeps == [1, 2]


def test_get_json_raises_on_403_and_on_html(make_client):    # B3
    with pytest.raises(AccessDeniedError):
        make_client(FakePage([js(403, {"detail": "no"})])).get_json("u", "el temario")
    with pytest.raises(ApiError, match="no es JSON"):
        make_client(FakePage([js(200, "<html>")])).get_json("u", "el temario")


def test_paginate_collects_all_pages(make_client):
    page = FakePage([js(200, {"results": [1, 2], "next": "https://x/2"}),
                     js(200, {"results": [3], "next": None})])
    assert make_client(page).paginate("https://x/1", "cosas") == [1, 2, 3]


def test_download_text_retries_then_returns_status(make_client, sleeps):
    class Flaky(FakeContext):
        def get(self, url):
            self.requested.append(url)
            status = 429 if len(self.requested) < 3 else 200
            return type("R", (), {"status": status, "text": lambda s: "WEBVTT",
                                  "headers": {"retry-after": "3"}})()
    ctx = Flaky()
    res = make_client(context=ctx).download_text("https://cdn/a.vtt", "el subtítulo")
    assert res.ok and res.text == "WEBVTT" and sleeps == [3, 3]


def test_current_user(make_client):
    ok = {"id": 7, "title": "Ana"}
    assert current_user(make_client(FakePage([js(200, ok)])))["title"] == "Ana"
    assert current_user(make_client(FakePage([js(200, {"id": 0})]))) is None   # anónimo
    assert current_user(make_client(FakePage([js(401)]))) is None
    assert current_user(make_client(FakePage([js(403, {"detail": "x"})]))) is None
    with pytest.raises(BlockedError):
        current_user(make_client(FakePage([js(403, CLOUDFLARE)])))
    with pytest.raises(ApiError):
        current_user(make_client(FakePage([js(500)] * 4)))


def test_ensure_login_already_logged(make_client):
    page = FakePage([js(200, {"id": 7, "title": "Ana"})])
    assert ensure_login(make_client(page), input_fn=lambda *_: pytest.fail("no debe pedir login"))["id"] == 7
    assert page.visited == ["https://www.udemy.com/"]


def test_ensure_login_prompts_and_rechecks(make_client):
    page = FakePage([js(401), js(200, {"id": 7, "title": "Ana"})])
    asked = []
    ensure_login(make_client(page), input_fn=asked.append)
    assert len(asked) == 1 and len(page.visited) == 2


def test_ensure_login_fails_if_still_anonymous_or_non_interactive(make_client):
    with pytest.raises(NotLoggedInError, match="No detecto sesión"):
        ensure_login(make_client(FakePage([js(401), js(401)])), input_fn=lambda *_: None)

    def eof(*_):
        raise EOFError
    with pytest.raises(NotLoggedInError, match="interactiva"):
        ensure_login(make_client(FakePage([js(401)])), input_fn=eof)


def test_goto_waits_for_cloudflare_challenge(make_client, sleeps):
    page = FakePage(title="Just a moment...")
    make_client(page).goto("/course/x/", wait=3)
    assert page.visited == ["https://www.udemy.com/course/x/"] and sleeps == [1, 1, 1]
