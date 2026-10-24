"""Material de estudio con IA: resumen y flashcards (Anki) por sección.

Dos modos:
  api     llama a la API de Claude con tu clave (estima el coste y pide confirmación);
  prompt  escribe prompts listos para pegar en Claude/ChatGPT, sin coste de API.

Se trabaja a partir de las lecciones ya descargadas (`.udemy-transcripts.json`), por
sección, con una caché por la huella del texto para no regenerar lo que no cambió.
"""

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from .ai import (DEFAULT_MODEL, AnthropicBackend, FatalStudyError, StudyError, model_info)
from .errors import UdemyError
from .manifest import MANIFEST_NAME, Manifest
from .util import fs_path

PROMPT_VERSION = 1              # súbela si cambian las instrucciones: invalida la caché
CACHE_DIR = ".estudio"
PROMPTS_DIR = "prompts"
CHUNK_TOKENS = 100_000          # entrada máxima por petición; una sección más larga se parte
CHARS_PER_TOKEN = 3.3           # estimación para texto en español (sin llamar a la API)
SYSTEM_TOKENS = 900             # instrucciones de cada petición
OUTPUT_TOKENS_PER_CALL = 7000   # razonamiento + resumen + tarjetas (estimación)
ANKI_HEADER = ("#separator:semicolon", "#html:false", "#tags column:3")

SYSTEM_PROMPT = """\
Eres un tutor técnico que prepara material de estudio a partir de las transcripciones de \
un curso en vídeo. Trabajas solo con lo que dicen las transcripciones: no añadas datos, \
versiones, código ni afirmaciones que no aparezcan en ellas; si algo queda a medias, \
indícalo. Escribe en el mismo idioma que las transcripciones.

Produces dos cosas para el bloque de lecciones que recibes:

1. «resumen»: un resumen en Markdown con estas secciones (omite las que no apliquen):
   ## Ideas clave        viñetas con lo esencial, en orden de importancia
   ## Conceptos          «**Término**: definición breve» para cada concepto nuevo
   ## Código y comandos  los ejemplos de código, comandos o configuración que se mencionan, \
en bloques de código con su lenguaje y una línea de contexto; no inventes código que no se \
dicte en la transcripción
   ## Para repasar       3-5 preguntas abiertas de autoevaluación
   Menciona de qué lección sale cada idea importante con «(lección 012)».

2. «flashcards»: tarjetas para memorizar (repetición espaciada). Cada tarjeta es atómica \
(una sola idea), se entiende sin ver el vídeo (no digas «según la lección») y tiene la \
respuesta corta (1-3 frases). Mezcla definiciones, «¿para qué sirve…?», «¿qué diferencia hay \
entre…?» y detalles prácticos. «etiquetas»: 1-3 palabras clave en minúsculas, sin espacios \
(usa guiones), p. ej. «spring-security», «jwt».
"""


# ---------------------------------------------------------------------------------
# Lecciones y secciones a partir de lo descargado
# ---------------------------------------------------------------------------------
_TS_MD = re.compile(r"^(?:\[\d{1,2}:\d{2}(?::\d{2})?\]\([^)]*\)|`\[\d{1,2}:\d{2}(?::\d{2})?\]`) ?")
_TS_TXT = re.compile(r"^\[\d{1,2}:\d{2}(?::\d{2})?\] ")
_MD_ESCAPED = re.compile(r"\\([\\`*_\[\]<>$#+\-.)(])")


def clean_lesson_text(raw):
    """Quita de un archivo de lección lo que no es contenido: cabecera YAML, título,
    metadatos, marcas de tiempo, escapes de Markdown y la sección de recursos."""
    text = raw.replace("\r\n", "\n")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + 5:]
    text = re.split(r"\n(?:## Recursos|RECURSOS)\n", text)[0]
    out, in_fence, seen_title, meta_pending = [], False, False, False
    for line in text.split("\n"):
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            if not seen_title and line.startswith("# "):
                seen_title = meta_pending = True
                continue
            if meta_pending and line.strip():
                meta_pending = False
                if line.startswith("> "):
                    continue                              # línea de metadatos bajo el título
            line = _TS_TXT.sub("", _TS_MD.sub("", line))
            line = _MD_ESCAPED.sub(r"\1", line)
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


@dataclass
class StudyLesson:
    number: str
    title: str
    text: str
    rel: str

    @property
    def index(self):
        return int(self.number) if self.number.isdigit() else None


