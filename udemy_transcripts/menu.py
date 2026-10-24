"""Menú interactivo: `udemy` sin argumentos (o `udemy --menu`).

El menú no descarga nada por su cuenta: arma los mismos argumentos que escribirías en la línea
de comandos y llama a `cli.main(argv)`, así que hace exactamente lo mismo que el CLI. Antes de
empezar muestra el comando equivalente.
"""

import json
import os
import subprocess
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import __version__, cli
from .captions import parse_lang_spec
from .courses import list_courses
from .errors import UdemyError
from .manifest import MANIFEST_NAME
from .paths import learning_path_id
from .portal import choose_portal, host_from_ref
from .ranges import parse_ranges
from .tui import BOLD, CYAN, DIM, GREEN, RED, Console

SETTINGS_FILE = Path.home() / ".cache" / "udemy-transcripts-menu.json"

FORMATS = [
    ("merge", "Carpeta por lecciones + un archivo unificado (NotebookLM, Notion)"),
    ("folder", "Carpeta por lecciones (un .md por lección)"),
    ("single", "Solo un archivo Markdown con todo el curso (--single)"),
    ("txt", "Solo un archivo de texto plano (--txt)"),
]
LANGS = [("es,en", "Español (o inglés si no hay)"),
         ("es+en", "Bilingüe: español con el inglés debajo"), ("es", "Solo español"),
         ("en", "Solo inglés")]
RESOURCES = [("no", "No descargar archivos adjuntos"), ("yes", "Descargar adjuntos y imágenes"),
             ("only", "Solo los adjuntos (sin transcripciones)")]
STUDY = [("", "No"), ("prompt", "Prompts para pegar en un chat (gratis)"),
         ("api", "API de Claude (estima el coste y pide confirmación)")]


# ---------------------------------------------------------------------------------------------
# Ajustes (se guardan sin secretos; el token solo vive en la sesión)
# ---------------------------------------------------------------------------------------------
@dataclass
class Settings:
    out: str = ""            # "" = $UDEMY_OUT o ~/Udemy-Transcripts
    business: str = ""       # organización de Udemy Business ("" = cuenta personal)
    lang: str = "es,en"
    token: str = ""          # solo en memoria

    def effective_out(self):
        return Path(self.out or os.environ.get("UDEMY_OUT") or cli.DEFAULT_OUT)


def load_settings(path=None):
    path = Path(path or SETTINGS_FILE)
    settings = Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return settings
    if isinstance(data, dict):
        for f in fields(Settings):
            if f.name != "token" and isinstance(data.get(f.name), str):
                setattr(settings, f.name, data[f.name])
    return settings


def save_settings(settings, path=None):
    path = Path(path or SETTINGS_FILE)
    data = {k: v for k, v in asdict(settings).items() if k != "token"}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass                                  # no poder recordar los ajustes no es grave


# ---------------------------------------------------------------------------------------------
# Opciones de una descarga → argumentos del CLI
# ---------------------------------------------------------------------------------------------
@dataclass
class Choices:
    mode: str = "merge"       # merge | folder | single | txt
    lang: str = "es,en"
    resources: str = "no"     # no | yes | only
    sections: str = ""
    lectures: str = ""
    study: str = ""           # "" | prompt | api
    update: bool = False


def build_argv(target, choices, settings):
    """Argumentos del CLI para bajar `target` (URL, slug o id) con estas opciones."""
    argv = {"merge": ["--merge"], "single": ["--single"], "txt": ["--txt"]}.get(choices.mode, [])
    argv += ["--lang", choices.lang]
    if choices.resources == "yes":
        argv.append("--resources")
    elif choices.resources == "only":
        argv.append("--resources-only")
    if choices.sections:
        argv += ["--sections", choices.sections]
    if choices.lectures:
        argv += ["--lectures", choices.lectures]
    if choices.study:
        argv += ["--study", choices.study]
    if choices.update:
        argv.append("--update")
    if settings.out:
        argv += ["--out", settings.out]
    if settings.business and not host_from_ref(target):      # una URL ya indica su portal
        argv += ["--business", settings.business]
    if settings.token:
        argv += ["--token", settings.token]
    return argv + [target]


