"""Línea de comandos: argumentos y orquestación.

    udemy <url|slug|id> [--format md|txt] [--single] [--update] [--lang es,en] [--out DIR]
    udemy <url de una ruta de aprendizaje>
    udemy --list
"""

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import __version__
from .client import Client, ensure_login
from .courses import course_info, list_courses, resolve_course_id
from .curriculum import fetch_curriculum
from .ai import DEFAULT_MODEL
from .download import download_course
from .errors import BlockedError, NotLoggedInError, UdemyError
from .manifest import MANIFEST_NAME, Manifest
from .paths import course_folder, fetch_learning_path, learning_path_id, path_index
from .portal import choose_portal, host_from_ref, token_cookie
from .ranges import make_selector, parse_ranges
from .render import markdown, txt
from .render.common import RenderOptions
from .resources import DEFAULT_MAX_SIZE, ResourceOptions, parse_size, parse_types
from .study import StudyOptions, study_course
from .util import fs_path, safe_name

PROFILE_DIR = Path.home() / ".cache" / "udemy-transcripts-profile"
DEFAULT_OUT = Path.home() / "Udemy-Transcripts"


def build_parser():
    ap = argparse.ArgumentParser(prog="udemy",
                                 description="Transcripciones, artículos y recursos de un "
                                             "curso de Udemy.")
    ap.add_argument("course", nargs="?",
                    help="URL del curso o de una ruta de aprendizaje, slug o course_id numérico")
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
                    help="solo descarga lecciones nuevas o cambiadas y reanuda una descarga "
                         "cortada (usa .udemy-transcripts.json)")
    ap.add_argument("--no-timestamps", action="store_true",
                    help="sin marcas de tiempo al inicio de los párrafos")
    ap.add_argument("--ts-every", type=int, default=0, metavar="SEG",
                    help="una marca de tiempo como mucho cada SEG segundos "
                         "(default 0: una por párrafo)")
    ap.add_argument("--width", type=int, default=100,
                    help="ancho de línea del texto (solo --format txt); 0 = sin ajustar "
                         "(default 100)")
    sel = ap.add_argument_group("selección")
    sel.add_argument("--sections", metavar="RANGOS",
                     help="solo estas secciones (numeración de Udemy), p. ej. 3-5,8 o 12-")
    sel.add_argument("--lectures", metavar="RANGOS",
                     help="solo estas lecciones (el número NNN de los archivos), p. ej. 10-20")
    res = ap.add_argument_group("recursos")
    res.add_argument("--resources", action="store_true",
                     help="descarga también los archivos adjuntos (PDF, código, zip…) a "
                          "recursos/ y las imágenes de los artículos")
    res.add_argument("--resources-only", action="store_true",
                     help="solo los recursos: sin transcripciones ni artículos (implica "
                          "--resources)")
    res.add_argument("--resource-types", metavar="EXT",
                     help="solo estas extensiones de archivo, p. ej. pdf,zip")
    res.add_argument("--max-size", default=None, metavar="TAM",
                     help="omite archivos más grandes (default 500MB), p. ej. 200MB o 2GB")
    res.add_argument("--yes", action="store_true",
                     help="no pedir confirmación cuando los recursos pesan mucho")
    study = ap.add_argument_group("estudio con IA")
    study.add_argument("--study", choices=("api", "prompt"),
                       help="genera RESUMEN.md y flashcards.csv (Anki) por sección: «api» "
                            "usa la API de Claude (estima el coste y pide confirmación); "
                            "«prompt» escribe prompts para pegar en un chat, sin coste")
    study.add_argument("--ai-model", default=DEFAULT_MODEL, metavar="MODELO",
                       help=f"modelo de --study api (default {DEFAULT_MODEL})")
    study.add_argument("--study-from", metavar="CARPETA",
                       help="estudia un curso ya descargado, sin abrir el navegador ni Udemy")
    study.add_argument("--regenerate", action="store_true",
                       help="ignora la caché y vuelve a generar el estudio")
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


