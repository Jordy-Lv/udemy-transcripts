import os
import re
from pathlib import Path

_LONG_PATH = 240                 # margen bajo MAX_PATH (260) de Windows
_EXTENDED = "\\\\?\\"            # prefijo \\?\
_EXTENDED_UNC = "\\\\?\\UNC\\"   # prefijo \\?\UNC\
_INVALID = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


def safe_name(name, fallback="sin título", maxlen=120):
    """Nombre válido como archivo/carpeta en Windows, macOS y Linux."""
    name = _INVALID.sub("-", name or "")
    name = re.sub(r"\s+", " ", name).strip()[:maxlen].rstrip(". ")
    return name or fallback


def fs_path(path):
    """Ruta usable para escribir; en Windows añade el prefijo de ruta extendida si es larga.

    Sin el prefijo, Windows rechaza (FileNotFoundError) las rutas de más de 259
    caracteres, algo común con una carpeta de salida profunda y títulos largos.
    """
    path = Path(path)
    if os.name != "nt":
        return path
    text = str(path.resolve())
    if len(text) < _LONG_PATH or text.startswith(_EXTENDED):
        return path
    if text.startswith("\\\\"):                       # \\servidor\recurso
        return Path(_EXTENDED_UNC + text[2:])
    return Path(_EXTENDED + text)
