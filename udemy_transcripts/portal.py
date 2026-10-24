"""Host del portal: www.udemy.com (personal) o <org>.udemy.com (Udemy Business)."""

import re
from dataclasses import dataclass

DEFAULT_HOST = "www.udemy.com"

_HOST_RE = re.compile(
    r"^(?:https?://)?([a-z0-9-]+(?:\.[a-z0-9-]+)*\.udemy\.com)(?:[:/?#]|$)", re.I)


@dataclass(frozen=True)
class Portal:
    host: str = DEFAULT_HOST

    @property
    def base(self):
        return f"https://{self.host}"

    @property
    def api(self):
        return f"{self.base}/api-2.0"

    @property
    def is_business(self):
        return self.host != DEFAULT_HOST


def portal_from_ref(ref):
    """Portal de una URL de curso; cualquier otra cosa (slug, id) usa www."""
    m = _HOST_RE.match((ref or "").strip())
    return Portal(m.group(1).lower()) if m else Portal()