def resource_options(args):
    only = args.resources_only
    return ResourceOptions(
        enabled=args.resources or only, only=only, types=parse_types(args.resource_types),
        max_size=parse_size(args.max_size) if args.max_size else DEFAULT_MAX_SIZE,
        assume_yes=args.yes)


def study_options(args):
    """Opciones de --study (o None) y comprobación de combinaciones imposibles."""
    if not args.study:
        if args.study_from:
            raise UdemyError("--study-from necesita --study api o --study prompt.")
        return None
    if args.txt or args.single:
        raise UdemyError("--study trabaja con las lecciones por archivo: no lo combines con "
                         "--single ni --txt.")
    return StudyOptions(mode=args.study, model=args.ai_model, regenerate=args.regenerate,
                        assume_yes=args.yes)


def selector_from_args(args):
    sections = parse_ranges(args.sections, "--sections")
    lectures = parse_ranges(args.lectures, "--lectures")
    return make_selector(sections, lectures) if sections or lectures else None


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


@dataclass
class Job:
    """Todo lo que hace falta para bajar un curso (se reutiliza en las rutas)."""
    langs: list
    opts: RenderOptions
    single: bool
    res: ResourceOptions
    select: Optional[object]
    update: bool
    study: Optional[StudyOptions] = None


def download_one(client, course_id, job, base, course_dir=None, log=print):
    """Baja un curso completo; devuelve (course, stats, carpeta o archivo de salida)."""
    course = course_info(client, course_id)
    log(f"  → {course.title} (id {course_id})")
    course_dir = Path(course_dir) if course_dir else base / safe_name(course.title)

    log("• Leyendo temario…")
    sections = fetch_curriculum(client, course_id)
    lessons = [lec for s in sections for lec in s.lectures]
    if not any(lec.is_video or lec.is_article for lec in lessons):
        raise UdemyError("El curso no tiene lecciones de vídeo ni artículos.")
    if job.res.only and not any(lec.resources for lec in lessons):
        raise UdemyError("El curso no tiene recursos que descargar.")

    manifest = None
    if not job.single or job.res.enabled:
        fs_path(course_dir).mkdir(parents=True, exist_ok=True)
        manifest = Manifest.load(course_dir / MANIFEST_NAME, course_id, log=log)
    stats = download_course(client, course, sections, job.langs, job.opts, course_dir,
                            job.single, job.update, manifest, log=log, select=job.select,
                            res=job.res)
    if job.study and stats.ok:
        log("• Material de estudio…")
        study_course(course_dir, course.title, job.study, select=job.select, log=log)
    output = course_dir
    if job.single and stats.saved:
        output = course_dir.parent / f"{safe_name(course.title)}.{job.opts.ext}"
        render = markdown if job.opts.format == "md" else txt
        try:
            fs_path(output).write_text(render.single_document(course, stats.items),
                                       encoding="utf-8")
        except OSError as exc:
            raise UdemyError(f"No pude escribir {output}: {exc}")
    return course, stats, output


def summary(stats, job):
    """Línea «Listo: …» de un curso."""
    parts = []
    if not job.res.only:
        parts.append(f"{stats.saved} lecciones")
    if job.update:
        parts.append(f"{stats.up_to_date} sin cambios")
    if job.res.enabled:
        parts.append(f"{stats.files} recursos"
                     + (f" ({stats.files_done} ya estaban)" if stats.files_done else ""))
    if not job.res.only:
        parts.append(f"{stats.no_captions} sin subtítulos")
        if stats.empty:
            parts.append(f"{stats.empty} artículos vacíos")
    parts.append(f"{stats.errors} con error")
    return f"{'✓' if stats.ok else '✗'} Listo: " + ", ".join(parts) + "."


