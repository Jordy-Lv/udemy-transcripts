"""Escape de texto literal para Markdown."""

import re

_SPECIAL = re.compile(r"([\\`*_\[\]<>$])")


def escape_inline(text):
    """Escapa lo que Markdown interpretaría dentro de una línea."""
    return _SPECIAL.sub(r"\\\1", text)


def guard_block_start(text):
    """Evita que el inicio de un bloque se lea como lista o título."""
    text = re.sub(r"^(\d+)([.)])", r"\1\\\2", text)   # «3. algo» no es una lista
    return re.sub(r"^([#+-])", r"\\\1", text)


def md_escape(text):
    """Texto literal de un párrafo (una transcripción) → Markdown seguro."""
    return guard_block_start(escape_inline(text))
