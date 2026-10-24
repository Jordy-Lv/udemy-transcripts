"""Rangos numéricos de la CLI: `3-5,8`, `12-` (desde 12 hasta el final)."""

import re

from .errors import UdemyError

_TOKEN = re.compile(r"^(\d+)(?:(-)(\d*))?$")


def parse_ranges(spec, flag="--sections"):
    """`"3-5,8,12-"` → `[(3, 5), (8, 8), (12, None)]`; `None` o vacío → `[]` (todo)."""
    if spec is None or not spec.strip():
        return []
    ranges = []
    for token in spec.split(","):
        m = _TOKEN.match(token.strip())
        if not m:
            raise UdemyError(f"{flag}: «{token.strip()}» no es válido. Usa números o rangos, "
                             "p. ej. 3-5,8 o 12- (desde el 12).")
        low = int(m.group(1))
        high = (int(m.group(3)) if m.group(3) else None) if m.group(2) else low
        if high is not None and high < low:
            raise UdemyError(f"{flag}: el rango {low}-{high} está al revés.")
        ranges.append((low, high))
    return ranges


def in_ranges(number, ranges):
    """¿`number` cae en algún rango? Una lista vacía significa «sin filtro»."""
    if not ranges:
        return True
    if not isinstance(number, int):
        return False
    return any(low <= number and (high is None or number <= high) for low, high in ranges)


def make_selector(section_ranges, lecture_ranges):
    """Función `(sección, lección) → bool` según `--sections` y `--lectures`."""
    def select(section, lecture):
        return in_ranges(section.index, section_ranges) and in_ranges(lecture.index, lecture_ranges)
    return select
