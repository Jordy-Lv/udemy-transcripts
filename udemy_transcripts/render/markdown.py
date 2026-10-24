"""Salida en Markdown: lecciones con cabecera YAML, índice del curso y archivo único."""

import json

from ..paragraphs import marked
from ..resources import link_path
from .common import fmt_time
from .mdtext import escape_inline, md_escape


def _yaml(value):
    return json.dumps(value, ensure_ascii=False)       # un escalar entre comillas es YAML válido


def reading_time(seconds):
    """«≈ 2 min» a partir del tiempo de lectura estimado."""
    return f"≈ {max(1, round(seconds / 60))} min" if seconds else ""


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
        if paragraph.other:
            text += f"\n\n> **{opts.second_lang or '→'}** · {escape_inline(paragraph.other.strip())}"
        blocks.append(text)
    return "\n\n".join(blocks)


def resources_block(outcomes, links, prefix=""):
    """Sección «Recursos» de una lección. Vacía si la lección no tiene adjuntos.

    `outcomes`: [Outcome] de los archivos; `links`: [Resource] de tipo enlace;
    `prefix`: ruta para llegar desde el documento a la carpeta del curso.
    """
    lines = []
    for outcome in outcomes:
        name = outcome.name or outcome.resource.filename or outcome.resource.title
        if outcome.rel:
            lines.append(f"- [{md_escape(name)}]({link_path(outcome.rel, prefix)})")
        else:
            lines.append(f"- {md_escape(name)} — sin descargar (usa --resources)")
    for res in links:
        lines.append(f"- [{md_escape(res.title or res.url)}]({res.url})")
    return "## Recursos\n\n" + "\n".join(lines) if lines else ""


def _locales(caption, caption2):
    """«es_LA (automático) + en_US» para la línea de metadatos."""
    def one(c):
        return c["locale_id"] + (" (automático)" if c.get("source") == "auto" else "")
    names = [one(c) for c in (caption, caption2) if c and c.get("locale_id")]
    return " + ".join(names)


def _meta_line(course, lecture, caption, with_section=None, caption2=None):
    bits = [with_section] if with_section else []
    if lecture.is_article:
        if lecture.duration:
            bits.append(f"lectura {reading_time(lecture.duration)}")
    elif lecture.duration:
        bits.append(fmt_time(lecture.duration))
    if _locales(caption, caption2):
        bits.append(_locales(caption, caption2))
    url = course.lecture_url(lecture.id)
    if url:
        bits.append(f"[Abrir en Udemy]({url})")
    return "> " + " · ".join(bits) if bits else ""


def _front_matter(course, section, lecture, caption, caption2=None):
    fm = ["---",
          f"curso: {_yaml(course.title)}",
          f"seccion: {_yaml(section.title)}",
          f"leccion: {_yaml(lecture.title)}",
          f"numero: {lecture.index if isinstance(lecture.index, int) else 0}",
          f"tipo: {_yaml('articulo' if lecture.is_article else 'video')}"]
    url = course.lecture_url(lecture.id)
    if url:
        fm.append(f"url: {_yaml(url)}")
    if lecture.is_article:
        if lecture.duration:
            fm.append(f"lectura: {_yaml(reading_time(lecture.duration))}")
    else:
        if lecture.duration:
            fm.append(f"duracion: {_yaml(fmt_time(lecture.duration))}")
        fm.append(f"idioma: {_yaml((caption or {}).get('locale_id') or '')}")
        if caption2:
            fm.append(f"idioma_secundario: {_yaml(caption2.get('locale_id') or '')}")
        fm.append("subtitulo_automatico: "
                  f"{'true' if (caption or {}).get('source') == 'auto' else 'false'}")
    fm.append("---")
    return "\n".join(fm)


def lecture_document(course, section, lecture, caption, paragraphs, opts, resources_md="",
                     caption2=None):
    """Archivo `.md` de una lección de vídeo."""
    parts = [_front_matter(course, section, lecture, caption, caption2),
             f"# {md_escape(lecture.title)}"]
    meta = _meta_line(course, lecture, caption, with_section=md_escape(section.dirname),
                      caption2=caption2)
    parts += [meta, paragraphs_to_markdown(paragraphs, course, lecture, opts), resources_md]
    return "\n\n".join(p for p in parts if p) + "\n"


def article_document(course, section, lecture, body_md, resources_md=""):
    """Archivo `.md` de un artículo (`body_md` ya convertido desde HTML)."""
    parts = [_front_matter(course, section, lecture, None), f"# {md_escape(lecture.title)}",
             _meta_line(course, lecture, None, with_section=md_escape(section.dirname)),
             body_md.strip(), resources_md]
    return "\n\n".join(p for p in parts if p) + "\n"


