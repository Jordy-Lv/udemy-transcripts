"""Salida en texto plano (el formato histórico de la herramienta)."""

import re
import textwrap


def cues_to_text(cues, width=100):
    """Una oración por bloque (si hay puntuación) y ajuste de línea a `width`."""
    text = re.sub(r"\s+", " ", " ".join(c.text for c in cues)).strip()
    text = re.sub(r"(?<=[.!?])\s+", "\n", text)
    if width and width > 0:
        text = "\n".join(textwrap.fill(p, width) if p else "" for p in text.split("\n"))
    return text


def single_part(num, section, title, text):
    """Bloque de una lección dentro del archivo único."""
    return f"{'=' * 70}\n[{num}] {section} — {title}\n{'=' * 70}\n\n{text}"


def single_file(course_title, parts):
    return f"{course_title}\n\n" + "\n\n".join(parts) + "\n"
