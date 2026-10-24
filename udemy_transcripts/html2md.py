"""HTML de los artículos de Udemy → Markdown (o texto plano), sin dependencias."""

import re
from html.parser import HTMLParser

from .render.mdtext import escape_inline, guard_block_start

_BLOCKS = {"p", "div", "section", "article", "header", "footer", "figure", "figcaption",
           "dl", "dt", "dd", "center"}
_HEADINGS = {f"h{n}": n for n in range(1, 7)}
_SKIP = {"script", "style", "head", "title", "svg", "iframe", "noscript"}
_LANG = re.compile(r"(?:language|lang)-([\w+#-]+)")
_EMPHASIS = {"strong": "**", "b": "**", "em": "*", "i": "*", "code": "`"}


class _Converter(HTMLParser):
    """Un convertidor de un solo uso: `feed()` y luego `result()`."""

    def __init__(self, image_map=None, plain=False, heading_shift=1):
        super().__init__(convert_charrefs=True)
        self.image_map = image_map or {}
        self.plain = plain
        self.shift = heading_shift
        self.blocks = []          # (tipo, texto); los "li" consecutivos se unen con salto simple
        self.buf = []             # fragmentos de la línea en curso
        self.lists = []           # pila de [tipo, contador]
        self.li_prefix = None     # marcador del <li> abierto
        self.heading = None
        self.pre = None           # None o {"lang": str, "parts": []}
        self.skip = 0
        self.links = []           # pila de (href, posición en buf)
        self.table = None         # {"rows": [], "row": None, "cell": None}
        self.quote = 0
        self.marks = []           # posiciones de las marcas de énfasis abiertas
        self.code = 0             # dentro de `código` en línea: el texto va sin escapar

    # ---- utilidades ---------------------------------------------------
    def _emit(self, kind, text):
        if text:
            self.blocks.append((kind, text))

    def _take(self):
        text = "".join(self.buf)
        self.buf = []
        self.marks = []
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r" ?([\n\x01]) ?", r"\1", text).strip(" \n\x01")
        return text.replace("\x01", "\n" if self.plain else "  \n")

    def _flush(self):
        text = self._take()
        if not text:
            return
        if self.heading:
            level = min(6, self.heading + self.shift)
            text = text.replace("\n", " ")
            self._emit("h", text if self.plain else "#" * level + " " + text)
        elif self.li_prefix is not None:
            pad = " " * len(self.li_prefix)
            self._emit("li", self.li_prefix + text.replace("\n", "\n" + pad))
            self.li_prefix = pad                    # párrafos siguientes del mismo <li>
        else:
            text = text if self.plain else guard_block_start(text)
            if self.quote and not self.plain:
                text = "\n".join("> " + line for line in text.split("\n"))
            self._emit("p", text)

    def _text(self, data):
        raw = self.plain or self.code
        self.buf.append(data.replace("`", "'") if self.code and not self.plain else
                        data if raw else escape_inline(data))

    def _open(self, mark):
        if mark != "`" and (self.code or self.heading):
            self.marks.append(-1)           # negrita/cursiva dentro de código o título: se omite
            return
        self.buf.append(mark)
        self.marks.append(len(self.buf) - 1)

    def _close(self, mark):
        """Cierra `mark` sin dejar espacios dentro («**a **b» no es negrita en Markdown)."""
        start = self.marks.pop() if self.marks else None
        if start == -1:
            return
        tail = ""
        while self.buf and (start is None or len(self.buf) - 1 > start):
            piece = self.buf[-1]
            if piece.strip(" \n") == "":
                tail = self.buf.pop() + tail
            elif piece.endswith(" "):
                self.buf[-1] = piece.rstrip(" ")
                tail = piece[len(self.buf[-1]):] + tail
                break
            else:
                break
        if start is not None and len(self.buf) - 1 == start:       # énfasis vacío
            self.buf.pop()
        else:
            self.buf.append(mark)
        if tail:
            self.buf.append(tail)

    # ---- eventos -------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in _SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if self.pre is not None:
            if tag == "code":
                m = _LANG.search(attrs.get("class") or "")
                if m and not self.pre["lang"]:
                    self.pre["lang"] = m.group(1)
            elif tag == "br":
                self.pre["parts"].append("\n")
            return
        if tag == "pre":
            self._flush()
            m = _LANG.search(attrs.get("class") or "")
            self.pre = {"lang": m.group(1) if m else "", "parts": []}
        elif tag in _HEADINGS:
            self._flush()
            self.heading = _HEADINGS[tag]
        elif tag in ("ul", "ol"):
            self._flush()
            self.lists.append([tag, int(attrs.get("start") or 1) - 1])
        elif tag == "li":
            self._flush()
            kind = self.lists[-1] if self.lists else ["ul", 0]
            if kind[0] == "ol":
                kind[1] += 1
                marker = f"{kind[1]}. "
            else:
                marker = "- "
            self.li_prefix = "  " * max(0, len(self.lists) - 1) + marker
        elif tag == "blockquote":
            self._flush()
            self.quote += 1
        elif tag == "table":
            self._flush()
            self.table = {"rows": [], "row": None, "cell": None}
        elif tag == "tr":
            if self.table is not None:
                self.table["row"] = []
        elif tag in ("td", "th"):
            if self.table is not None:
                self._take()
                self.table["cell"] = True
        elif tag == "br":
            self.buf.append("\x01")             # salto duro; se resuelve en _take()
        elif tag == "hr":
            self._flush()
            self._emit("p", "-" * 20 if self.plain else "---")
        elif tag in _EMPHASIS and not self.plain:
            self.code += tag == "code"
            self._open(_EMPHASIS[tag])
        elif tag == "a":
            self.links.append((attrs.get("href") or "", len(self.buf)))
            if not self.plain:
                self.buf.append("[")
        elif tag == "img":
            src = attrs.get("src") or ""
            alt = (attrs.get("alt") or "").strip()
            if self.plain:
                self.buf.append(f"[imagen: {alt}]" if alt else "[imagen]")
            elif src:
                self.buf.append(f"![{escape_inline(alt)}]({self.image_map.get(src, src)})")
        elif tag in _BLOCKS:
            self._flush()

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if self.pre is not None:
            if tag == "pre":
                self._end_pre()
            return
        if tag in _HEADINGS:
            self._flush()
            self.heading = None
        elif tag in ("ul", "ol"):
            self._flush()
            if self.lists:
                self.lists.pop()
            if not self.lists:
                self.li_prefix = None
                self.blocks.append(("sep", ""))     # la lista siguiente no se pega a esta
        elif tag == "li":
            self._flush()
            self.li_prefix = None
        elif tag == "blockquote":
            self._flush()
            self.quote = max(0, self.quote - 1)
        elif tag in ("td", "th"):
            if self.table is not None and self.table["row"] is not None:
                self.table["row"].append(self._take().replace("\n", " "))
                self.table["cell"] = None
        elif tag == "tr":
            if self.table is not None:
                if self.table["row"]:
                    self.table["rows"].append(self.table["row"])
                self.table["row"] = None
        elif tag == "table":
            if self.table is not None:
                self._emit_table()
                self.table = None
        elif tag in _EMPHASIS and not self.plain:
            if tag == "code":
                self.code = max(0, self.code - 1)
            self._close(_EMPHASIS[tag])
        elif tag == "a":
            href, start = self.links.pop() if self.links else ("", len(self.buf))
            if self.plain:
                if href and "".join(self.buf[start:]).strip() != href:
                    self.buf.append(f" ({href})")
            else:
                self.buf.append(f"]({href})" if href else "]")
        elif tag in _BLOCKS:
            self._flush()

    def handle_data(self, data):
        if self.skip:
            return
        if self.pre is not None:
            self.pre["parts"].append(data)
            return
        data = re.sub(r"\s+", " ", data)
        if self.table is not None and self.table["cell"] is None and not data.strip():
            return
        self._text(data)

    def _end_pre(self):
        code = "".join(self.pre["parts"]).strip("\n").rstrip()
        lang, self.pre = self.pre["lang"], None
        if not code:
            return
        if self.plain:
            self._emit("p", "\n".join("    " + line for line in code.split("\n")))
        else:
            fence = "````" if "```" in code else "```"
            self._emit("p", f"{fence}{lang}\n{code}\n{fence}")

    def _emit_table(self):
        rows = self.table["rows"]
        if not rows:
            return
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        if self.plain:
            self._emit("p", "\n".join(" | ".join(r) for r in rows))
            return

        def line(row):
            return "| " + " | ".join(c.replace("|", "\\|") for c in row) + " |"

        lines = [line(rows[0]), "| " + " | ".join("---" for _ in range(width)) + " |"]
        self._emit("p", "\n".join(lines + [line(r) for r in rows[1:]]))

    def result(self):
        if self.pre is not None:                 # <pre> sin cerrar
            self._end_pre()
        self._flush()
        out, prev = [], None
        for kind, text in self.blocks:
            if kind == "sep":
                prev = "sep"
                continue
            if prev is not None:
                out.append("\n" if kind == "li" and prev == "li" else "\n\n")
            out.append(text)
            prev = kind
        return "".join(out).strip() + "\n" if out else ""


def html_to_markdown(html, image_map=None, plain=False, heading_shift=1):
    """Convierte el HTML de un artículo.

    `image_map`: {src original: ruta local} para reescribir las imágenes.
    `plain`: texto sin marcas de Markdown (para `--format txt`).
    `heading_shift`: los títulos bajan ese nº de niveles (la lección ya tiene su `#`).
    """
    conv = _Converter(image_map, plain, heading_shift)
    conv.feed(html or "")
    conv.close()
    return conv.result()


def extract_images(html):
    """URLs de las imágenes de un artículo, en orden y sin repetir."""
    found = []
    for src in re.findall(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", html or "", re.I):
        if src not in found:
            found.append(src)
    return found
