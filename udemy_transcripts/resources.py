"""Recursos de las lecciones: archivos adjuntos, enlaces e imágenes de artículos."""

import os
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote, unquote, urlparse

from .errors import UdemyError
from .util import fs_path, safe_name

RESOURCES_DIR = "recursos"
DEFAULT_MAX_SIZE = 500 * 1024 * 1024          # por archivo
CONFIRM_ABOVE = 500 * 1024 * 1024             # total que pide confirmación
EXECUTABLE_EXTS = {"exe", "msi", "bat", "cmd", "com", "scr", "ps1", "vbs", "jar", "war",
                   "dmg", "pkg", "apk", "deb", "rpm", "sh"}
_UNITS = {"": 1, "b": 1, "k": 1024, "kb": 1024, "m": 1024 ** 2, "mb": 1024 ** 2,
          "g": 1024 ** 3, "gb": 1024 ** 3}


@dataclass
class ResourceOptions:
    enabled: bool = False                 # --resources
    only: bool = False                    # --resources-only
    types: Optional[set] = None           # --resource-types
    max_size: Optional[int] = DEFAULT_MAX_SIZE
    assume_yes: bool = False              # --yes


@dataclass
class Planned:
    """Un archivo candidato a descargarse."""
    lecture: object
    section: object
    resource: object
    rel: str                      # ruta relativa al curso (con «/»)
    size: Optional[int] = None    # bytes; None si no se pudo averiguar
    status: str = "new"           # new | done | big | type


@dataclass
class Plan:
    items: List[Planned] = field(default_factory=list)

    def with_status(self, status):
        return [p for p in self.items if p.status == status]

    @property
    def to_download(self):
        return self.with_status("new")

    @property
    def total_bytes(self):
        return sum(p.size or 0 for p in self.to_download)

    @property
    def unknown_size(self):
        return sum(1 for p in self.to_download if p.size is None)


@dataclass
class Outcome:
    """Resultado de un recurso para pintarlo en su lección."""
    resource: object
    rel: Optional[str] = None     # ruta local si está descargado
    name: str = ""                # nombre en disco (con extensión)


def parse_size(text):
    """`200MB`, `1.5g`, `4096` → bytes."""
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*([a-zA-Z]*)\s*", text or "")
    unit = m.group(2).lower() if m else None
    if not m or unit not in _UNITS:
        raise UdemyError(f"--max-size: «{text}» no es un tamaño válido (p. ej. 200MB, 1.5GB).")
    return int(float(m.group(1).replace(",", ".")) * _UNITS[unit])


def format_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def parse_types(text):
    """`pdf,zip` → {'pdf', 'zip'}; vacío → None (todos)."""
    types = {t.strip().lower().lstrip(".") for t in (text or "").split(",") if t.strip()}
    return types or None


def extension(name):
    ext = os.path.splitext(name or "")[1].lstrip(".").lower()
    return ext if re.fullmatch(r"[a-z0-9_]{1,12}", ext) else ""


def url_extension(url):
    return extension(posixpath.basename(unquote(urlparse(url).path)))


def safe_filename(name, maxlen=120):
    """Como `safe_name`, pero recortando el nombre sin comerse la extensión."""
    stem, ext = os.path.splitext(name or "")
    if not re.fullmatch(r"\.[A-Za-z0-9_]{1,12}", ext):
        stem, ext = name or "", ""
    return safe_name(stem, "archivo", maxlen - len(ext)) + ext


def resource_filename(resource):
    """Nombre en disco: el original; si no tiene extensión, la del archivo del CDN."""
    name = resource.filename or resource.title or "archivo"
    if not extension(name):
        ext = url_extension(resource.url)
        if ext:
            name = f"{name}.{ext}"
    return safe_filename(name)


def lecture_dirname(lecture):
    return f"{lecture.number} - {safe_name(lecture.title)}"


def resource_dir(section, lecture):
    return f"{RESOURCES_DIR}/{section.dirname}/{lecture_dirname(lecture)}"


def unique_names(names):
    """Desambigua duplicados de una misma carpeta: `a.pdf`, `a (2).pdf`…"""
    seen, out = {}, []
    for name in names:
        key = name.lower()
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 1:
            out.append(name)
        else:
            stem, ext = os.path.splitext(name)
            out.append(f"{stem} ({seen[key]}){ext}")
    return out


def lecture_file_paths(section, lecture):
    """{id del recurso: ruta relativa} de los archivos descargables de la lección."""
    files = [r for r in lecture.resources if r.kind == "file"]
    names = unique_names([resource_filename(r) for r in files])
    folder = resource_dir(section, lecture)
    return {id(r): f"{folder}/{name}" for r, name in zip(files, names)}


def probe_size(client, url):
    """Tamaño total del archivo sin bajarlo (petición con `Range: bytes=0-0`)."""
    result = client.download_bytes(url, "el tamaño del recurso", headers={"Range": "bytes=0-0"})
    if not result.ok:
        return None
    total = re.search(r"/(\d+)\s*$", (result.headers or {}).get("content-range", ""))
    if total:
        return int(total.group(1))
    if result.status == 200:                       # el servidor ignoró Range
        return len(result.body)
    return None


