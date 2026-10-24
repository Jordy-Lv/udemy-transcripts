import re

_INVALID = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


def safe_name(name, fallback="sin título", maxlen=120):
    """Nombre válido como archivo/carpeta en Windows, macOS y Linux."""
    name = _INVALID.sub("-", name or "")
    name = re.sub(r"\s+", " ", name).strip()[:maxlen].rstrip(". ")
    return name or fallback
