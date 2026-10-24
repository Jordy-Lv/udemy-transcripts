"""Cursos del usuario y resolución de URL/slug/id → course_id."""

import re
from collections import namedtuple

from .errors import ApiError, NotFoundError, UdemyError

CourseRef = namedtuple("CourseRef", "id slug")

_ID_PATTERNS = (
    r'data-clp-course-id="(\d+)"',      # el atributo de la landing: el más fiable
    r'"courseId"\s*:\s*(\d+)',
    r"courseId\D{0,8}(\d+)",
    r"/course/(\d+)/",
)


def list_courses(client):
    url = (f"{client.portal.api}/users/me/subscribed-courses/"
           "?fields%5Bcourse%5D=id,title,url&page_size=100&ordering=-last_accessed")
    return client.paginate(url, "tu lista de cursos")


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


def course_title(client, course_id):
    info = client.get_json(
        f"{client.portal.api}/courses/{course_id}/?fields%5Bcourse%5D=title",
        "el curso")
    return info.get("title") or f"curso-{course_id}"
