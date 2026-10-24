"""Cues → párrafos naturales, con la marca de tiempo de cada uno."""

import re
from dataclasses import dataclass

# Medido con 4 178 cues de 28 lecciones reales (curso de Spring Boot, subtítulos manuales):
# con 1,5 s / 500 el 18 % de los párrafos era de una sola frase (<80 car.); con 2,5 s / 400
# la mediana es ~420 car. y solo el 5 % es tan corto.
PAUSE = 2.5        # segundos de silencio que cortan el párrafo
MAX_CHARS = 400    # largo a partir del cual un punto final cierra el párrafo

_SENTENCE_END = re.compile(r"[.!?…][\"'”’»)\]]*$")


@dataclass
class Paragraph:
    start: float   # segundos
    text: str


def build_paragraphs(cues, pause=PAUSE, max_chars=MAX_CHARS):
    """Agrupa los cues en párrafos.

    Un párrafo nuevo empieza tras una pausa de `pause` s o más, o cuando el actual
    ya pasa de `max_chars` y el cue anterior terminó una oración. Si el subtítulo
    no tiene puntuación (automáticos), solo corta la pausa.
    """
    paragraphs, parts, start, size, prev_end, prev_text = [], [], 0.0, 0, 0.0, ""

    def flush():
        if parts:
            paragraphs.append(Paragraph(start, " ".join(parts)))
            parts.clear()

    for cue in cues:
        if parts and (cue.start - prev_end >= pause or
                      (size >= max_chars and _SENTENCE_END.search(prev_text))):
            flush()
            size = 0
        if not parts:
            start = cue.start
        parts.append(cue.text)
        size += len(cue.text) + 1
        prev_end, prev_text = max(prev_end, cue.end), cue.text
    flush()
    return paragraphs


def marked(paragraphs, every=0):
    """(párrafo, ¿lleva marca de tiempo?).

    La primera siempre; con `every` > 0 solo las que llegan ≥ `every` s después
    de la última marcada (con 0, todas).
    """
    last = None
    for p in paragraphs:
        show = last is None or every <= 0 or p.start - last >= every
        if show:
            last = p.start
        yield p, show
