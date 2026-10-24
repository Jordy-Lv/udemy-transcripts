"""Opciones y utilidades comunes a los formatos de salida."""

from dataclasses import dataclass

from ..paragraphs import MAX_CHARS, PAUSE

RENDER_VERSION = 2   # súbela si cambia la salida para que --update regenere los archivos


@dataclass(frozen=True)
class RenderOptions:
    format: str = "md"          # "md" | "txt"
    timestamps: bool = True
    ts_every: int = 0           # 0 = una marca por párrafo
    width: int = 100            # solo txt; 0 = sin ajustar
    pause: float = PAUSE
    max_chars: int = MAX_CHARS

    @property
    def ext(self):
        return "md" if self.format == "md" else "txt"

    @property
    def signature(self):
        """Identifica cómo se generaron los archivos (para --update)."""
        width = self.width if self.format == "txt" else 0
        return (f"{self.format}|ts={int(self.timestamps)}|every={self.ts_every}"
                f"|w={width}|p={self.pause:g}|m={self.max_chars}|v={RENDER_VERSION}")


def fmt_time(seconds):
    """`mm:ss` o `h:mm:ss`; cadena vacía si no hay dato."""
    if seconds is None:
        return ""
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