def plan_resources(client, selected, manifest, course_dir, types=None, max_size=None,
                   log=print):
    """Qué archivos hay, cuáles faltan y cuánto pesan. `selected`: [(sección, lección)]."""
    plan = Plan()
    for section, lecture in selected:
        paths = lecture_file_paths(section, lecture)
        for res in lecture.resources:
            if res.kind != "file":
                continue
            item = Planned(lecture, section, res, paths[id(res)])
            if types and extension(item.rel) not in types:
                item.status = "type"
            elif res.id is not None and manifest.resource_done(res.id, item.rel, course_dir):
                item.status = "done"
            else:
                item.size = probe_size(client, res.url)
                if max_size and item.size is not None and item.size > max_size:
                    item.status = "big"
            plan.items.append(item)
    return plan


def summarize(plan, max_size=None):
    """Líneas de resumen para el usuario."""
    new = plan.to_download
    lines = []
    if new:
        size = f"{format_size(plan.total_bytes)}" + (
            f" + {plan.unknown_size} de tamaño desconocido" if plan.unknown_size else "")
        lines.append(f"  Recursos: {len(new)} archivo(s) por descargar ({size})")
    for status, text in (("done", "ya descargados"), ("type", "omitidos por tipo"),
                         ("big", f"omitidos por pasar de {format_size(max_size or 0)}")):
        n = len(plan.with_status(status))
        if n:
            lines.append(f"  Recursos: {n} {text}")
    risky = [p for p in new if extension(p.rel) in EXECUTABLE_EXTS]
    if risky:
        exts = ", ".join(sorted({"." + extension(p.rel) for p in risky}))
        lines.append(f"  ⚠ {len(risky)} ejecutable(s)/instalador(es) ({exts}): se guardan pero "
                     "nunca se ejecutan; revísalos antes de abrirlos.")
    return lines


def confirm(plan, assume_yes=False, threshold=CONFIRM_ABOVE, input_fn=input, log=print):
    """¿Seguir con la descarga? Pregunta solo si el total supera `threshold`."""
    if assume_yes or plan.total_bytes <= threshold:
        return True
    try:
        answer = input_fn(f"  El total ({format_size(plan.total_bytes)}) es grande. "
                          "¿Descargar los recursos? [s/N] ")
    except EOFError:
        raise UdemyError("Los recursos pesan "
                         f"{format_size(plan.total_bytes)} y no puedo preguntar sin una terminal "
                         "interactiva. Repite con --yes para aceptar o con --max-size para limitar.")
    return answer.strip().lower() in ("s", "si", "sí", "y", "yes")


def write_file(course_dir, rel, data):
    """Escribe de forma atómica (`.part` + renombrado): nunca queda un archivo a medias."""
    target = fs_path(Path(course_dir) / rel)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, target)
    except OSError as exc:
        raise UdemyError(f"No pude escribir {Path(course_dir) / rel}: {exc}")


def download_planned(client, item, manifest, course_dir, max_size=None, log=print):
    """Baja un archivo planificado; devuelve True si quedó guardado."""
    res = item.resource
    result = client.download_bytes(res.url, f"el recurso {posixpath.basename(item.rel)}")
    if not result.ok:
        hint = " (¿URL caducada?)" if result.status in (401, 403) else ""
        log(f"    ✗ {posixpath.basename(item.rel)}: HTTP {result.status}{hint}")
        return False
    if max_size and len(result.body) > max_size:
        log(f"    – {posixpath.basename(item.rel)}: pesa {format_size(len(result.body))}, "
            "más que --max-size; no se guarda")
        return False
    write_file(course_dir, item.rel, result.body)
    if res.id is not None:
        manifest.set_resource(res.id, {
            "file": item.rel, "size": len(result.body), "lecture": item.lecture.id,
            "title": res.title})
        manifest.save()
    warn = "  ⚠ ejecutable: no se ejecuta" if extension(item.rel) in EXECUTABLE_EXTS else ""
    log(f"    ✓ {item.rel}  ({format_size(len(result.body))}){warn}")
    return True


def image_name(url, taken):
    """Nombre local de una imagen de artículo (sin colisiones dentro de `taken`)."""
    base = safe_filename(posixpath.basename(unquote(urlparse(url).path)) or "imagen")
    if not extension(base):
        base += ".png"
    name, n = base, 1
    while name.lower() in taken:
        n += 1
        stem, ext = os.path.splitext(base)
        name = f"{stem} ({n}){ext}"
    taken.add(name.lower())
    return name


def download_images(client, section, lecture, urls, course_dir, max_size=None, log=print):
    """Baja las imágenes de un artículo; devuelve {url: ruta relativa al curso}."""
    saved, taken = {}, set()
    folder = f"{resource_dir(section, lecture)}/img"
    for url in urls:
        absolute = url if urlparse(url).scheme in ("http", "https") else None
        if not absolute:
            continue
        name = image_name(absolute, taken)
        if fs_path(Path(course_dir) / folder / name).is_file():      # ya la tenemos
            saved[url] = f"{folder}/{name}"
            continue
        result = client.download_bytes(absolute, "una imagen del artículo")
        if not result.ok or (max_size and len(result.body) > max_size):
            log(f"    ✗ imagen {name}: no se pudo bajar (HTTP {result.status}); "
                "se deja el enlace original")
            continue
        write_file(course_dir, f"{folder}/{name}", result.body)
        saved[url] = f"{folder}/{name}"
    return saved


def link_path(rel, prefix=""):
    """Ruta relativa para un enlace Markdown: segmentos codificados (espacios, tildes)."""
    return "/".join(quote(part) for part in (prefix + rel).split("/"))
