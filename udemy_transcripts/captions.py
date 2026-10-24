"""Subtítulos: selección de idioma y parser WebVTT basado en bloques de cue."""

import html
import re
from collections import namedtuple
from dataclasses import dataclass
from typing import Optional

from .errors import UdemyError

_TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})")
_TIMING = re.compile(r"^\s*(\S+)\s+-->\s+(\S+)")
_TAG = re.compile(r"<[^>]+>")
_BLOCK_SEP = re.compile(r"\n[ \t]*\n")


@dataclass
class Cue:
    start: float   # segundos
    end: float
    text: str


Pick = namedtuple("Pick", "caption preferred")


def _seconds(stamp):
    m = _TIME.fullmatch(stamp)
    if not m:
        return None
    hours, minutes, seconds, millis = m.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_vtt(vtt):
    """Lista de `Cue` en orden.

    Se trabaja por bloques (separados por línea en blanco): el identificador
    opcional de un cue es la línea anterior a la de tiempos y se descarta
    aunque sea un número; el texto del cue conserva cualquier línea, incluidas
    las que sean solo un número. Las líneas idénticas consecutivas se colapsan
    (los subtítulos "rodantes" repiten la última línea en el cue siguiente).
    """
    text = vtt.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    cues, last_line = [], None
    for block in _BLOCK_SEP.split(text):
        lines = block.split("\n")
        idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if idx is None or idx > 1:       # cabecera, NOTE, STYLE, REGION…
            continue
        m = _TIMING.match(lines[idx])
        start, end = (_seconds(m.group(1)), _seconds(m.group(2))) if m else (None, None)
        if start is None or end is None:
            continue
        kept = []
        for raw in lines[idx + 1:]:
            line = re.sub(r"\s+", " ", html.unescape(_TAG.sub("", raw))).strip()
            if line and line != last_line:
                kept.append(line)
                last_line = line
        if kept:
            cues.append(Cue(start, end, " ".join(kept)))
    return cues


def _locale_matches(locale, want):
    loc = (locale or "").lower().replace("-", "_")
    want = want.strip().lower().replace("-", "_")
    return bool(want) and (loc == want or loc.startswith(want + "_"))


def pick_caption(captions, langs):
    """Elige el subtítulo según `langs` (orden de preferencia).

    Devuelve `Pick(caption, preferred)`; `preferred` es False si se tuvo que
    usar otro idioma que el primero pedido. Entre subtítulos del mismo idioma
    se prefiere el manual al automático. Sin subtítulos con URL → (None, False).
    """
    usable = [c for c in captions or [] if c.get("url")]
    if not usable:
        return Pick(None, False)
    for rank, want in enumerate(langs):
        matches = [c for c in usable if _locale_matches(c.get("locale_id"), want)]
        if matches:
            matches.sort(key=lambda c: c.get("source") == "auto")   # estable
            return Pick(matches[0], rank == 0)
    return Pick(usable[0], not langs)


@dataclass
class LangSpec:
    """Idiomas pedidos: preferencias en orden y, opcionalmente, una 2.ª pista (bilingüe)."""
    prefs: list
    secondary: Optional[str] = None


def parse_lang_spec(value):
    """`es,en` → preferencias; `es+en` → texto en es con la pista en como segunda columna.

    El par bilingüe pasa a ser la primera preferencia; solo se admite uno.
    """
    prefs, secondary = [], None
    for token in (value or "").split(","):
        token = token.strip()
        if not token:
            continue
        if "+" in token:
            first, second = (part.strip() for part in token.split("+", 1))
            if not first or not second or "+" in second or secondary is not None:
                raise UdemyError(f"--lang: «{token}» no es válido. Usa un solo par, p. ej. es+en.")
            prefs.insert(0, first)
            secondary = second
        else:
            prefs.append(token)
    return LangSpec(prefs, secondary)


def pick_secondary(captions, want, primary):
    """Pista de `want` distinta de la principal (o None); prefiere la manual a la automática."""
    primary_locale = (primary or {}).get("locale_id")
    matches = [c for c in captions or [] if c.get("url") and c.get("locale_id") != primary_locale
               and _locale_matches(c.get("locale_id"), want)]
    matches.sort(key=lambda c: c.get("source") == "auto")
    return matches[0] if matches else None