def command_line(argv):
    """El comando equivalente, listo para copiar (sin mostrar el token)."""
    shown = list(argv)
    for i, arg in enumerate(shown[:-1]):
        if arg == "--token":
            shown[i + 1] = "***"
    return "udemy " + subprocess.list2cmdline(shown)


def validate_target(text):
    """Mensaje de error si `text` no parece un curso, una ruta, un slug o un id; si no, None."""
    if any(c.isspace() for c in text):
        return "Escribe solo la URL, el slug o el id del curso (sin espacios)."
    if text.lower().startswith(("http://", "https://")) or "udemy.com" in text.lower():
        if not host_from_ref(text):
            return "Esa URL no es de Udemy (www.udemy.com o <org>.udemy.com)."
        if "/course/" not in text and not learning_path_id(text):
            return "La URL debe ser de un curso (/course/…) o de una ruta (/learning-paths/…)."
    return None


def find_courses(root):
    """Cursos descargados bajo `root` (hasta 2 niveles: cursos sueltos y cursos de rutas)."""
    root = Path(root)
    found = []
    try:
        for first in sorted(root.iterdir()):
            if (first / MANIFEST_NAME).is_file():
                found.append(first)
            elif first.is_dir():
                found += sorted(d for d in first.iterdir() if (d / MANIFEST_NAME).is_file())
    except OSError:
        return []
    return found


def manifest_course_id(course_dir):
    try:
        data = json.loads((Path(course_dir) / MANIFEST_NAME).read_text(encoding="utf-8"))
        return str(data.get("course_id") or "")
    except (OSError, ValueError, AttributeError):
        return ""


# ---------------------------------------------------------------------------------------------
# Pantallas
# ---------------------------------------------------------------------------------------------
def label_of(table, value):
    return next((label for key, label in table if key == value), value)


def banner(ui, settings):
    ui.clear()
    ui.say(f"Udemy Transcripts {__version__}", BOLD + CYAN)
    ui.say(f"Salida: {settings.effective_out()}"
           + (f" · Business: {settings.business}" if settings.business else ""), DIM)
    ui.say()


def run_cli(ui, argv):
    """Ejecuta el CLI con estos argumentos; devuelve su código de salida."""
    ui.say(f"\n$ {command_line(argv)}\n", DIM)
    try:
        return cli.main(argv)
    except SystemExit as exc:                       # argparse rechazó los argumentos
        return exc.code if isinstance(exc.code, int) else 2


def ask_targets(ui, first=None):
    """Una o varias URLs/ids (una por línea; vacío termina). None si se cancela."""
    ui.say("URLs de los cursos (o rutas de aprendizaje). Pega una, Enter; deja vacío para seguir.",
           DIM)
    targets = [first] if first else []
    while True:
        text = ui.ask(f"  URL {len(targets) + 1}", validate=validate_target)
        if text is None:
            return None if not targets else targets
        if not text:
            if targets:
                return targets
            ui.say("  Escribe al menos una (Esc para volver).", RED)
            continue
        targets.append(text)


def ask_ranges(ui, what, flag, current):
    def check(text):
        try:
            parse_ranges(text, flag)
        except UdemyError as exc:
            return str(exc)
        return None
    return ui.ask(f"{what} (p. ej. 3-5,8 o 12-)", current, check)


def ask_lang(ui, current):
    labels = [label for _, label in LANGS] + ["Otro…"]
    i = ui.choose("Idiomas del subtítulo", labels,
                  next((n for n, (k, _) in enumerate(LANGS) if k == current), len(LANGS)))
    if i is None:
        return current
    if i < len(LANGS):
        return LANGS[i][0]

    def check(text):
        try:
            parse_lang_spec(text)
        except (UdemyError, ValueError) as exc:
            return str(exc)
        return None
    return ui.ask("Idiomas por orden de preferencia (p. ej. es,en o pt)", current, check) \
        or current


def pick(ui, title, table, current):
    i = ui.choose(title, [label for _, label in table],
                  next((n for n, (k, _) in enumerate(table) if k == current), 0))
    return current if i is None else table[i][0]


