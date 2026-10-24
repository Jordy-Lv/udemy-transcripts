"""Descarga de las transcripciones de un curso y escritura de la salida."""

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from .captions import parse_vtt, pick_caption
from .manifest import caption_signature
from .paragraphs import build_paragraphs
from .render import markdown, txt
from .errors import UdemyError
from .util import fs_path, safe_name


@dataclass
class Stats:
    saved: int = 0
    up_to_date: int = 0
    no_captions: int = 0
    failed: int = 0
    items: list = field(default_factory=list)     # (sección, lección, bloque) del archivo único
    orphans: list = field(default_factory=list)   # archivos antiguos que se conservan

    @property
    def ok(self):
        return self.saved + self.up_to_date


def _lecture_rel_path(section, lecture, opts):
    return f"{section.dirname}/{lecture.number} - {safe_name(lecture.title)}.{opts.ext}"


def _render(course, section, lecture, caption, cues, opts, single):
    paragraphs = build_paragraphs(cues, opts.pause, opts.max_chars)
    if opts.format == "md":
        if single:
            return markdown.single_part(course, section, lecture, caption, paragraphs, opts)
        return markdown.lecture_document(course, section, lecture, caption, paragraphs, opts)
    text = txt.paragraphs_to_text(paragraphs, opts)
    if single:
        return txt.single_part(lecture.number, section.dirname, safe_name(lecture.title), text)
    return text + "\n"


def write_index(course_dir, course, sections, manifest):
    path = Path(course_dir) / "README.md"
    try:
        fs_path(path).write_text(markdown.course_index(course, sections, manifest.entries),
                                 encoding="utf-8")
    except OSError as exc:
        raise UdemyError(f"No pude escribir {path}: {exc}")
    return path


def download_course(client, course, sections, langs, opts, course_dir=None, single=False,
                    update=False, manifest=None, log=print, pause=0.15):
    """Baja y guarda el subtítulo de cada lección de vídeo.

    En modo normal escribe un archivo por lección bajo `course_dir`, apunta cada
    una en `manifest` (guardado tras cada lección, así una interrupción se puede
    reanudar con `update=True`) y regenera `README.md` al terminar. Con `single`
    solo reúne los bloques en `Stats.items`.
    """
    videos = [(s, lec) for s in sections for lec in s.lectures if lec.is_video]
    total, stats = len(videos), Stats()
    index = not single and opts.format == "md"
    try:
        for n, (section, lec) in enumerate(videos, 1):
            label = f"[{n}/{total}] {section.title} › {lec.number} - {lec.title}"
            caption, preferred = pick_caption(lec.captions, langs)
            if not caption:
                log(f"  – {label}: sin subtítulos")
                stats.no_captions += 1
                continue
            rel = _lecture_rel_path(section, lec, opts)
            if (not single and update and manifest.up_to_date(
                    lec, section, caption, rel, opts.signature, course_dir)):
                log(f"  = {label}  (sin cambios)")
                stats.up_to_date += 1
                continue
            result = client.download_text(caption["url"], "el subtítulo")
            if not result.ok:
                hint = " (¿URL caducada?)" if result.status in (401, 403) else ""
                log(f"  ✗ {label}: no se pudo bajar el subtítulo "
                    f"(HTTP {result.status}){hint}")
                stats.failed += 1
                continue
            block = _render(course, section, lec, caption, parse_vtt(result.text), opts, single)
            locale = caption.get("locale_id")
            note = "" if preferred else f" — usando {locale}, no hay {langs[0]}"
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
                        "file": rel, "locale": locale, "source": caption.get("source") or "",
                        "caption": caption_signature(caption), "render": opts.signature,
                        "vtt_sha256": hashlib.sha256(result.text.encode("utf-8")).hexdigest(),
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
        if index and manifest is not None:
            write_index(course_dir, course, sections, manifest)
    return stats
