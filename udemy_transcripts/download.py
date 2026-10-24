"""Descarga de un curso: transcripciones, artículos y recursos, y escritura de la salida."""

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import resources as res_mod
from .captions import LangSpec, parse_vtt, pick_caption, pick_secondary
from .errors import UdemyError
from .html2md import extract_images, html_to_markdown
from .manifest import caption_signature
from .paragraphs import attach_translation, build_paragraphs
from .render import markdown, txt
from .resources import Outcome, ResourceOptions
from .util import fs_path, safe_name


@dataclass
class Stats:
    saved: int = 0          # lecciones escritas
    up_to_date: int = 0     # lecciones omitidas por --update
    no_captions: int = 0
    empty: int = 0          # artículos sin contenido
    failed: int = 0
    files: int = 0          # recursos descargados
    files_done: int = 0     # recursos que ya estaban
    files_failed: int = 0
    items: list = field(default_factory=list)     # (sección, lección, bloque) del archivo único
    orphans: list = field(default_factory=list)   # archivos antiguos que se conservan
    merged: list = field(default_factory=list)    # archivos del curso unificado (--merge)

    @property
    def ok(self):
        return self.saved + self.up_to_date + self.files + self.files_done

    @property
    def errors(self):
        return self.failed + self.files_failed


def _lecture_rel_path(section, lecture, opts):
    return f"{section.dirname}/{lecture.number} - {safe_name(lecture.title)}.{opts.ext}"


def _caption_signature(caption, caption2=None):
    """Huella de las pistas usadas: cambia si se sube otra versión o se pide otro idioma."""
    return caption_signature(caption) + (f"+{caption_signature(caption2)}" if caption2 else "")


def _fingerprint(outcomes, links, images):
    """Resume qué adjuntos acompañan a la lección: si cambian, hay que reescribirla."""
    if not (outcomes or links or images):
        return ""
    raw = "|".join([f"{o.resource.id}:{o.rel or '-'}" for o in outcomes]
                   + [r.url for r in links] + sorted(images.values()))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _resources_text(opts, outcomes, links, prefix):
    if opts.format == "md":
        return markdown.resources_block(outcomes, links, prefix)
    return txt.resources_text(outcomes, links)


def _render_video(course, section, lecture, caption, cues, opts, single, extra,
                  caption2=None, cues2=None):
    paragraphs = build_paragraphs(cues, opts.pause, opts.max_chars)
    if cues2:
        attach_translation(paragraphs, cues2)
    if opts.format == "md":
        if single:
            return markdown.single_part(course, section, lecture, caption, paragraphs, opts,
                                        extra, caption2)
        return markdown.lecture_document(course, section, lecture, caption, paragraphs, opts,
                                         extra, caption2)
    text = txt.with_resources(txt.paragraphs_to_text(paragraphs, opts), extra)
    if single:
        return txt.single_part(lecture.number, section.dirname, safe_name(lecture.title), text)
    return text + "\n"


def _render_article(course, section, lecture, opts, single, extra, image_map):
    plain = opts.format == "txt"
    body = html_to_markdown(lecture.body, image_map, plain=plain,
                            heading_shift=3 if single else 1)
    if not body.strip():
        return None
    if opts.format == "md":
        if single:
            return markdown.single_article_part(course, section, lecture, body, extra)
        return markdown.article_document(course, section, lecture, body, extra)
    text = txt.with_resources(body.strip(), extra)
    if single:
        return txt.single_part(lecture.number, section.dirname, safe_name(lecture.title), text)
    return text + "\n"


def write_index(course_dir, course, sections, manifest):
    path = Path(course_dir) / "README.md"
    has_resources = fs_path(Path(course_dir) / res_mod.RESOURCES_DIR).is_dir()
    try:
        fs_path(path).write_text(
            markdown.course_index(course, sections, manifest.entries, has_resources),
            encoding="utf-8")
    except OSError as exc:
        raise UdemyError(f"No pude escribir {path}: {exc}")
    return path


