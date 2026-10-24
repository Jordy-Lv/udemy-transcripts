"""Curso unificado: todas las lecciones descargadas en un solo Markdown (o en unas pocas partes).

Pensado para herramientas que no aceptan carpetas, como NotebookLM o Notion. Se construye a
partir de lo ya escrito en disco (`.udemy-transcripts.json` + los `.md` de cada lección), así que
funciona igual tras `--update`, con `--study` y sin abrir Udemy (`--merge-from`).

Respecto a `--single` (que sustituye a la carpeta y se escribe al final), aquí la carpeta por
lecciones se conserva y el unificado se regenera cuando se quiera. Además se limpia para que se
lea bien fuera de tu disco: sin cabeceras YAML, sin enlaces a rutas locales y con las marcas de
tiempo sin URL.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from .errors import UdemyError
from .render.common import fmt_time
from .render.mdtext import md_escape
from .study import load_manifest
from .util import fs_path, safe_name

MAX_WORDS = 400_000           # NotebookLM admite ~500.000 palabras por fuente: queda margen

_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_HEADING = re.compile(r"^(#{1,6}) (.*)$")
_LINK = re.compile(r"(!?)\[((?:[^\[\]\\]|\\.)*)\]\(([^)\s]*)\)")
_STAMP = re.compile(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]\([^)\s]*\)")
_SCHEME = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//|#)")
_COURSE_URL = re.compile(r"\[Abrir el curso en Udemy\]\(([^)\s]+)\)")


@dataclass
class MergeLesson:
    number: str
    title: str
    text: str
    duration: str = ""

    @property
    def words(self):
        return len(self.text.split())

    @property
    def index(self):
        return int(self.number) if self.number.isdigit() else None


@dataclass
class MergeSection:
    index: int
    dirname: str
    lessons: list = field(default_factory=list)
    title: str = ""            # título real de la sección (el nombre de carpeta va sin «:» ni «?»)

    @property
    def heading(self):
        """«01 - Introducción: ¿qué es?» (número de la carpeta + título real, si se conoce)."""
        number = self.dirname.split(" - ", 1)[0]
        return f"{number} - {self.title}" if self.title else self.dirname

    @property
    def words(self):
        return sum(lesson.words for lesson in self.lessons)


def _n(number):
    """Número con punto de millar: 400.000."""
    return f"{number:,}".replace(",", ".")


def split_front_matter(raw):
    """(metadatos, resto) de un archivo de lección; `{}` si no tiene cabecera YAML."""
    text = raw.replace("\r\n", "\n")
    m = _FRONT.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).split("\n"):
        key, _, value = line.partition(": ")
        try:
            meta[key.strip()] = json.loads(value)
        except ValueError:
            meta[key.strip()] = value.strip()
    return meta, text[m.end():]


def clean_links(line):
    """Marcas de tiempo sin URL y enlaces o imágenes a rutas locales reducidos a su texto."""
    line = _STAMP.sub(r"[\1]", line)

    def local(m):
        bang, text, target = m.groups()
        if _SCHEME.match(target):
            return m.group(0)                          # web, ancla o mailto: se conserva
        if bang:
            return f"*[imagen: {text}]*" if text else ""
        return text
    return _LINK.sub(local, line)


def lesson_text(body, number):
    """Cuerpo de una lección listo para el unificado: título `###` y resto de encabezados +2."""
    out, in_fence, seen_title = [], False, False
    for line in body.split("\n"):
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            m = _HEADING.match(line)
            if m:
                level, text = len(m.group(1)), m.group(2)
                if level == 1 and not seen_title:
                    seen_title = True
                    line = f"### {number} - {text}"
                else:
                    line = f"{'#' * min(level + 2, 6)} {text}"
            line = clean_links(line)
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def collect(course_dir, manifest, select=None):
    """(título del curso, secciones con sus lecciones) de lo descargado en Markdown."""
    grouped, title = {}, ""
    for item in manifest.downloaded(course_dir):
        if item.path.suffix != ".md":
            continue
        meta, body = split_front_matter(item.path.read_text(encoding="utf-8"))
        title = title or meta.get("curso") or ""
        entry = item.entry
        section = grouped.setdefault(item.dirname, MergeSection(
            item.section_index, item.dirname, title=entry.get("section") or ""))
        lesson = MergeLesson(
            item.number, entry.get("title") or item.name, lesson_text(body, item.number),
            fmt_time(entry.get("duration")) if entry.get("kind") == "video"
            and entry.get("duration") else "")
        if lesson.text and (select is None or select(SimpleNamespace(index=section.index),
                                                     SimpleNamespace(index=lesson.index))):
            section.lessons.append(lesson)
    sections = [s for s in grouped.values() if s.lessons]
    for section in sections:
        section.lessons.sort(key=lambda lesson: (lesson.index is None, lesson.index or 0,
                                                 lesson.number))
    return title, sorted(sections, key=lambda s: (s.index, s.dirname))


def split_parts(sections, max_words):
    """Reparte las secciones en partes de como mucho `max_words` palabras.

    Corta en fronteras de sección; solo parte una sección por lecciones si ella sola no cabe.
    `max_words` 0 = una sola parte.
    """
    if not max_words:
        return [sections]
    parts, current, size = [], [], 0

    def flush():
        nonlocal current, size
        if current:
            parts.append(current)
        current, size = [], 0

    for section in sections:
        if size and section.words <= max_words and size + section.words > max_words:
            flush()
        chunk = []
        for lesson in section.lessons:
            if size and size + lesson.words > max_words:
                if chunk:
                    current.append(MergeSection(section.index, section.dirname, chunk,
                                                section.title))
                    chunk = []
                flush()
            chunk.append(lesson)
            size += lesson.words
        if chunk:
            current.append(MergeSection(section.index, section.dirname, chunk, section.title))
    flush()
    return parts


def render_part(title, url, sections, number=1, total=1, lessons_total=None):
    """Un archivo del unificado: cabecera, contenido y las secciones con sus lecciones."""
    count = sum(len(s.lessons) for s in sections)
    heading = f"# {md_escape(title)}" + (f" (parte {number} de {total})" if total > 1 else "")
    head = [heading, ""]
    if url:
        head += [f"[Abrir el curso en Udemy]({url})", ""]
    head.append(f"{count} lecciones" + (f" de {lessons_total}" if total > 1 and lessons_total
                                        else ""))
    head += ["", "## Contenido", ""]
    for section in sections:
        head.append(f"- {md_escape(section.heading)}")
        for lesson in section.lessons:
            dur = f" ({lesson.duration})" if lesson.duration else ""
            head.append(f"  - {md_escape(lesson.number + ' - ' + lesson.title)}{dur}")
    blocks = ["\n".join(head)]
    for section in sections:
        blocks.append(f"## {md_escape(section.heading)}")
        blocks.extend(lesson.text for lesson in section.lessons)
    return "\n\n".join(blocks) + "\n"


def course_url(course_dir):
    """Enlace al curso, si el `README.md` de la carpeta lo trae."""
    try:
        m = _COURSE_URL.search(fs_path(Path(course_dir) / "README.md").read_text(encoding="utf-8"))
    except OSError:
        return ""
    return m.group(1) if m else ""


def _output_names(course_dir, total):
    base = Path(course_dir).resolve().name
    if total == 1:
        return [Path(course_dir).resolve().parent / f"{base}.md"]
    return [Path(course_dir).resolve().parent / f"{base} (parte {n} de {total}).md"
            for n in range(1, total + 1)]


def _remove_stale(course_dir, keep):
    """Borra unificados de una ejecución anterior que ya no corresponden (otro nº de partes)."""
    parent = Path(course_dir).resolve().parent
    base = Path(course_dir).resolve().name
    pattern = re.compile(rf"{re.escape(base)}(?: \(parte \d+ de \d+\))?\.md")
    for path in parent.glob("*.md"):
        if pattern.fullmatch(path.name) and path not in keep:
            try:
                fs_path(path).unlink()
            except OSError:
                pass


def merge_course(course_dir, select=None, max_words=MAX_WORDS, log=print):
    """Escribe el curso unificado junto a su carpeta y devuelve las rutas de los archivos.

    Un archivo `<curso>.md` si cabe en `max_words`; si no, `<curso> (parte N de M).md`.
    """
    course_dir = Path(course_dir)
    if max_words < 0:
        raise UdemyError("--merge-words no puede ser negativo.")
    manifest = load_manifest(course_dir)
    title, sections = collect(course_dir, manifest, select)
    if not sections:
        raise UdemyError(f"No hay lecciones en Markdown que unificar en {course_dir}.")
    title = title or course_dir.resolve().name
    url = course_url(course_dir)
    parts = split_parts(sections, max_words)
    total_lessons = sum(len(s.lessons) for s in sections)
    paths = _output_names(course_dir, len(parts))
    for n, (path, part) in enumerate(zip(paths, parts), 1):
        text = render_part(title, url, part, n, len(parts), total_lessons)
        try:
            fs_path(path).write_text(text, encoding="utf-8")
        except OSError as exc:
            raise UdemyError(f"No pude escribir {path}: {exc}")
        log(f"  ✓ {path.name}  ({_n(len(text.split()))} palabras)")
    _remove_stale(course_dir, set(paths))
    if len(parts) > 1:
        log(f"  ⚠ El curso supera {_n(max_words)} palabras: se dividió en {len(parts)} partes "
            "(carga todas como fuentes).")
    biggest = max((lesson.words for s in sections for lesson in s.lessons), default=0)
    if max_words and biggest > max_words:
        log(f"  ⚠ Una lección sola tiene {_n(biggest)} palabras, más que el límite.")
    return paths