def report(stats, output, job):
    print(f"\n{summary(stats, job)}")
    if stats.orphans:
        print(f"  ⚠ {len(stats.orphans)} archivo(s) antiguo(s) se conservan "
              "(la lección cambió de nombre o de sección).")
    if stats.ok:
        print(f"  {'Archivo' if Path(output).suffix in ('.md', '.txt') else 'Carpeta'}: {output}")
    if stats.errors and not job.update:
        print("  Los errores suelen ser transitorios: repite con --update para completar "
              "solo lo que falta.")


def download_path(client, path_id, job, base):
    """Baja todos los cursos de una ruta de aprendizaje en `<ruta>/<NN - curso>/`."""
    path = fetch_learning_path(client, path_id)
    courses = path.courses
    print(f"  → Ruta: {path.title} ({len(courses)} cursos)")
    path_dir = base / safe_name(path.title)
    fs_path(path_dir).mkdir(parents=True, exist_ok=True)
    done = 0
    try:
        for n, item in enumerate(courses, 1):
            folder = course_folder(n, item.title)
            print(f"\n══ Curso {n}/{len(courses)}: {item.title}")
            try:
                _, stats, _ = download_one(client, item.course_id, job, path_dir,
                                           course_dir=path_dir / folder)
            except (NotLoggedInError, BlockedError):
                raise                              # la sesión se perdió: no tiene sentido seguir
            except UdemyError as exc:
                print(f"  ✗ {exc}")
                item.status = f"error: {exc}"
                continue
            print(summary(stats, job))
            item.folder = folder
            item.status = "ok" if stats.ok else "sin contenido descargado"
            done += bool(stats.ok)
    finally:
        try:
            fs_path(path_dir / "README.md").write_text(path_index(path, client.portal.base),
                                                       encoding="utf-8")
        except OSError as exc:
            print(f"  ⚠ No pude escribir el índice de la ruta: {exc}")
    print(f"\n{'✓' if done else '✗'} Ruta: {done} de {len(courses)} cursos descargados."
          f"\n  Carpeta: {path_dir}")
    return 0 if done else 1


def run(args):
    opts, single = options_from_args(args)
    res = resource_options(args)
    select = selector_from_args(args)
    study = study_options(args)
    if args.study_from:                       # sin navegador: solo lo ya descargado
        course_dir = Path(args.study_from)
        study_course(course_dir, course_dir.resolve().name, study, select=select)
        return 0
    if args.headless:
        print("⚠ Aviso: Udemy suele bloquear el modo headless (Cloudflare). "
              "Si falla, ejecútalo sin --headless.")
    if args.update and single and not args.do_list:
        print("⚠ Aviso: --update no aplica a --single/--txt; se regenera el archivo completo.")
    langs = parse_langs(args.lang)
    portal = choose_portal(args.course, args.business)
    if args.business and host_from_ref(args.course) and \
            host_from_ref(args.course) != choose_portal(None, args.business).host:
        print(f"⚠ Aviso: la URL apunta a {portal.host}; se ignora --business "
              f"{args.business}.")
    if portal.is_business:
        print(f"• Portal: Udemy Business ({portal.host})")
    path_id = learning_path_id(args.course)
    if path_id and not portal.is_business:
        raise UdemyError("Las rutas de aprendizaje son de Udemy Business: usa la URL de tu "
                         "portal (https://<org>.udemy.com/learning-paths/<id>/).")

    base = Path(args.out) if args.out else Path(os.environ.get("UDEMY_OUT") or DEFAULT_OUT)
    job = Job(langs, opts, single, res, select, args.update, study)

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

            fs_path(base).mkdir(parents=True, exist_ok=True)
            if path_id:
                return download_path(client, path_id, job, base)

            print("• Resolviendo curso…")
            course_id = resolve_course_id(client, args.course)
            _, stats, output = download_one(client, course_id, job, base)
        finally:
            context.close()

    report(stats, output, job)
    return 0 if stats.ok else 1


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")   # consolas que no son UTF-8
        except (AttributeError, ValueError):
            pass
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.do_list and not args.course and not args.study_from:
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
