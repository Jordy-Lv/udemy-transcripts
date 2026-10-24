"""Rutas de aprendizaje de Udemy Business: lista de cursos y su índice."""

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .errors import UdemyError
from .render.mdtext import md_escape
from .resources import link_path
from .util import safe_name

_PATH_RE = re.compile(r"/learning-paths?/(\d+)")

_SECTIONS_FIELDS = (
    "&fields%5Blearning_path_section%5D=id,title,description,items"
    "&fields%5Blearning_path_section_has_item%5D=id,title,description,related_object_type,"
    "estimated_content_length,content,is_removed"
    "&fields%5Bcourse_label%5D=id")


def learning_path_id(ref):
    """Id de una ruta si `ref` es la URL de una (`…/learning-paths/<id>/`); si no, None."""
    m = _PATH_RE.search(ref or "")
    return m.group(1) if m else None


@dataclass
class PathItem:
    kind: str                       # "course", "lab", "adaptive_assessment_assessment"…
    title: str
    course_id: Optional[str] = None
    slug: Optional[str] = None
    folder: str = ""                # carpeta del curso dentro de la ruta (si se descarga)
    status: str = ""                # ok | error | omitido | sin acceso…


@dataclass
class PathSection:
    title: str
    items: List[PathItem] = field(default_factory=list)


@dataclass
class LearningPath:
    id: str
    title: str
    description: str
    sections: List[PathSection]

    @property
    def courses(self):
        return [item for s in self.sections for item in s.items if item.kind == "course"]


def parse_path_sections(rows):
    sections = []
    for row in rows:
        section = PathSection(row.get("title") or "")
        for raw in row.get("items") or []:
            if raw.get("is_removed"):
                continue
            kind = raw.get("related_object_type") or "otro"
            content = raw.get("content") or {}
            title = raw.get("title") or content.get("title") or ""
            if kind == "course" and content.get("id"):
                m = re.search(r"/course/([^/?#]+)", content.get("url") or "")
                section.items.append(PathItem(kind, title, str(content["id"]),
                                              m.group(1) if m else None))
            else:
                section.items.append(PathItem(kind, title))
        if section.items:
            sections.append(section)
    return sections


def fetch_learning_path(client, path_id):
    api = f"{client.portal.api}/learning-paths/{path_id}/"
    info = client.get_json(api, "la ruta de aprendizaje")
    rows = client.paginate(f"{api}sections/?page_size=9999{_SECTIONS_FIELDS}",
                           "los cursos de la ruta")
    path = LearningPath(str(path_id), info.get("title") or f"ruta-{path_id}",
                        info.get("description") or "", parse_path_sections(rows))
    if not path.courses:
        raise UdemyError(f"La ruta «{path.title}» no tiene cursos que descargar.")
    return path


def course_folder(number, title):
    return f"{number:02d} - {safe_name(title)}"


_KIND_NAMES = {"lab": "laboratorio", "adaptive_assessment_assessment": "evaluación",
               "course": "curso"}


def path_index(path, portal_base):
    """`README.md` de la ruta: secciones y cursos (con enlace a su carpeta)."""
    lines = [f"# {md_escape(path.title)}", "", f"[Abrir la ruta en Udemy]"
             f"({portal_base}/learning-paths/{path.id}/)"]
    if path.description:
        lines += ["", md_escape(path.description.strip())]
    for section in path.sections:
        lines += ["", f"## {md_escape(section.title or 'Cursos')}", ""]
        for item in section.items:
            name = md_escape(item.title or "(sin título)")
            if item.kind != "course":
                lines.append(f"- {name} — {_KIND_NAMES.get(item.kind, item.kind)}: "
                             "no se descarga")
            elif item.status == "ok" and item.folder:
                lines.append(f"- [{name}]({link_path(item.folder)}/)")
            else:
                lines.append(f"- {name} — {item.status or 'pendiente'}")
    return "\n".join(lines) + "\n"
