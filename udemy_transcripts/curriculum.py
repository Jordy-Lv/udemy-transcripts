"""Temario del curso: modelo de secciones, lecciones y recursos."""

from dataclasses import dataclass, field
from typing import List, Optional

from .errors import AccessDeniedError
from .util import safe_name

_FIELDS = (
    "&fields%5Blecture%5D=title,object_index,asset,supplementary_assets"
    "&fields%5Bchapter%5D=title,object_index"
    "&fields%5Basset%5D=asset_type,captions,title,time_estimation,body,filename,"
    "download_urls,external_url"
    "&fields%5Bcaption%5D=url,locale_id,video_label,file_name,source"
)


@dataclass
class Resource:
    """Adjunto de una lección: un archivo descargable o un enlace externo."""
    id: Optional[int]
    kind: str                       # "file" | "link"
    title: str
    filename: str
    url: str                        # descarga firmada (file) o enlace externo (link)
    asset_type: str = ""


@dataclass
class Lecture:
    id: Optional[int]
    title: str
    index: Optional[int]
    asset_type: Optional[str]
    captions: list = field(default_factory=list)
    duration: Optional[int] = None          # segundos (vídeo) o tiempo de lectura (artículo)
    body: str = ""                          # HTML del artículo
    resources: List[Resource] = field(default_factory=list)

    @property
    def is_video(self):
        return self.asset_type == "Video"

    @property
    def is_article(self):
        return self.asset_type == "Article"

    @property
    def number(self):
        return f"{self.index:03d}" if isinstance(self.index, int) else "000"


@dataclass
class Section:
    index: int
    title: str
    lectures: List[Lecture] = field(default_factory=list)

    @property
    def dirname(self):
        return f"{self.index:02d} - {safe_name(self.title)}"


def _best_download(download_urls):
    """URL de descarga de un asset: `File` si existe; si no, la de mayor calidad."""
    if not isinstance(download_urls, dict) or not download_urls:
        return ""
    entries = download_urls.get("File") or next(iter(download_urls.values()))
    entries = [e for e in entries or [] if isinstance(e, dict) and e.get("file")]

    def quality(entry):
        label = str(entry.get("label") or "")
        return int(label) if label.isdigit() else 0

    return max(entries, key=quality)["file"] if entries else ""


def parse_resource(asset):
    """Asset de `supplementary_assets` → Resource (None si no hay nada utilizable)."""
    if not isinstance(asset, dict):
        return None
    title = asset.get("title") or asset.get("filename") or ""
    if asset.get("asset_type") == "ExternalLink":
        url = asset.get("external_url") or ""
        return Resource(asset.get("id"), "link", title or url, "", url, "ExternalLink") \
            if url else None
    url = _best_download(asset.get("download_urls"))
    if not url:
        return None
    return Resource(asset.get("id"), "file", title, asset.get("filename") or title, url,
                    asset.get("asset_type") or "")


def parse_curriculum(items):
    """Items de la API → secciones con sus lecciones (los quiz se ignoran)."""
    sections, current = [], None
    for it in items:
        klass = it.get("_class")
        if klass == "chapter":
            current = Section(it.get("object_index") or 0, it.get("title") or "")
            sections.append(current)
        elif klass == "lecture":
            if current is None:       # lección antes de cualquier capítulo
                current = Section(0, "General")
                sections.append(current)
            asset = it.get("asset") or {}
            lecture = Lecture(
                id=it.get("id"), title="", index=it.get("object_index"),
                asset_type=asset.get("asset_type"),
                captions=asset.get("captions") or [],
                duration=asset.get("time_estimation"),
                body=asset.get("body") or "",
                resources=[r for r in map(parse_resource, it.get("supplementary_assets") or [])
                           if r])
            lecture.title = it.get("title") or f"leccion-{lecture.number}"
            current.lectures.append(lecture)
    return sections


def fetch_curriculum(client, course_id):
    url = (f"{client.portal.api}/courses/{course_id}/subscriber-curriculum-items/"
           f"?page_size=200{_FIELDS}")
    try:
        items = client.paginate(url, "el temario del curso")
    except AccessDeniedError:
        if not client.portal.is_business:
            raise
        raise AccessDeniedError(
            "Sin acceso al temario del curso (HTTP 403). En Udemy Business hay que "
            f"inscribirse una vez: abre el curso en {client.portal.base} y pulsa "
            "«Empezar curso»; luego repite.")
    return parse_curriculum(items)