@dataclass
class StudySection:
    index: int
    dirname: str
    title: str
    lessons: list = field(default_factory=list)

    @property
    def words(self):
        return sum(len(lesson.text.split()) for lesson in self.lessons)

    def chunks(self, max_tokens=None):
        """Partes de la sección que caben en una petición (casi siempre, una)."""
        max_tokens = max_tokens or CHUNK_TOKENS
        parts, current, size = [], [], 0
        for lesson in self.lessons:
            tokens = estimate_tokens(lesson.text) + 20
            if current and size + tokens > max_tokens:
                parts.append(current)
                current, size = [], 0
            current.append(lesson)
            size += tokens
        if current:
            parts.append(current)
        return parts

    @property
    def digest(self):
        raw = "\x1f".join(f"{lesson.number}\x1e{lesson.title}\x1e{lesson.text}"
                          for lesson in self.lessons)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def estimate_tokens(text):
    return int(len(text) / CHARS_PER_TOKEN) + 1


def load_manifest(course_dir):
    """Manifest de una carpeta de curso ya descargada (sin saber su id de antemano)."""
    path = Path(course_dir) / MANIFEST_NAME
    try:
        course_id = json.loads(fs_path(path).read_text(encoding="utf-8")).get("course_id")
    except (OSError, ValueError, AttributeError):
        raise UdemyError(f"{course_dir} no parece un curso descargado: falta {MANIFEST_NAME}. "
                         "Descárgalo primero con udemy.")
    return Manifest.load(path, course_id, log=lambda *_: None)


def collect_sections(course_dir, manifest, select=None):
    """Secciones con el texto limpio de sus lecciones descargadas (vídeos y artículos)."""
    grouped = {}
    for entry in manifest.entries.values():
        rel = entry.get("file") or ""
        parts = rel.split("/")
        if len(parts) != 2:
            continue
        dirname, name = parts
        m = re.match(r"(\d+) - ", dirname)
        n = re.match(r"(\d+) - (.*)\.(?:md|txt)$", name)
        path = fs_path(Path(course_dir) / rel)
        if not (m and n and path.is_file()):
            continue
        section = grouped.setdefault(dirname, StudySection(int(m.group(1)), dirname,
                                                           entry.get("section") or dirname))
        lesson = StudyLesson(n.group(1), entry.get("title") or n.group(2),
                             clean_lesson_text(path.read_text(encoding="utf-8")), rel)
        if lesson.text and (select is None or select(SimpleNamespace(index=section.index),
                                                     SimpleNamespace(index=lesson.index))):
            section.lessons.append(lesson)
    sections = [s for s in grouped.values() if s.lessons]
    for section in sections:
        section.lessons.sort(key=lambda lesson: lesson.number)
    return sorted(sections, key=lambda s: (s.index, s.dirname))


# ---------------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------------
def card_range(words):
    """Nº orientativo de tarjetas según la cantidad de texto."""
    target = max(6, min(25, round(words / 450)))
    return max(4, target - 3), target + 3


def lessons_block(lessons):
    return "\n\n".join(f'<leccion numero="{lesson.number}" titulo="{_attr(lesson.title)}">\n'
                       f"{lesson.text}\n</leccion>" for lesson in lessons)


def _attr(text):
    return text.replace('"', "'").replace("\n", " ")


def user_prompt(section, lessons, part=None, parts=1):
    lo, hi = card_range(sum(len(lesson.text.split()) for lesson in lessons))
    where = f"la sección «{section.title}»" + (f" (parte {part} de {parts})" if parts > 1 else "")
    return (f"Estas son las transcripciones de {where} del curso.\n\n"
            f"{lessons_block(lessons)}\n\n"
            f"Genera el resumen y entre {lo} y {hi} tarjetas.")


def chat_prompt(section, lessons, part=None, parts=1):
    """Prompt completo para pegar en un chat (sin API): instrucciones + texto + formato."""
    return (f"{SYSTEM_PROMPT}\n"
            "Responde con EXACTAMENTE dos bloques de código y nada más:\n\n"
            "- uno ```markdown con el resumen (el contenido de RESUMEN.md);\n"
            "- uno ```csv con las tarjetas, una por línea, con el formato "
            "`pregunta;respuesta;etiquetas` (separador «;», campos con «;», comillas o saltos de "
            "línea entre comillas dobles, etiquetas separadas por espacios, sin cabecera).\n\n"
            f"{user_prompt(section, lessons, part, parts)}\n")


# ---------------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------------
def _tag(text):
    return re.sub(r"[^\w\-:.]+", "-", text.strip().lower()).strip("-")


def card_rows(cards, section):
    """(pregunta, respuesta, etiquetas) con la etiqueta de sección añadida."""
    section_tag = f"seccion-{section.index:02d}"
    rows = []
    for card in cards:
        tags = [t for t in (_tag(t) for t in card.get("etiquetas") or []) if t]
        if section_tag not in tags:
            tags.append(section_tag)
        rows.append((card["pregunta"].strip(), card["respuesta"].strip(), " ".join(tags)))
    return rows


