"""Línea de comandos: argumentos y orquestación.

    udemy <url|slug|id> [--txt] [--lang es,en] [--out DIR] [--width N]
    udemy --list
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .captions import parse_vtt, pick_caption
from .client import Client, ensure_login
from .courses import course_title, list_courses, resolve_course_id
from .curriculum import fetch_curriculum
from .errors import UdemyError
from .portal import Portal, portal_from_ref
from .render.txt import cues_to_text, single_file, single_part
from .util import safe_name

PROFILE_DIR = Path.home() / ".cache" / "udemy-transcripts-profile"
DEFAULT_OUT = Path.home() / "Udemy-Transcripts"


@dataclass
class Stats:
    saved: int = 0
    no_captions: int = 0
    failed: int = 0
    parts: list = field(default_factory=list)   # bloques para el archivo único


def build_parser():
    ap = argparse.ArgumentParser(prog="udemy",
                                 description="Transcripciones de un curso de Udemy.")
    ap.add_argument("course", nargs="?", help="URL del curso, slug o course_id numérico")
    ap.add_argument("--list", action="store_true", dest="do_list",
                    help="lista tus cursos suscritos y termina")
    ap.add_argument("--token", default=os.environ.get("UDEMY_TOKEN"),
                    help="access_token de la cookie (evita el login manual; o env UDEMY_TOKEN)")
    ap.add_argument("--lang", default="es,en",
                    help="idiomas del subtítulo por orden de preferencia (default es,en)")
    ap.add_argument("--out", default=None,
                    help="carpeta base (default: $UDEMY_OUT o ~/Udemy-Transcripts)")
    ap.add_argument("--txt", action="store_true",
                    help="todo el curso en UN solo .txt (en vez de uno por video)")
    ap.add_argument("--width", type=int, default=100,
                    help="ancho de línea del texto; 0 = sin ajustar (default 100)")
    ap.add_argument("--headless", action="store_true",
                    help="(NO recomendado: Udemy bloquea el modo headless con Cloudflare)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return ap


def parse_langs(value):
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def download_transcripts(client, sections, langs, course_dir=None, width=100,
                         single=False, log=print, pause=0.15):
    """Baja y guarda el subtítulo de cada lección de vídeo."""
    videos = [(s, lec) for s in sections for lec in s.lectures if lec.is_video]
    total, stats = len(videos), Stats()
    for n, (section, lec) in enumerate(videos, 1):
        label = f"[{n}/{total}] {section.title} › {lec.number} - {lec.title}"
        caption, preferred = pick_caption(lec.captions, langs)
        if not caption:
            log(f"  – {label}: sin subtítulos")
            stats.no_captions += 1
            continue
        result = client.download_text(caption["url"], "el subtítulo")
        if not result.ok:
            hint = " (¿URL caducada?)" if result.status in (401, 403) else ""
            log(f"  ✗ {label}: no se pudo bajar el subtítulo (HTTP {result.status}){hint}")
            stats.failed += 1
            continue
        text = cues_to_text(parse_vtt(result.text), width)
        locale = caption.get("locale_id")
        note = "" if preferred else f" — usando {locale}, no hay {langs[0]}"
        if single:
            stats.parts.append(single_part(lec.number, section.title,
                                           safe_name(lec.title), text))
        else:
            folder = course_dir / section.dirname
            folder.mkdir(parents=True, exist_ok=True)
            name = f"{lec.number} - {safe_name(lec.title)}.txt"
            (folder / name).write_text(text + "\n", encoding="utf-8")
        log(f"  ✓ {label}  ({locale}){note}")
        stats.saved += 1
        time.sleep(pause)
    return stats


def _launch(pw, args):
    context = pw.chromium.launch_persistent_context(
        str(PROFILE_DIR), headless=args.headless,
        viewport={"width": 1280, "height": 800},
        args=["--disable-blink-features=AutomationControlled"])
    if args.token:
        context.add_cookies([{
            "name": "access_token", "value": args.token,
            "domain": ".udemy.com", "path": "/", "secure": True,
        }])
    return context


def _import_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise UdemyError("Falta Playwright. Instálalo con:\n"
                         "    pip3 install playwright\n"
                         "    python3 -m playwright install chromium")
    return sync_playwright


def run(args):
    if args.headless:
        print("⚠ Aviso: Udemy suele bloquear el modo headless (Cloudflare). "
              "Si falla, ejecútalo sin --headless.")
    langs = parse_langs(args.lang)
    portal = portal_from_ref(args.course) if args.course else Portal()

    with _import_playwright()() as pw:
        context = _launch(pw, args)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            client = Client(context, page, portal)

            print("• Comprobando sesión…")
            ensure_login(client)

            if args.do_list:
                rows = list_courses(client)
                print(f"\nTienes {len(rows)} cursos:\n")
                for c in rows:
                    print(f"  [{c['id']}] {c['title']}")
                print("\nDescarga uno con:  udemy <id-o-URL>")
                return 0

            print("• Resolviendo curso…")
            course_id = resolve_course_id(client, args.course)
            title = course_title(client, course_id)
            print(f"  → {title} (id {course_id})")

            base = Path(args.out) if args.out else Path(
                os.environ.get("UDEMY_OUT") or DEFAULT_OUT)
            base.mkdir(parents=True, exist_ok=True)
            course_dir = base / safe_name(title)
            if not args.txt:
                course_dir.mkdir(parents=True, exist_ok=True)

            print("• Leyendo temario…")
            sections = fetch_curriculum(client, course_id)
            if not any(lec.is_video for s in sections for lec in s.lectures):
                raise UdemyError("El curso no tiene lecciones de vídeo.")

            stats = download_transcripts(client, sections, langs, course_dir,
                                         args.width, args.txt)
        finally:
            context.close()

    print(f"\n{'✓' if stats.saved else '✗'} Listo: {stats.saved} transcripciones, "
          f"{stats.no_captions} sin subtítulos, {stats.failed} con error.")
    if args.txt and stats.saved:
        target = base / f"{safe_name(title)}.txt"
        target.write_text(single_file(title, stats.parts), encoding="utf-8")
        print(f"  Archivo: {target}")
    elif stats.saved:
        print(f"  Carpeta: {course_dir}")
    return 0 if stats.saved else 1


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")   # consolas que no son UTF-8
        except (AttributeError, ValueError):
            pass
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.do_list and not args.course:
        ap.error("indica la URL/ID del curso, o usa --list para ver tus cursos.")
    try:
        return run(args)
    except UdemyError as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n✗ Interrumpido.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
