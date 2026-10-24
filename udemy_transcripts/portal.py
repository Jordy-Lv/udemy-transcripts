"""Host del portal: www.udemy.com (personal) o <org>.udemy.com (Udemy Business)."""

import re
from dataclasses import dataclass

from .errors import UdemyError

DEFAULT_HOST = "www.udemy.com"

_HOST_RE = re.compile(
    r"^(?:https?://)?([a-z0-9-]+(?:\.[a-z0-9-]+)*\.udemy\.com)(?:[:/?#]|$)", re.I)
_ORG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


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


def host_from_ref(ref):
    """Host de una URL de Udemy (con o sin esquema); None si `ref` no lo trae."""
    m = _HOST_RE.match((ref or "").strip())
    return m.group(1).lower() if m else None


def portal_from_ref(ref):
    """Portal de una URL de curso; cualquier otra cosa (slug, id) usa www."""
    host = host_from_ref(ref)
    return Portal(host) if host else Portal()


def portal_from_org(org):
    """Portal de Business a partir de `seti`, `seti.udemy.com` o una URL del portal."""
    org = (org or "").strip()
    host = host_from_ref(org)
    if host:
        return Portal(host)
    org = org.lower()
    if not _ORG_RE.match(org):
        raise UdemyError(f"Organización no válida: {org!r}. Usa el subdominio "
                         "(p. ej. «seti» para seti.udemy.com).")
    return Portal(f"{org}.udemy.com")


def choose_portal(ref=None, business=None):
    """Portal a usar: el host de la URL manda; si no, `--business`; si no, www."""
    if host_from_ref(ref):
        return Portal(host_from_ref(ref))
    if business:
        return portal_from_org(business)
    return Portal()


def token_cookie(token, portal):
    """Cookie `access_token` para inyectar la sesión en el dominio del portal."""
    cookie = {"name": "access_token", "value": token}
    if portal.is_business:
        cookie["url"] = portal.base            # cookie del host del portal, no de todo .udemy.com
    else:
        cookie.update(domain=".udemy.com", path="/", secure=True)
    return cookie
