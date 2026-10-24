"""Salida en Markdown: lecciones con cabecera YAML, índice del curso y archivo único."""

import json
import re
from urllib.parse import quote

from ..paragraphs import marked
from .common import fmt_time

_SPECIAL = re.compile(r"([\\`*_\[\]<>$])")


def md_escape(text):
    """Escapa lo que Markdown interpretaría (el texto de una transcripción es literal)."""
    text = _SPECIAL.sub(r"\\\1", text)
    text = re.sub(r"^(\d+)([.)])", r"\1\\\2", text)   # «3. algo» no es una lista
    return re.sub(r"^([#+-])", r"\\\1", text)


def _yaml(value):
    return json.dumps(value, ensure_ascii=False)       # un escalar entre comillas es YAML válido


def _link_path(rel):
    return "/".join(quote(part) for part in rel.split("/"))


def paragraphs_to_markdown(paragraphs, course, lecture, opts):
    pairs = marked(paragraphs, opts.ts_every) if opts.timestamps \
        else ((p, False) for p in paragraphs)
    blocks = []
    for paragraph, show in pairs:
        text = md_escape(paragraph.text.strip())
        if show:
            stamp = fmt_time(paragraph.start)
            url = course.lecture_url(lecture.id, paragraph.start)
            text = f"[{stamp}]({url}) {text}" if url else f"`[{stamp}]` {text}"
        blocks.append(text)
    return "\n\n".join(blocks)


def _meta_line(course, lecture, caption, with_section=None):
    bits = [with_section] if with_section else []
    if lecture.duration:
        bits.append(fmt_time(lecture.duration))
    if caption and caption.get("locale_id"):
        auto = " (automático)" if caption.get("source") == "auto" else ""
        bits.append(f"{caption['locale_id']}{auto}")
    url = course.lecture_url(lecture.id)
    if url:
        bits.append(f"[Abrir en Udemy]({url})")
    return "> " + " · ".join(bits) if bits else ""


def lecture_document(course, section, lecture, caption, paragraphs, opts):
    """Archivo `.md` de una lección."""
    fm = ["---",
          f"curso: {_yaml(course.title)}",
          f"seccion: {_yaml(section.title)}",
          f"leccion: {_yaml(lecture.title)}",
          f"numero: {lecture.index if isinstance(lecture.index, int) else 0}"]
    url = course.lecture_url(lecture.id)
    if url:
        fm.append(f"url: {_yaml(url)}")
    if lecture.duration:
        fm.append(f"duracion: {_yaml(fmt_time(lecture.duration))}")
    fm.append(f"idioma: {_yaml((caption or {}).get('locale_id') or '')}")
    fm.append(f"subtitulo_automatico: {'true' if (caption or {}).get('source') == 'auto' else 'false'}")
    fm.append("---")
    parts = ["\n".join(fm), f"# {md_escape(lecture.title)}"]
    meta = _meta_line(course, lecture, caption, with_section=md_escape(section.dirname))
    if meta:
        parts.append(meta)
    parts.append(paragraphs_to_markdown(paragraphs, course, lecture, opts))
    return "\n\n".join(parts) + "\n"


def course_index(course, sections, entries):
    """`README.md` del curso. `entries`: id de lección (str) → entrada del manifest."""
    videos = [lec for s in sections for lec in s.lectures if lec.is_video]
    done = [lec for lec in videos if str(lec.id) in entries]
    total = sum(lec.duration or 0 for lec in videos)
    lines = [f"# {md_escape(course.title)}", ""]
    if course.url:
        lines += [f"[Abrir el curso en Udemy]({course.url})", ""]
    lines.append(f"{len(done)} de {len(videos)} lecciones con transcripción"
                 + (f" · duración total {fmt_time(total)}" if total else ""))
    for section in sections:
        lectures = [lec for lec in section.lectures if lec.is_video]
        if not lectures:
            continue
        lines += ["", f"## {md_escape(section.dirname)}", ""]
        for lec in lectures:
            label = f"{lec.number} - {lec.title}"
            entry = entries.get(str(lec.id))
            bits = [fmt_time(lec.duration)] if lec.duration else []
            if entry:
                if entry.get("locale"):
                    bits.append(entry["locale"] + (" (automático)"
                                                   if entry.get("source") == "auto" else ""))
                lines.append(f"- [{md_escape(label)}]({_link_path(entry['file'])})"
                             + (" — " + " · ".join(bits) if bits else ""))
            else:
                usable = any(c.get("url") for c in lec.captions)
                bits.append("pendiente de descargar" if usable else "sin subtítulos")
                lines.append(f"- {md_escape(label)} — " + " · ".join(bits))
    return "\n".join(lines) + "\n"


def _lecture_anchor(lecture):
    return f"lec-{lecture.id or lecture.number}"


def single_part(course, section, lecture, caption, paragraphs, opts):
    """Bloque de una lección dentro del archivo único."""
    meta = _meta_line(course, lecture, caption)
    return "\n\n".join(filter(None, [
        f'<a id="{_lecture_anchor(lecture)}"></a>',
        f"### {lecture.number} - {md_escape(lecture.title)}",
        meta,
        paragraphs_to_markdown(paragraphs, course, lecture, opts)]))


def single_document(course, items):
    """Archivo único con tabla de contenidos. `items`: [(sección, lección, bloque)]."""
    order, by_section = [], {}
    for section, lecture, block in items:
        if section.index not in by_section:
            order.append(section)
            by_section[section.index] = []
        by_section[section.index].append((lecture, block))
    lines = [f"# {md_escape(course.title)}", ""]
    if course.url:
        lines += [f"[Abrir el curso en Udemy]({course.url})", ""]
    lines += ["## Contenido", ""]
    for section in order:
        lines.append(f"- [{md_escape(section.dirname)}](#sec-{section.index})")
        for lecture, _ in by_section[section.index]:
            dur = f" ({fmt_time(lecture.duration)})" if lecture.duration else ""
            lines.append(f"  - [{md_escape(lecture.number + ' - ' + lecture.title)}]"
                         f"(#{_lecture_anchor(lecture)}){dur}")
    out = ["\n".join(lines)]
    for section in order:
        out.append(f'<a id="sec-{section.index}"></a>\n\n## {md_escape(section.dirname)}')
        out.extend(block for _, block in by_section[section.index])
    return "\n\n".join(out) + "\n"
