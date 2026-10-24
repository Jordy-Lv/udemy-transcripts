"""Acceso a Udemy a través de un navegador real (Playwright).

Las llamadas a la API se hacen con `fetch()` dentro de la página (same-origin,
con las cookies de la sesión), lo que atraviesa Cloudflare. Cada llamada
devuelve el status HTTP; los 429/5xx/fallos de red se reintentan con backoff.
"""

import json
import time
from dataclasses import dataclass
from typing import Optional

from .errors import (AccessDeniedError, ApiError, BlockedError, NotFoundError,
                     NotLoggedInError)

_FETCH_JS = """async (u) => {
    try {
        const r = await fetch(u, {headers: {'Accept': 'application/json'},
                                  credentials: 'include'});
        return {status: r.status, text: await r.text(),
                retryAfter: r.headers.get('retry-after')};
    } catch (e) {
        return {status: 0, text: String(e), retryAfter: null};
    }
}"""


@dataclass
class ApiResult:
    status: int
    text: str = ""
    retry_after: Optional[str] = None
    body: bytes = b""                      # descargas binarias (download_bytes)
    headers: Optional[dict] = None         # en minúsculas (download_bytes)

    @property
    def ok(self):
        return 200 <= self.status < 300

    @property
    def blocked(self):
        """Página de verificación de Cloudflare."""
        return self.status in (403, 503) and "just a moment" in self.text.lower()

    def json(self):
        try:
            return json.loads(self.text)
        except (ValueError, TypeError):
            return None


def is_retryable(result):
    if result.blocked:
        return False
    return result.status in (0, 429) or 500 <= result.status <= 599


def retry_delay(attempt, result, base=1.0, cap=30.0):
    """Segundos de espera antes del reintento nº `attempt+1` (0, 1, 2…)."""
    try:
        return min(float(result.retry_after), 60.0)
    except (TypeError, ValueError):
        return min(base * 2 ** attempt, cap)


def with_retries(request, attempts=4, base_delay=1.0, sleep=time.sleep, log=None,
                 what=""):
    """Ejecuta `request()` (→ ApiResult) y reintenta los fallos transitorios."""
    result = None
    for n in range(attempts):
        result = request()
        if not is_retryable(result) or n == attempts - 1:
            return result
        delay = retry_delay(n, result, base_delay)
        if log:
            cause = f"HTTP {result.status}" if result.status else "error de red"
            log(f"  ↻ {what}: {cause}; reintento {n + 1}/{attempts - 1} en {delay:g}s")
        sleep(delay)
    return result


def raise_for_status(result, what):
    """Convierte un resultado no exitoso en un error con mensaje claro."""
    if result.ok:
        return
    status = result.status
    if result.blocked:
        raise BlockedError(
            "Cloudflare bloqueó la petición. Ejecuta con la ventana visible "
            "(sin --headless) y espera a que termine la verificación.")
    if status == 401:
        raise NotLoggedInError(
            "La sesión no es válida o caducó (HTTP 401). Vuelve a iniciar sesión.")
    if status == 403:
        raise AccessDeniedError(
            f"Sin acceso a {what} (HTTP 403). ¿Hay sesión iniciada y estás "
            "inscrito en el curso?")
    if status == 404:
        raise NotFoundError(f"No se encontró {what} (HTTP 404).")
    if status == 0:
        raise ApiError(f"Error de red al pedir {what}: {result.text[:120]}")
    raise ApiError(f"Error al pedir {what} (HTTP {status}).")


class Client:
    """Navegador + portal. `sleep` y `log` son inyectables para los tests."""

    def __init__(self, context, page, portal, sleep=time.sleep, log=print):
        self.context = context
        self.page = page
        self.portal = portal
        self.sleep = sleep
        self.log = log

    def goto(self, url, wait=20):
        """Navega y espera a que Cloudflare resuelva su challenge si aparece."""
        if url.startswith("/"):
            url = self.portal.base + url
        self.page.goto(url, wait_until="domcontentloaded")
        for _ in range(wait):
            if "just a moment" not in (self.page.title() or "").lower():
                return
            self.sleep(1)

    def _fetch_once(self, url):
        try:
            raw = self.page.evaluate(_FETCH_JS, url)
            return ApiResult(raw["status"], raw.get("text") or "", raw.get("retryAfter"))
        except Exception as exc:   # navegación a mitad de la llamada, página cerrada…
            return ApiResult(0, str(exc))

    def get(self, url, what):
        """GET a la API con reintentos; devuelve el resultado sin lanzar por status."""
        return with_retries(lambda: self._fetch_once(url), sleep=self.sleep,
                            log=self.log, what=what)

    def get_json(self, url, what):
        result = self.get(url, what)
        raise_for_status(result, what)
        data = result.json()
        if data is None:
            raise ApiError(f"La respuesta de {what} no es JSON.")
        return data

    def paginate(self, url, what):
        """Todos los `results` de un endpoint paginado."""
        rows = []
        while url:
            data = self.get_json(url, what)
            rows.extend(data.get("results", []))
            url = data.get("next")
        return rows

    def download_text(self, url, what):
        """GET de un archivo (p. ej. un .vtt del CDN) con reintentos."""
        def once():
            try:
                resp = self.context.request.get(url)
                return ApiResult(resp.status, resp.text(),
                                 resp.headers.get("retry-after"))
            except Exception as exc:
                return ApiResult(0, str(exc))
        return with_retries(once, sleep=self.sleep, log=self.log, what=what)

    def download_bytes(self, url, what, headers=None, timeout=900_000):
        """GET binario (PDF, zip…) con reintentos; sin el tope de 30 s de Playwright."""
        def once():
            try:
                resp = self.context.request.get(url, headers=headers, timeout=timeout)
                head = {k.lower(): v for k, v in dict(resp.headers).items()}
                return ApiResult(resp.status, "", head.get("retry-after"),
                                 resp.body() if resp.ok else b"", head)
            except Exception as exc:
                return ApiResult(0, str(exc))
        return with_retries(once, sleep=self.sleep, log=self.log, what=what)


def current_user(client):
    """Usuario de la sesión, o None si no hay sesión iniciada."""
    result = client.get(f"{client.portal.api}/users/me/?fields%5Buser%5D=title",
                        "tu sesión")
    if result.blocked:
        raise_for_status(result, "tu sesión")
    if result.status in (401, 403):
        return None
    raise_for_status(result, "tu sesión")
    data = result.json()
    if isinstance(data, dict) and isinstance(data.get("id"), int) and data["id"] > 0:
        return data
    return None


def ensure_login(client, input_fn=input):
    client.goto("/")
    user = current_user(client)
    if not user:
        print(f"\n▶ Inicia sesión en {client.portal.host} en la ventana de Chromium "
              "que se abrió.")
        try:
            input_fn("  Cuando ya estés dentro de tu cuenta, vuelve aquí y pulsa ENTER… ")
        except EOFError:
            raise NotLoggedInError(
                "No hay sesión iniciada y no puedo pedir el login sin una terminal "
                "interactiva. Ejecútalo una vez sin redirigir la entrada, o usa --token.")
        client.goto("/")
        user = current_user(client)
        if not user:
            raise NotLoggedInError("No detecto sesión iniciada. Vuelve a intentarlo.")
    print(f"  ✓ Sesión activa: {user.get('title') or user.get('id')}")
    return user
