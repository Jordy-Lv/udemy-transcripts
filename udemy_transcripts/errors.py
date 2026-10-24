"""Errores explícitos: el mensaje de cada uno se muestra tal cual al usuario."""


class UdemyError(Exception):
    """Error base; la CLI imprime el mensaje y termina con código 1."""


class NotLoggedInError(UdemyError):
    """No hay sesión iniciada o caducó."""


class AccessDeniedError(UdemyError):
    """La sesión es válida pero no da acceso al recurso (p. ej. no inscrito)."""


class NotFoundError(UdemyError):
    """El recurso no existe."""


class BlockedError(UdemyError):
    """Cloudflare bloqueó la petición."""


class ApiError(UdemyError):
    """Cualquier otro fallo de la API o de la red."""
