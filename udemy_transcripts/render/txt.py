"""Salida en texto plano: una oración por línea, párrafos separados por una línea
en blanco y, si se piden, marcas `[mm:ss]` al inicio del párrafo (sin enlace)."""

import re
import textwrap

from ..paragraphs import marked
from .common import fmt_time


def paragraphs_to_text(paragraphs, opts):
    blocks = []
    pairs = marked(paragraphs, opts.ts_every) if opts.timestamps \
        else ((p, False) for p in paragraphs)
    for paragraph, show in pairs:
        lines = re.split(r"(?<=[.!?])\s+", paragraph.text.strip())
        if show:
            lines[0] = f"[{fmt_time(paragraph.start)}] {lines[0]}"
        if opts.width and opts.width > 0:
            lines = [textwrap.fill(line, opts.width) for line in lines]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def single_part(num, section, title, text):
    """Bloque de una lección dentro del archivo único."""
    return f"{'=' * 70}\n[{num}] {section} — {title}\n{'=' * 70}\n\n{text}"


def table_of_contents(entries):
    """`entries`: [(título de sección, [(número, título, duración), …]), …]."""
    lines = ["CONTENIDO", ""]
    for section, lessons in entries:
        lines.append(section)
        for number, title, duration in lessons:
            lines.append(f"  {number} - {title}" + (f"  ({duration})" if duration else ""))
        lines.append("")
    return "\n".join(lines).rstrip()


def single_file(course_title, parts, toc=None):
    head = f"{course_title}\n\n" + (f"{toc}\n\n" if toc else "")
    return head + "\n\n".join(parts) + "\n"


def single_document(course, items):
    """Archivo único con tabla de contenidos. `items`: [(sección, lección, bloque)]."""
    toc, parts = [], []
    for section, lecture, block in items:
        if not toc or toc[-1][0] != section.dirname:
            toc.append((section.dirname, []))
        toc[-1][1].append((lecture.number, lecture.title,
                           fmt_time(lecture.duration) if lecture.duration else ""))
        parts.append(block)
    return single_file(course.title, parts, table_of_contents(toc))
