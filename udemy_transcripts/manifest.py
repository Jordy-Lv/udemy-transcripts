"""Estado de la descarga (`<curso>/.udemy-transcripts.json`) para `--update` y reanudar."""

import json
import os
import re
from collections import namedtuple
from pathlib import Path

from .util import fs_path

MANIFEST_NAME = ".udemy-transcripts.json"
VERSION = 1

_SECTION_DIR = re.compile(r"(\d+) - ")
_LECTURE_FILE = re.compile(r"(\d+) - (.*)\.(?:md|txt)$")

# Una lección ya escrita en disco: índice y carpeta de su sección, entrada del manifest,
# número y título sacados del nombre del archivo, ruta relativa y ruta absoluta.
Downloaded = namedtuple("Downloaded", "section_index dirname entry number name rel path")


def caption_signature(caption):
    """Identifica el archivo de subtítulos: cambia si el instructor lo vuelve a subir."""
    name = caption.get("file_name") or (caption.get("url") or "").split("?")[0]
    return f"{caption.get('locale_id') or ''}:{name}"


class Manifest:
    def __init__(self, path, course_id=None, entries=None, resources=None):
        self.path = Path(path)
        self.course_id = str(course_id) if course_id is not None else None
        self.entries = entries or {}          # id de lección (str) → dict
        self.resources = resources or {}      # id del recurso (str) → dict

    @classmethod
    def load(cls, path, course_id, log=print):
        """Carga el manifest; uno ausente, ilegible o de otro curso empieza vacío."""
        path = Path(path)
        try:
            data = json.loads(fs_path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls(path, course_id)
        except (OSError, ValueError):
            log(f"  ⚠ {path.name} está dañado; se empieza de cero.")
            return cls(path, course_id)
        if not isinstance(data, dict) or not isinstance(data.get("lectures"), dict):
            log(f"  ⚠ {path.name} no tiene el formato esperado; se empieza de cero.")
            return cls(path, course_id)
        if str(data.get("course_id")) != str(course_id):
            log(f"  ⚠ {path.name} es del curso {data.get('course_id')}, no del {course_id}; "
                "se ignora.")
            return cls(path, course_id)
        resources = data.get("resources")
        return cls(path, course_id, data["lectures"],
                   resources if isinstance(resources, dict) else {})

    def get(self, lecture_id):
        return self.entries.get(str(lecture_id))

    def set(self, lecture_id, entry):
        self.entries[str(lecture_id)] = entry

    def up_to_date(self, lecture, section, signature, rel_path, render, course_dir):
        """¿Se puede omitir la lección? Solo si nada de lo que afecta al archivo cambió.

        `signature` es la huella del contenido de origen: la del subtítulo en los
        vídeos y la del HTML en los artículos.
        """
        entry = self.get(lecture.id) if lecture.id else None
        return bool(
            entry
            and entry.get("caption") == signature
            and entry.get("file") == rel_path
            and entry.get("render") == render
            and entry.get("title") == lecture.title
            and entry.get("section") == section.title
            and fs_path(Path(course_dir) / rel_path).is_file())

    def downloaded(self, course_dir):
        """Las lecciones apuntadas cuyo archivo `NN - sección/NNN - título.ext` está en disco."""
        found = []
        for entry in self.entries.values():
            rel = entry.get("file") or ""
            parts = rel.split("/")
            if len(parts) != 2:
                continue
            dirname, name = parts
            m, n = _SECTION_DIR.match(dirname), _LECTURE_FILE.match(name)
            path = fs_path(Path(course_dir) / rel)
            if m and n and path.is_file():
                found.append(Downloaded(int(m.group(1)), dirname, entry, n.group(1), n.group(2),
                                        rel, path))
        return found

    # ---- recursos ------------------------------------------------------
    def resource_done(self, resource_id, rel_path, course_dir):
        """¿Ya está el archivo completo? (misma ruta y el tamaño apuntado coincide)."""
        entry = self.resources.get(str(resource_id))
        if not entry or entry.get("file") != rel_path:
            return False
        try:
            return fs_path(Path(course_dir) / rel_path).stat().st_size == entry.get("size")
        except OSError:
            return False

    def set_resource(self, resource_id, entry):
        self.resources[str(resource_id)] = entry

    def save(self):
        data = {"version": VERSION, "course_id": self.course_id, "lectures": self.entries,
                "resources": self.resources}
        tmp = fs_path(self.path.with_name(self.path.name + ".tmp"))
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, fs_path(self.path))
