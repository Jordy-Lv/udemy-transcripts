"""Línea de comandos: argumentos y orquestación.

    udemy <url|slug|id> [--format md|txt] [--single] [--update] [--lang es,en] [--out DIR]
    udemy --list
"""

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .client import Client, ensure_login
from .courses import course_info, list_courses, resolve_course_id
from .curriculum import fetch_curriculum
from .download import download_course
from .errors import UdemyError
from .manifest import MANIFEST_NAME, Manifest
from .portal import choose_portal, host_from_ref, token_cookie
from .render import markdown, txt
from .render.common import RenderOptions
from .util import fs_path, safe_name

PROFILE_DIR = Path.home() / ".cache" / "udemy-transcripts-profile"
DEFAULT_OUT = Path.home() / "Udemy-Transcripts"


def build_parser():
    ap = argparse.ArgumentParser(prog="udemy",
                                 description="Transcripciones de un curso de Udemy.")
    ap.add_argument("course", nargs="?", help="URL del curso, slug o course_id numérico")
    ap.add_argument("--list", action="store_true", dest="do_list",
                    help="lista tus cursos suscritos y termina")
    ap.add_argument("--business", metavar="ORG", default=os.environ.get("UDEMY_BUSINESS"),
                    help="organización de Udemy Business (p. ej. seti para seti.udemy.com) "
                         "cuando pasas un id/slug o usas --list (o env UDEMY_BUSINESS). "
                         "Una URL ya indica su portal")
    ap.add_argument("--token", default=os.environ.get("UDEMY_TOKEN"),
                    help="access_token de la cookie (evita el login manual; o env UDEMY_TOKEN)")
    ap.add_argument("--lang", default="es,en",
                    help="idiomas del subtítulo por orden de preferencia (default es,en)")
    ap.add_argument("--out", default=None,
                    help="carpeta base (default: $UDEMY_OUT o ~/Udemy-Transcripts)")
    ap.add_argument("--format", choices=("md", "txt"), default="md",
                    help="formato de salida: md (Markdown, default) o txt")
    ap.add_argument("--single", action="store_true",
                    help="todo el curso en UN solo archivo (con tabla de contenidos)")
    ap.add_argument("--txt", action="store_true",
                    help="el modo clásico: equivale a --single --format txt")
    ap.add_argument("--update", action="store_true",
                    help="solo descarga lecciones nuevas o con subtítulo cambiado y "
                         "reanuda una descarga cortada (usa .udemy-transcripts.json)")
    ap.add_argument("--no-timestamps", action="store_true",
                    help="sin marcas de tiempo al inicio de los párrafos")
    ap.add_argument("--ts-every", type=int, default=0, metavar="SEG",
                    help="una marca de tiempo como mucho cada SEG segundos "
                         "(default 0: una por párrafo)")
    ap.add_argument("--width", type=int, default=100,
                    help="ancho de línea del texto (solo --format txt); 0 = sin ajustar "
                         "(default 100)")
    ap.add_argument("--headless", action="store_true",
                    help="(NO recomendado: Udemy bloquea el modo headless con Cloudflare)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return ap


def parse_langs(value):
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def options_from_args(args):
    """Opciones de render y modo (archivo único) a partir de los argumentos."""
    fmt, single = args.format, args.single
    if args.txt:                      # alias del modo de siempre
        fmt, single = "txt", True
    if args.width < 0 or args.ts_every < 0:
        raise UdemyError("--width y --ts-every no pueden ser negativos.")
    return RenderOptions(format=fmt, timestamps=not args.no_timestamps,
                         ts_every=args.ts_every, width=args.width), single


def _launch(pw, args, portal):
    context = pw.chromium.launch_persistent_context(
        str(PROFILE_DIR), headless=args.headless,
        viewport={"width": 1280, "height": 800},
        args=["--disable-blink-features=AutomationControlled"])
    if args.token:
        context.add_cookies([token_cookie(args.token, portal)])
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
    opts, single = options_from_args(args)
    if args.headless:
        print("⚠ Aviso: Udemy suele bloquear el modo headless (Cloudflare). "
              "Si falla, ejecútalo sin --headless.")
    if args.update and single and not args.do_list:
        print("⚠ Aviso: --update no aplica a --single/--txt; se regenera el archivo completo.")
    langs = parse_langs(args.lang)
    portal = choose_portal(args.course, args.business)
    if args.business and host_from_ref(args.course) and             host_from_ref(args.course) != choose_portal(None, args.business).host:
        print(f"⚠ Aviso: la URL apunta a {portal.host}; se ignora --business "
              f"{args.business}.")
    if portal.is_business:
        print(f"• Portal: Udemy Business ({portal.host})")

    with _import_playwright()() as pw:
        context = _launch(pw, args, portal)
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
            course = course_info(client, course_id)
            print(f"  → {course.title} (id {course_id})")

            base = Path(args.out) if args.out else Path(
                os.environ.get("UDEMY_OUT") or DEFAULT_OUT)
            base.mkdir(parents=True, exist_ok=True)
            course_dir = base / safe_name(course.title)

            print("• Leyendo temario…")
            sections = fetch_curriculum(client, course_id)
            if not any(lec.is_video for s in sections for lec in s.lectures):
                raise UdemyError("El curso no tiene lecciones de vídeo.")

            manifest = None
            if not single:
                course_dir.mkdir(parents=True, exist_ok=True)
                manifest = Manifest.load(course_dir / MANIFEST_NAME, course_id)
            stats = download_course(client, course, sections, langs, opts,
                                    course_dir, single, args.update, manifest)
        finally:
            context.close()

    kept = f", {stats.up_to_date} sin cambios" if args.update else ""
    print(f"\n{'✓' if stats.ok else '✗'} Listo: {stats.saved} transcripciones{kept}, "
          f"{stats.no_captions} sin subtítulos, {stats.failed} con error.")
    if stats.orphans:
        print(f"  ⚠ {len(stats.orphans)} archivo(s) antiguo(s) se conservan "
              "(la lección cambió de nombre o de sección).")
    if single and stats.saved:
        target = base / f"{safe_name(course.title)}.{opts.ext}"
        render = markdown if opts.format == "md" else txt
        try:
            fs_path(target).write_text(render.single_document(course, stats.items),
                                       encoding="utf-8")
        except OSError as exc:
            raise UdemyError(f"No pude escribir {target}: {exc}")
        print(f"  Archivo: {target}")
    elif stats.ok:
        print(f"  Carpeta: {course_dir}")
    if stats.failed and not args.update:
        print("  Los errores suelen ser transitorios: repite con --update para completar "
              "solo lo que falta.")
    return 0 if stats.ok else 1


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
        print("\n✗ Interrumpido. Lo ya descargado se conserva: continúa con --update.",
              file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