def write_links_file(course_dir, course, selected):
    """`recursos/enlaces.md` con los enlaces externos de las lecciones elegidas."""
    entries = [(s, lec, [r for r in lec.resources if r.kind == "link"]) for s, lec in selected]
    entries = [e for e in entries if e[2]]
    if not entries:
        return None
    rel = f"{res_mod.RESOURCES_DIR}/enlaces.md"
    res_mod.write_file(course_dir, rel, markdown.links_file(course, entries).encode("utf-8"))
    return rel


def _prepare_resources(client, selected, manifest, course_dir, res, log, input_fn):
    """Planifica los recursos (tamaños, qué falta) y pide confirmación si es mucho."""
    with_files = [(s, lec) for s, lec in selected if any(r.kind == "file" for r in lec.resources)]
    if not with_files:
        return res_mod.Plan(), False
    log("• Revisando recursos…")
    plan = res_mod.plan_resources(client, with_files, manifest, course_dir, res.types,
                                  res.max_size, log)
    for line in res_mod.summarize(plan, res.max_size):
        log(line)
    go = res_mod.confirm(plan, res.assume_yes, input_fn=input_fn, log=log)
    if not go:
        log("  Recursos omitidos por tu respuesta.")
    return plan, go


def download_course(client, course, sections, langs, opts, course_dir=None, single=False,
                    update=False, manifest=None, log=print, pause=0.15, select=None,
                    res: Optional[ResourceOptions] = None, input_fn=input):
    """Baja y guarda las lecciones (vídeos y artículos) y, si se pide, sus recursos.

    En modo normal escribe un archivo por lección bajo `course_dir`, apunta cada
    una en `manifest` (guardado tras cada lección, así una interrupción se puede
    reanudar con `update=True`) y regenera `README.md` al terminar. Con `single`
    solo reúne los bloques en `Stats.items`. `select(sección, lección)` limita
    qué lecciones se procesan (rangos `--sections`/`--lectures`).
    """
    res = res or ResourceOptions()
    spec = langs if isinstance(langs, LangSpec) else LangSpec(list(langs))
    stats = Stats()
    lessons = [(s, lec) for s in sections for lec in s.lectures
               if (lec.is_video or lec.is_article) and (select is None or select(s, lec))]
    if res.only:
        lessons = [(s, lec) for s, lec in lessons if lec.resources]
    total = len(lessons)
    index = not single and not res.only and opts.format == "md"
    plan, resources_on = res_mod.Plan(), False
    if res.enabled and manifest is not None:
        plan, resources_on = _prepare_resources(client, lessons, manifest, course_dir, res,
                                                log, input_fn)
    planned = {id(p.resource): p for p in plan.items}
    rel_of = {}                      # id(recurso) → ruta local (si el archivo está en disco)
    try:
        for n, (section, lec) in enumerate(lessons, 1):
            label = f"[{n}/{total}] {section.title} › {lec.number} - {lec.title}"
            files = [r for r in lec.resources if r.kind == "file"]
            links = [r for r in lec.resources if r.kind == "link"]
            paths = res_mod.lecture_file_paths(section, lec)

            # 1) recursos de la lección
            for r in files:
                rel = paths[id(r)]
                item = planned.get(id(r))
                if item is not None and item.status == "done":
                    stats.files_done += 1
                elif item is not None and item.status == "new" and resources_on:
                    if res_mod.download_planned(client, item, manifest, course_dir,
                                                res.max_size, log):
                        stats.files += 1
                        time.sleep(pause)
                    else:
                        stats.files_failed += 1
                        continue
                elif not (manifest is not None and r.id is not None
                          and manifest.resource_done(r.id, rel, course_dir)):
                    continue
                rel_of[id(r)] = rel
            outcomes = [Outcome(r, rel_of.get(id(r)), paths[id(r)].rsplit("/", 1)[-1])
                        for r in files]
            if res.only:
                continue

            # 2) imágenes del artículo (con --resources)
            images = {}
            if lec.is_article and resources_on:
                images = res_mod.download_images(client, section, lec, extract_images(lec.body),
                                                 course_dir, res.max_size, log)

            # 3) ¿sigue vigente? (--update)
            rel = _lecture_rel_path(section, lec, opts)
            if lec.is_article:
                caption, caption2, preferred = None, None, True
                signature = "article:" + hashlib.sha1(lec.body.encode("utf-8")).hexdigest()[:16]
                if not lec.body.strip():
                    log(f"  – {label}: artículo vacío")
                    stats.empty += 1
                    continue
            else:
                caption, preferred = pick_caption(lec.captions, spec.prefs)
                if not caption:
                    log(f"  – {label}: sin subtítulos")
                    stats.no_captions += 1
                    continue
                caption2 = pick_secondary(lec.captions, spec.secondary, caption) \
                    if spec.secondary else None
                signature = _caption_signature(caption, caption2)
            fp = _fingerprint(outcomes, links, images)
            render_sig = opts.signature + (f"|res={fp}" if fp else "")
            if (not single and update and manifest.up_to_date(
                    lec, section, signature, rel, render_sig, course_dir)):
                log(f"  = {label}  (sin cambios)")
                stats.up_to_date += 1
                continue

            # 4) contenido y render
            prefix = "../" if not single else f"{safe_name(course.title)}/"
            extra = _resources_text(opts, outcomes, links, prefix)
            if lec.is_article:
                image_map = {src: res_mod.link_path(r_, prefix) for src, r_ in images.items()}
                block, vtt_hash = _render_article(course, section, lec, opts, single, extra,
                                                  image_map), ""
                if block is None:
                    log(f"  – {label}: artículo vacío")
                    stats.empty += 1
                    continue
                locale, note = "artículo", ""
            else:
                result = client.download_text(caption["url"], "el subtítulo")
                if not result.ok:
                    hint = " (¿URL caducada?)" if result.status in (401, 403) else ""
                    log(f"  ✗ {label}: no se pudo bajar el subtítulo "
                        f"(HTTP {result.status}){hint}")
                    stats.failed += 1
                    continue
                cues2 = None
                if caption2:
                    result2 = client.download_text(caption2["url"], "el subtítulo secundario")
                    if result2.ok:
                        cues2 = parse_vtt(result2.text)
                    else:
                        log(f"  ⚠ {label}: no se pudo bajar la pista {caption2.get('locale_id')} "
                            f"(HTTP {result2.status}); solo {caption.get('locale_id')}")
                        caption2 = None
                block = _render_video(course, section, lec, caption, parse_vtt(result.text),
                                      opts, single, extra, caption2, cues2)
                vtt_hash = hashlib.sha256(result.text.encode("utf-8")).hexdigest()
                locale = caption.get("locale_id")
                note = "" if preferred else f" — usando {locale}, no hay {spec.prefs[0]}"
                if caption2:
                    locale += f" + {caption2.get('locale_id')}"
                elif spec.secondary:
                    note += f" — sin pista {spec.secondary}"

            # 5) escribir y apuntar
            if single:
                stats.items.append((section, lec, block))
            else:
                previous = manifest.get(lec.id) if lec.id else None
                target = fs_path(Path(course_dir) / rel)
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(block, encoding="utf-8")
                except OSError as exc:
                    raise UdemyError(f"No pude escribir {Path(course_dir) / rel}: {exc}")
                if lec.id:
                    manifest.set(lec.id, {
                        "file": rel, "kind": "article" if lec.is_article else "video",
                        "locale": caption.get("locale_id") if lec.is_video else "",
                        "locale2": caption2.get("locale_id") if caption2 else "",
                        "source": (caption or {}).get("source") or "",
                        "caption": _caption_signature(caption, caption2) if caption else signature,
                        "render": render_sig, "vtt_sha256": vtt_hash,
                        "title": lec.title, "section": section.title,
                        "duration": lec.duration})
                    manifest.save()
                if previous and previous.get("file") != rel \
                        and fs_path(Path(course_dir) / previous["file"]).is_file():
                    stats.orphans.append(previous["file"])
                    note += f" — se conserva el archivo anterior {previous['file']}"
            log(f"  ✓ {label}  ({locale}){note}")
            stats.saved += 1
            time.sleep(pause)
    finally:
        if resources_on and manifest is not None:
            write_links_file(course_dir, course, lessons)
        if index and manifest is not None:
            write_index(course_dir, course, sections, manifest)
    return stats
