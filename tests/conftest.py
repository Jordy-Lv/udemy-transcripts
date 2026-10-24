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
    """`context.request.get` responde con lo que diga `files[url]` (status, texto)."""

    def __init__(self, files=None):
        self.files = files or {}
        self.requested = []
        self.request = self

    def get(self, url):
        self.requested.append(url)
        status, text = self.files.get(url, (404, ""))
        return type("Resp", (), {"status": status, "text": lambda s: text,
                                 "headers": {}})()


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