def ask_selection(ui, choices):
    i = ui.choose("¿Qué partes del curso?", ["Todo el curso", "Solo algunas secciones…",
                                              "Solo algunas lecciones…"])
    if i == 0:
        choices.sections = choices.lectures = ""
    elif i == 1:
        text = ask_ranges(ui, "Secciones", "--sections", choices.sections)
        if text is not None:
            choices.sections, choices.lectures = text, ""
    elif i == 2:
        text = ask_ranges(ui, "Lecciones", "--lectures", choices.lectures)
        if text is not None:
            choices.lectures, choices.sections = text, ""


def selection_label(choices):
    if choices.sections:
        return f"Secciones {choices.sections}"
    if choices.lectures:
        return f"Lecciones {choices.lectures}"
    return "Todo el curso"


def edit_options(ui, choices, settings, title="Opciones de la descarga"):
    """Pantalla de opciones; devuelve True para empezar o False si se cancela."""
    row = 0
    while True:
        rows = [f"Formato:        {label_of(FORMATS, choices.mode)}",
                f"Idiomas:        {label_of(LANGS, choices.lang)}",
                f"Recursos:       {label_of(RESOURCES, choices.resources)}",
                f"Selección:      {selection_label(choices)}",
                f"Estudio con IA: {label_of(STUDY, choices.study)}",
                f"Solo novedades: {'Sí (--update)' if choices.update else 'No'}",
                "▶ Empezar la descarga"]
        row = ui.choose(title + "\nElige una opción para cambiarla, o empieza.", rows, row)
        if row is None:
            return False
        if row == 0:
            choices.mode = pick(ui, "Formato de salida", FORMATS, choices.mode)
            if choices.mode in ("single", "txt") and choices.study:
                choices.study = ""
        elif row == 1:
            choices.lang = ask_lang(ui, choices.lang)
        elif row == 2:
            choices.resources = pick(ui, "Recursos", RESOURCES, choices.resources)
        elif row == 3:
            ask_selection(ui, choices)
        elif row == 4:
            if choices.mode in ("single", "txt"):
                ui.say("El estudio con IA necesita la carpeta por lecciones: cambia el formato.",
                       RED)
                ui.pause()
            else:
                choices.study = pick(ui, "Estudio con IA (resumen + flashcards)", STUDY,
                                     choices.study)
        elif row == 5:
            answer = ui.choose("¿Solo lecciones nuevas o cambiadas?",
                               ["No, todo", "Sí, solo novedades (--update)"], int(choices.update))
            if answer is not None:
                choices.update = bool(answer)
        else:
            return True


def start_downloads(ui, settings, targets, choices):
    """Confirma y ejecuta una descarga por cada destino; muestra el resultado."""
    banner(ui, settings)
    ui.say("Se va a ejecutar:", BOLD)
    for target in targets:
        ui.say(f"  {command_line(build_argv(target, choices, settings))}", DIM)
    ui.say()
    if not ui.confirm(f"¿Empezar ({len(targets)} descarga{'s' if len(targets) != 1 else ''})?"):
        return
    results = []
    for n, target in enumerate(targets, 1):
        ui.say(f"\n══ {n}/{len(targets)}: {target}", BOLD)
        results.append((target, run_cli(ui, build_argv(target, choices, settings))))
    ui.say()
    for target, code in results:
        ui.say(f"  {'✓' if code == 0 else '✗'} {target}", GREEN if code == 0 else RED)
    ui.pause("Pulsa Enter para volver al menú…")


def screen_download(ui, settings, targets=None):
    banner(ui, settings)
    targets = ask_targets(ui) if targets is None else targets
    if not targets:
        return
    choices = Choices(lang=settings.lang)
    if edit_options(ui, choices, settings):
        start_downloads(ui, settings, targets, choices)


def screen_courses(ui, settings):
    """Lista tus cursos suscritos y descarga los que marques."""
    banner(ui, settings)
    ui.say("Abriendo Udemy para leer tu lista de cursos…", DIM)
    argv = []
    if settings.token:
        argv += ["--token", settings.token]
    args = cli.build_parser().parse_args(argv + ["--list"])
    try:
        with cli.open_client(args, choose_portal(None, settings.business)) as client:
            rows = list_courses(client)
    except UdemyError as exc:
        ui.say(f"\n✗ {exc}", RED)
        ui.pause()
        return
    if not rows:
        ui.say("No tienes cursos en esta cuenta.", RED)
        ui.pause()
        return
    picked = ui.multi(f"Tus cursos ({len(rows)}) — marca los que quieras descargar",
                      [f"{c['title']}  [{c['id']}]" for c in rows])
    if picked:
        screen_download(ui, settings, [str(rows[i]["id"]) for i in picked])


