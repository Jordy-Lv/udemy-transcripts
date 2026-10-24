"""Cursos del usuario y resolución de URL/slug/id → course_id."""

import re
from collections import namedtuple
from dataclasses import dataclass
from typing import Optional

from .errors import AccessDeniedError, ApiError, NotFoundError, UdemyError

CourseRef = namedtuple("CourseRef", "id slug")

_ID_PATTERNS = (
    r'data-clp-course-id="(\d+)"',      # el atributo de la landing: el más fiable
    r'"courseId"\s*:\s*(\d+)',
    r"courseId\D{0,8}(\d+)",
    r"/course/(\d+)/",
)


def _course_of(row):
    """Curso de una fila de inscripción (el curso mismo o anidado en `course`)."""
    course = row.get("course") if isinstance(row.get("course"), dict) else row
    return course if course.get("id") and course.get("title") else None


def list_courses(client):
    """Cursos del usuario; en Business se suman las inscripciones de la suscripción."""
    api = client.portal.api
    rows = client.paginate(
        f"{api}/users/me/subscribed-courses/"
        "?fields%5Bcourse%5D=id,title,url&page_size=100&ordering=-last_accessed",
        "tu lista de cursos")
    if client.portal.is_business:
        seen = {c.get("id") for c in rows}
        try:
            extra = client.paginate(
                f"{api}/users/me/subscription-course-enrollments/?page_size=100",
                "tus inscripciones de Business")
        except (ApiError, NotFoundError, AccessDeniedError):
            extra = []            # endpoint auxiliar: su ausencia no impide listar
        for row in extra:
            course = _course_of(row)
            if course and course["id"] not in seen:
                seen.add(course["id"])
                rows.append(course)
    return rows


def parse_course_ref(arg):
    arg = arg.strip()
    if arg.isdigit():
        return CourseRef(arg, None)
    m = re.search(r"/course/([^/?#]+)", arg)
    return CourseRef(None, m.group(1) if m else arg.strip("/").split("/")[-1])


def url_matches_slug(url, slug):
    url = url or ""
    return f"/course/{slug}/" in url or url.rstrip("/").endswith("/" + slug)


def extract_course_id_candidates(html):
    """Ids que aparecen en el HTML, en orden de fiabilidad y sin repetir."""
    found = []
    for pattern in _ID_PATTERNS:
        for m in re.finditer(pattern, html):
            if m.group(1) not in found:
                found.append(m.group(1))
    return found


def _course_slug_matches(client, course_id, slug):
    """Valida con la API que `course_id` es el curso del slug."""
    result = client.get(
        f"{client.portal.api}/courses/{course_id}/?fields%5Bcourse%5D=url", "el curso")
    data = result.json() if result.ok else None
    return isinstance(data, dict) and url_matches_slug(data.get("url"), slug)


def resolve_course_id(client, arg):
    ref = parse_course_ref(arg)
    if ref.id:
        return ref.id
    slug = ref.slug
    # 1) entre los cursos del usuario (vía API)
    try:
        for course in list_courses(client):
            if url_matches_slug(course.get("url"), slug):
                return str(course["id"])
    except (ApiError, NotFoundError):
        pass                      # se prueba la landing; otros errores sí se propagan
    # 2) landing del curso: candidatos validados contra la API
    client.goto(f"/course/{slug}/")
    for candidate in extract_course_id_candidates(client.page.content()):
        if _course_slug_matches(client, candidate, slug):
            return candidate
    raise UdemyError("No pude resolver el course_id. Usa  udemy --list  para ver el "
                     "id y pásalo directo:  udemy <id>.")


@dataclass
class CourseInfo:
    id: str
    title: str
    slug: Optional[str]
    base: str                 # https://<host> del portal

    @property
    def url(self):
        return f"{self.base}/course/{self.slug}/" if self.slug else None

    def lecture_url(self, lecture_id, start=None):
        """Enlace a una lección (y a un segundo concreto con `start`)."""
        if not (self.slug and lecture_id):
            return None
        url = f"{self.base}/course/{self.slug}/learn/lecture/{lecture_id}"
        return url if start is None else f"{url}?start={int(start)}"


def course_info(client, course_id):
    data = client.get_json(
        f"{client.portal.api}/courses/{course_id}/?fields%5Bcourse%5D=title,url",
        "el curso")
    m = re.search(r"/course/([^/?#]+)", data.get("url") or "")
    return CourseInfo(str(course_id), data.get("title") or f"curso-{course_id}",
                      m.group(1) if m else None, client.portal.base)