def course_index(course, sections, entries, has_resources=False):
    """`README.md` del curso. `entries`: id de lección (str) → entrada del manifest."""
    lessons = [lec for s in sections for lec in s.lectures if lec.is_video or lec.is_article]
    done = [lec for lec in lessons if str(lec.id) in entries]
    video_time = sum(lec.duration or 0 for lec in lessons if lec.is_video)
    lines = [f"# {md_escape(course.title)}", ""]
    if course.url:
        lines += [f"[Abrir el curso en Udemy]({course.url})", ""]
    lines.append(f"{len(done)} de {len(lessons)} lecciones descargadas"
                 + (f" · {fmt_time(video_time)} de vídeo" if video_time else ""))
    if has_resources:
        lines += ["", "Recursos: carpeta [recursos/](recursos/) · "
                      "[enlaces externos](recursos/enlaces.md)"]
    for section in sections:
        lectures = [lec for lec in section.lectures if lec.is_video or lec.is_article]
        if not lectures:
            continue
        lines += ["", f"## {md_escape(section.dirname)}", ""]
        for lec in lectures:
            label = f"{lec.number} - {lec.title}"
            entry = entries.get(str(lec.id))
            if lec.is_article:
                bits = ["artículo"] + ([reading_time(lec.duration)] if lec.duration else [])
            else:
                bits = [fmt_time(lec.duration)] if lec.duration else []
            if entry:
                if entry.get("locale") and lec.is_video:
                    bits.append(entry["locale"] + (" (automático)"
                                                   if entry.get("source") == "auto" else "")
                                + (f" + {entry['locale2']}" if entry.get("locale2") else ""))
                lines.append(f"- [{md_escape(label)}]({link_path(entry['file'])})"
                             + (" — " + " · ".join(bits) if bits else ""))
            else:
                if lec.is_article:
                    bits.append("pendiente de descargar" if lec.body.strip() else "vacío")
                else:
                    usable = any(c.get("url") for c in lec.captions)
                    bits.append("pendiente de descargar" if usable else "sin subtítulos")
                lines.append(f"- {md_escape(label)} — " + " · ".join(bits))
    return "\n".join(lines) + "\n"


def links_file(course, entries):
    """`recursos/enlaces.md`: los enlaces externos de todo el curso.

    `entries`: [(sección, lección, [Resource enlace])] con al menos un enlace.
    """
    lines = [f"# Enlaces de {md_escape(course.title)}", ""]
    last = None
    for section, lecture, links in entries:
        if section.index != last:
            lines += [f"## {md_escape(section.dirname)}", ""]
            last = section.index
        lines.append(f"### {md_escape(lecture.number + ' - ' + lecture.title)}")
        lines.append("")
        lines += [f"- [{md_escape(r.title or r.url)}]({r.url})" for r in links]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _lecture_anchor(lecture):
    return f"lec-{lecture.id or lecture.number}"


def single_part(course, section, lecture, caption, paragraphs, opts, resources_md="",
                caption2=None):
    """Bloque de una lección de vídeo dentro del archivo único."""
    return "\n\n".join(filter(None, [
        f'<a id="{_lecture_anchor(lecture)}"></a>',
        f"### {lecture.number} - {md_escape(lecture.title)}",
        _meta_line(course, lecture, caption, caption2=caption2),
        paragraphs_to_markdown(paragraphs, course, lecture, opts),
        resources_md.replace("## Recursos", "#### Recursos", 1) if resources_md else ""]))


def single_article_part(course, section, lecture, body_md, resources_md=""):
    """Bloque de un artículo dentro del archivo único."""
    return "\n\n".join(filter(None, [
        f'<a id="{_lecture_anchor(lecture)}"></a>',
        f"### {lecture.number} - {md_escape(lecture.title)}",
        _meta_line(course, lecture, None),
        body_md.strip(),
        resources_md.replace("## Recursos", "#### Recursos", 1) if resources_md else ""]))


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
            dur = f" ({fmt_time(lecture.duration)})" if lecture.duration and not lecture.is_article \
                else ""
            lines.append(f"  - [{md_escape(lecture.number + ' - ' + lecture.title)}]"
                         f"(#{_lecture_anchor(lecture)}){dur}")
    out = ["\n".join(lines)]
    for section in order:
        out.append(f'<a id="sec-{section.index}"></a>\n\n## {md_escape(section.dirname)}')
        out.extend(block for _, block in by_section[section.index])
    return "\n\n".join(out) + "\n"