def flashcards_csv(rows):
    """CSV importable en Anki: separador «;», etiquetas en la 3.ª columna, sin cabecera."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerows(rows)
    return "\n".join(ANKI_HEADER) + "\n" + buffer.getvalue()


def summary_markdown(section, resumen, model, n_lessons):
    return (f"# Resumen — {section.dirname}\n\n"
            f"> Generado con {model} a partir de {n_lessons} lección(es). "
            "Revísalo: puede contener errores.\n\n" + resumen.strip() + "\n")


def _write(path, text):
    try:
        target = fs_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise UdemyError(f"No pude escribir {path}: {exc}")


# ---------------------------------------------------------------------------------
# Caché, estimación y ejecución
# ---------------------------------------------------------------------------------
def cache_path(course_dir, section):
    return Path(course_dir) / CACHE_DIR / f"{section.dirname}.json"


def section_key(section, model):
    raw = f"{PROMPT_VERSION}|{model}|{section.digest}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_cached(course_dir, section, model):
    try:
        data = json.loads(fs_path(cache_path(course_dir, section)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("key") == section_key(section, model) \
        else None


@dataclass
class Estimate:
    calls: int
    input_tokens: int
    output_tokens: int
    cost: Optional[float]          # USD; None si no conocemos el precio del modelo


def estimate(sections, model):
    calls = input_tokens = 0
    for section in sections:
        for chunk in section.chunks():
            calls += 1
            input_tokens += SYSTEM_TOKENS + sum(estimate_tokens(le.text) + 30 for le in chunk)
    output_tokens = calls * OUTPUT_TOKENS_PER_CALL
    info = model_info(model)
    cost = (input_tokens * info[0] + output_tokens * info[1]) / 1e6 if info else None
    return Estimate(calls, input_tokens, output_tokens, cost)


def money(usd):
    return f"${usd:.2f}" if usd >= 0.01 else "< $0.01"


@dataclass
class StudyOptions:
    mode: str = "api"                       # "api" | "prompt"
    model: str = DEFAULT_MODEL
    regenerate: bool = False
    assume_yes: bool = False


@dataclass
class StudyStats:
    generated: int = 0
    cached: int = 0
    failed: int = 0
    prompts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    errors: list = field(default_factory=list)


def write_prompts(course_dir, course_title, sections, log=print):
    """Un archivo `prompts/<sección>[ - parte N].md` por trozo, listo para pegar en un chat."""
    count = 0
    for section in sections:
        chunks = section.chunks()
        for n, chunk in enumerate(chunks, 1):
            suffix = f" - parte {n}" if len(chunks) > 1 else ""
            body = chat_prompt(section, chunk, n, len(chunks))
            tokens = estimate_tokens(body)
            head = (f"<!-- {course_title} · {section.dirname}{suffix} · ~{tokens:,} tokens -->\n"
                    f"<!-- Pega todo lo que sigue en un chat nuevo de Claude o ChatGPT. Guarda el "
                    f"bloque markdown como RESUMEN.md y el csv como flashcards.csv (en Anki: "
                    f"Importar; separador punto y coma, etiquetas en la columna 3). -->\n\n")
            _write(Path(course_dir) / PROMPTS_DIR / f"{section.dirname}{suffix}.md", head + body)
            count += 1
    _write(Path(course_dir) / PROMPTS_DIR / "LEEME.md", _readme(course_title, count))
    log(f"  ✓ {count} prompt(s) en {Path(course_dir) / PROMPTS_DIR}")
    return count


def _readme(course_title, count):
    return (f"# Prompts de estudio — {course_title}\n\n"
            f"{count} archivo(s), uno por sección (o por parte si la sección es muy larga).\n\n"
            "1. Abre un archivo y pega **todo** su contenido en un chat nuevo de Claude o ChatGPT.\n"
            "2. Guarda el bloque `markdown` de la respuesta como `RESUMEN.md` en la carpeta de esa "
            "sección y el bloque `csv` como `flashcards.csv`.\n"
            "3. Anki: *Archivo → Importar*, separador «punto y coma», etiquetas en la columna 3 "
            "(las líneas `#…` del principio no hacen falta: añádelas si tu Anki no detecta el formato).\n\n"
            "Cada prompt lleva el texto de las lecciones: úsalo solo para tu estudio personal.\n")


def _store(course_dir, section, model, chunks_results, log):
    """Escribe RESUMEN.md y flashcards.csv de la sección y devuelve sus datos."""
    resumen = "\n\n".join(chunks_results["resumen"])
    cards = chunks_results["flashcards"]
    section_dir = Path(course_dir) / section.dirname
    _write(section_dir / "RESUMEN.md",
           summary_markdown(section, resumen, model, len(section.lessons)))
    _write(section_dir / "flashcards.csv", flashcards_csv(card_rows(cards, section)))
    return resumen, cards


def write_course_flashcards(course_dir, sections, model):
    """`flashcards.csv` del curso: todas las tarjetas generadas, para importarlas de una vez."""
    rows = []
    for section in sections:
        cached = load_cached(course_dir, section, model)
        if cached:
            rows += card_rows(cached.get("flashcards") or [], section)
    if rows:
        _write(Path(course_dir) / "flashcards.csv", flashcards_csv(rows))
    return len(rows)


def run_api(course_dir, sections, opts, backend, log=print):
    stats = StudyStats()
    total = len(sections)
    for n, section in enumerate(sections, 1):
        label = f"[{n}/{total}] {section.dirname}"
        cached = None if opts.regenerate else load_cached(course_dir, section, opts.model)
        if cached:
            _store(course_dir, section, opts.model,
                   {"resumen": [cached["resumen"]], "flashcards": cached["flashcards"]}, log)
            log(f"  = {label}  (en caché, {len(cached['flashcards'])} tarjetas)")
            stats.cached += 1
            continue
        parts = section.chunks()
        results = {"resumen": [], "flashcards": []}
        used = [0, 0]
        try:
            for part, chunk in enumerate(parts, 1):
                gen = backend.generate(SYSTEM_PROMPT, user_prompt(section, chunk, part, len(parts)))
                header = f"### Parte {part}\n\n" if len(parts) > 1 else ""
                results["resumen"].append(header + gen.resumen)
                results["flashcards"] += gen.flashcards
                used[0] += gen.input_tokens
                used[1] += gen.output_tokens
                stats.input_tokens += gen.input_tokens
                stats.output_tokens += gen.output_tokens
        except FatalStudyError:
            raise
        except StudyError as exc:
            log(f"  ✗ {label}: {exc}")
            stats.failed += 1
            stats.errors.append(f"{section.dirname}: {exc}")
            continue
        resumen, cards = _store(course_dir, section, opts.model, results, log)
        _write(cache_path(course_dir, section), json.dumps({
            "key": section_key(section, opts.model), "model": opts.model,
            "resumen": resumen, "flashcards": cards,
            "usage": {"input": used[0], "output": used[1]}},
            ensure_ascii=False, indent=1))
        log(f"  ✓ {label}  ({len(cards)} tarjetas)")
        stats.generated += 1
    return stats


def study_course(course_dir, course_title, opts, select=None, backend=None, log=print,
                 input_fn=input):
    """Genera el material de estudio de un curso ya descargado."""
    manifest = load_manifest(course_dir)
    sections = collect_sections(course_dir, manifest, select)
    if not sections:
        raise UdemyError("No hay lecciones descargadas con texto que estudiar"
                         + (" en ese rango" if select else "") + ".")
    words = sum(s.words for s in sections)
    log(f"• Estudio ({opts.mode}): {len(sections)} sección(es), {words:,} palabras")

    if opts.mode == "prompt":
        stats = StudyStats(prompts=write_prompts(course_dir, course_title, sections, log))
        return stats

    todo = [s for s in sections if opts.regenerate or not load_cached(course_dir, s, opts.model)]
    if todo:
        est = estimate(todo, opts.model)
        price = (f"≈ {money(est.cost)}" if est.cost is not None
                 else "(no tengo el precio de este modelo)")
        log(f"  Se harán {est.calls} llamada(s) a {opts.model}: ~{est.input_tokens:,} tokens de "
            f"entrada y ~{est.output_tokens:,} de salida → coste estimado {price} "
            f"({len(sections) - len(todo)} sección(es) ya en caché).")
        log("  ⚠ Se enviará el texto de las transcripciones a la API de Anthropic con tu "
            "clave. Comprueba que las condiciones de tu curso/empresa lo permiten.")
        if not opts.assume_yes:
            try:
                answer = input_fn("  ¿Continuar? [s/N] ")
            except EOFError:
                raise UdemyError("Hace falta confirmar el envío a la API y no hay terminal "
                                 "interactiva: repite con --yes para aceptar.")
            if answer.strip().lower() not in ("s", "si", "sí", "y", "yes"):
                raise UdemyError("Cancelado: no se envió nada a la API.")
    backend = backend or AnthropicBackend(opts.model, log=log)
    stats = run_api(course_dir, sections, opts, backend, log)
    rows = write_course_flashcards(course_dir, sections, opts.model)
    info = model_info(opts.model)
    real = (stats.input_tokens * info[0] + stats.output_tokens * info[1]) / 1e6 if info else None
    log(f"  Tokens usados: {stats.input_tokens:,} de entrada y {stats.output_tokens:,} de salida"
        + (f" (≈ {money(real)})" if real is not None else "") + ".")
    if rows:
        log(f"  ✓ {rows} tarjetas en {Path(course_dir) / 'flashcards.csv'}")
    return stats