def screen_existing(ui, settings):
    """Actualizar, unificar o estudiar un curso que ya está en tu carpeta de salida."""
    root = settings.effective_out()
    courses = find_courses(root)
    banner(ui, settings)
    if not courses:
        ui.say(f"No encontré cursos descargados en {root}.", RED)
        ui.say("Cambia la carpeta en Ajustes o descarga uno primero.", DIM)
        ui.pause()
        return
    labels = [str(c.relative_to(root)) for c in courses]
    i = ui.choose(f"Cursos descargados en {root}", labels)
    if i is None:
        return
    course = courses[i]
    actions = ["Unificar en un solo Markdown (NotebookLM, Notion)",
               "Generar resumen y flashcards con IA",
               "Buscar lecciones nuevas en Udemy (--update)"]
    a = ui.choose(f"{labels[i]}\n¿Qué quieres hacer?", actions)
    if a is None:
        return
    if a == 0:
        argv = ["--merge-from", str(course)]
    elif a == 1:
        mode = pick(ui, "Estudio con IA", STUDY[1:], "prompt")
        argv = ["--study", mode, "--study-from", str(course)]
    else:
        course_id = manifest_course_id(course)
        if not course_id or course.parent != root:
            ui.say("Solo puedo actualizar cursos sueltos que tengan su manifest. Para una ruta "
                   "usa «Descargar» con la URL de la ruta y «Solo novedades».", RED)
            ui.pause()
            return
        argv = [course_id, "--update", "--out", str(root)]
        if settings.business:
            argv += ["--business", settings.business]
        if ui.confirm("¿Regenerar también el archivo unificado?"):
            argv.insert(0, "--merge")
        if settings.token:
            argv += ["--token", settings.token]
    banner(ui, settings)
    code = run_cli(ui, argv)
    ui.say(f"\n{'✓ Listo' if code == 0 else '✗ Terminó con errores'}",
           GREEN if code == 0 else RED)
    ui.pause("Pulsa Enter para volver al menú…")


def screen_settings(ui, settings):
    row = 0
    while True:
        rows = [f"Carpeta de salida: {settings.effective_out()}",
                f"Udemy Business:    {settings.business or '(cuenta personal)'}",
                f"Idioma por defecto: {label_of(LANGS, settings.lang)}",
                f"Token de acceso:   {'(definido, solo esta sesión)' if settings.token else '(ninguno)'}",
                "Volver"]
        row = ui.choose("Ajustes\nSe guardan para la próxima vez (el token no).", rows, row)
        if row is None or row == 4:
            return
        if row == 0:
            text = ui.ask("Carpeta de salida (vacío = la de siempre)", settings.out)
            if text is not None:
                settings.out = text
        elif row == 1:
            text = ui.ask("Organización de Udemy Business, p. ej. seti (vacío = personal)",
                          settings.business)
            if text is not None:
                settings.business = text.strip()
        elif row == 2:
            settings.lang = ask_lang(ui, settings.lang)
        elif row == 3:
            text = ui.ask("Token (access_token de la cookie; vacío = quitar)", secret=True)
            if text is not None:
                settings.token = text
        save_settings(settings)


def run_menu(ui=None, settings=None):
    """Bucle del menú principal. Devuelve el código de salida del programa."""
    ui = ui or Console()
    settings = settings or load_settings()
    items = ["Descargar curso(s) por URL", "Ver mis cursos", "Actualizar / unificar un curso "
             "descargado", "Ajustes", "Salir"]
    row = 0
    try:
        while True:
            banner(ui, settings)
            row = ui.choose("¿Qué quieres hacer?", items, row, hint="↑↓ mover · Enter elegir · "
                                                                    "Esc salir")
            if row is None or row == 4:
                return 0
            {0: screen_download, 1: screen_courses, 2: screen_existing,
             3: screen_settings}[row](ui, settings)
    except KeyboardInterrupt:
        ui.say("\nHasta luego.")
        return 130
