import json
from pathlib import Path

import pytest

from udemy_transcripts.client import ApiResult, Client
from udemy_transcripts.portal import Portal

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakePage:
    """Sustituye a la página de Playwright: `evaluate` devuelve respuestas guiadas."""

    def __init__(self, responses=None, handler=None, html="", title="Udemy"):
        self.responses = list(responses or [])
        self.handler = handler
        self.html = html
        self._title = title
        self.calls, self.visited = [], []

    def evaluate(self, script, url):
        self.calls.append(url)
        if self.handler:
            return self.handler(url)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def goto(self, url, wait_until=None):
        self.visited.append(url)

    def title(self):
        return self._title

    def content(self):
        return self.html


class FakeContext:
    """`context.request.get` sirve `files[url]`: (status, texto|bytes) o (status, cuerpo, cabeceras)."""

    def __init__(self, files=None):
        self.files = files or {}
        self.requested = []
        self.calls = []          # (url, headers)
        self.request = self

    def get(self, url, headers=None, timeout=None):
        self.requested.append(url)
        self.calls.append((url, headers))
        entry = self.files.get(url, (404, ""))
        status, body = entry[0], entry[1]
        heads = dict(entry[2]) if len(entry) > 2 else {}
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        total = len(data)
        if headers and "Range" in headers and 200 <= status < 300:
            status, data = 206, data[:1]
            heads.setdefault("Content-Range", f"bytes 0-0/{total}")
        return type("Resp", (), {
            "status": status, "ok": 200 <= status < 300, "headers": heads,
            "text": lambda s: data.decode("utf-8", "replace"), "body": lambda s: data})()


def js(status, body="", retry_after=None):
    """Respuesta tal como la devuelve el fetch() de la página."""
    import json as _json
    text = body if isinstance(body, str) else _json.dumps(body)
    return {"status": status, "text": text, "retryAfter": retry_after}


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def make_client(sleeps):
    def make(page=None, context=None, portal=None):
        return Client(context or FakeContext(), page or FakePage(), portal or Portal(),
                      sleep=sleeps.append, log=lambda *_: None)
    return make
