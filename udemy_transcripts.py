#!/usr/bin/env python3
"""
udemy_transcripts.py — Descarga las transcripciones (subtítulos) de todos los
videos de un curso de Udemy personal y las guarda como .txt limpio.

Usa un navegador real (Playwright) para reutilizar tu sesión y atravesar la
protección Cloudflare de Udemy, que bloquea las peticiones con curl/urllib.

── Instalación (una sola vez) ───────────────────────────────────────────────
    pip3 install playwright
    python3 -m playwright install chromium
  (Si tu Python da "externally-managed-environment", usa un venv:
     python3 -m venv ~/.venvs/udemy && source ~/.venvs/udemy/bin/activate
     pip install playwright && python -m playwright install chromium )

── Uso ──────────────────────────────────────────────────────────────────────
    udemy "https://www.udemy.com/course/mi-curso/"        # un .txt por video
    udemy --txt "https://www.udemy.com/course/mi-curso/"  # todo en un solo .txt

  • Por defecto crea  ~/Udemy-Transcripts/<curso>/<NN - sección>/  y dentro un
    archivo "NNN - título.txt" por video, con la misma numeración que Udemy.
  • Con --txt genera un único  ~/Udemy-Transcripts/<curso>.txt  con todo el
    curso concatenado.

  La PRIMERA vez se abre una ventana de Chromium: inicia sesión en Udemy ahí.
  La sesión queda guardada en un perfil propio, así que las siguientes veces
  ya no tendrás que volver a loguearte.

── Opciones ─────────────────────────────────────────────────────────────────
    --txt          todo el curso en UN solo .txt (en vez de uno por video)
    --list         lista tus cursos suscritos (con su id) y termina
    --token TOK    access_token de la cookie; evita el login manual (o env UDEMY_TOKEN)
    --lang  CODE   idioma preferido del subtítulo: es, en, pt… (default: es,en)
    --out   DIR    carpeta base de salida (default: ~/Udemy-Transcripts o $UDEMY_OUT)
    --width N      ancho de línea del texto; 0 = sin ajustar (default 100)
    --headless     NO recomendado: Udemy bloquea el modo headless (Cloudflare)
"""

import argparse
import html
import json
import os
import re
import sys
import textwrap
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("✗ Falta Playwright. Instálalo con:\n"
             "    pip3 install playwright\n"
             "    python3 -m playwright install chromium")

API = "https://www.udemy.com/api-2.0"
PROFILE_DIR = Path.home() / ".cache" / "udemy-transcripts-profile"


def goto_cf(page, url, wait=20):
    """Navega y espera a que Cloudflare resuelva su challenge si aparece."""
    page.goto(url, wait_until="domcontentloaded")
    for _ in range(wait):
        if "just a moment" not in (page.title() or "").lower():
            return
        time.sleep(1)


def api_get(page, url):
    """fetch same-origin desde la página real → atraviesa Cloudflare, da JSON."""
    txt = page.evaluate(
        """async (u) => {
            const r = await fetch(u, {headers: {'Accept': 'application/json'},
                                      credentials: 'include'});
            return await r.text();
        }""", url)
    try:
        return json.loads(txt)
    except (json.JSONDecodeError, TypeError):
        return None


def _logged_user(page):
    me = api_get(page, f"{API}/users/me/?fields%5Buser%5D=title")
    if me and isinstance(me.get("id"), int) and me["id"] > 0:
        return me
    return None


def ensure_login(page):
    goto_cf(page, "https://www.udemy.com/")
    me = _logged_user(page)
    if me:
        print(f"  ✓ Sesión activa: {me.get('title') or me.get('id')}")
        return
    print("\n▶ Inicia sesión en la ventana de Chromium que se abrió.")
    input("  Cuando ya estés dentro de tu cuenta, vuelve aquí y pulsa ENTER… ")
    goto_cf(page, "https://www.udemy.com/")
    me = _logged_user(page)
    if not me:
        sys.exit("✗ No detecto sesión iniciada. Vuelve a intentarlo.")
    print(f"  ✓ Sesión activa: {me.get('title') or me.get('id')}")


def list_courses(page):
    url = (f"{API}/users/me/subscribed-courses/"
           "?fields%5Bcourse%5D=id,title,url&page_size=100&ordering=-last_accessed")
    rows = []
    while url:
        data = api_get(page, url)
        if not data:
            sys.exit("✗ No pude leer tus cursos.")
        rows.extend(data.get("results", []))
        url = data.get("next")
    print(f"\nTienes {len(rows)} cursos:\n")
    for c in rows:
        print(f"  [{c['id']}] {c['title']}")
    print("\nDescarga uno con:  udemy <id-o-URL>")


def resolve_course_id(page, arg):
    if arg.isdigit():
        return arg
    m = re.search(r"/course/([^/?#]+)", arg)
    slug = m.group(1) if m else arg.strip("/").split("/")[-1]
    # 1) buscar el slug entre tus cursos inscritos (robusto, vía API)
    url = (f"{API}/users/me/subscribed-courses/"
           "?fields%5Bcourse%5D=id,url&page_size=100")
    while url:
        data = api_get(page, url)
        if not data:
            break
        for c in data.get("results", []):
            curl = c.get("url") or ""
            if f"/course/{slug}/" in curl or curl.rstrip("/").endswith("/" + slug):
                return str(c["id"])
        url = data.get("next")
    # 2) fallback: parsear el HTML de la landing del curso
    goto_cf(page, f"https://www.udemy.com/course/{slug}/")
    content = page.content()
    for pat in (r'data-clp-course-id="(\d+)"', r'courseId\D{0,8}(\d+)',
                r'/course/(\d+)/'):
        m = re.search(pat, content)
        if m:
            return m.group(1)
    sys.exit("✗ No pude resolver el course_id. Usa  udemy --list  para ver el id "
             "y pásalo directo:  udemy <id>.")


def fetch_curriculum(page, course_id):
    fields = (
        "&fields%5Blecture%5D=title,object_index,asset"
        "&fields%5Bchapter%5D=title,object_index"
        "&fields%5Basset%5D=asset_type,captions,title"
        "&fields%5Bcaption%5D=url,locale_id,video_label,file_name"
    )
    url = (f"{API}/courses/{course_id}/subscriber-curriculum-items/"
           f"?page_size=200{fields}")
    items = []
    while url:
        data = api_get(page, url)
        if not data:
            sys.exit("✗ No pude leer el temario (¿estás inscrito en el curso?).")
        items.extend(data.get("results", []))
        url = data.get("next")
    return items


def pick_caption(captions, langs):
    if not captions:
        return None
    for want in langs:
        for c in captions:
            if (c.get("locale_id") or "").lower().startswith(want.lower()):
                return c
    return captions[0]


def vtt_to_text(vtt, width=100):
    lines = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if (not line or line == "WEBVTT" or "-->" in line or line.isdigit()
                or line.startswith(("NOTE", "STYLE", "Kind:", "Language:"))):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = html.unescape(line).strip()
        if line and (not lines or lines[-1] != line):
            lines.append(line)
    text = re.sub(r"\s+", " ", " ".join(lines)).strip()
    # una oración por bloque (si hay puntuación) y ajuste de línea para leer cómodo
    text = re.sub(r"(?<=[.!?])\s+", "\n", text)
    if width and width > 0:
        text = "\n".join(textwrap.fill(p, width) if p else "" for p in text.split("\n"))
    return text


def safe_name(name):
    name = re.sub(r'[/\\:*?"<>|]', "-", name or "").strip()
    return re.sub(r"\s+", " ", name)[:120]


def main():
    ap = argparse.ArgumentParser(description="Transcripciones de un curso de Udemy.")
    ap.add_argument("course", nargs="?", help="URL del curso, slug o course_id numérico")
    ap.add_argument("--list", action="store_true", dest="do_list",
                    help="lista tus cursos suscritos y termina")
    ap.add_argument("--token", default=os.environ.get("UDEMY_TOKEN"),
                    help="access_token de la cookie (evita el login manual)")
    ap.add_argument("--lang", default="es,en")
    ap.add_argument("--out", default=None,
                    help="carpeta base (default ~/Proyectos/learning/udemy)")
    ap.add_argument("--txt", action="store_true",
                    help="todo el curso en UN solo .txt (en vez de uno por video)")
    ap.add_argument("--width", type=int, default=100,
                    help="ancho de línea del texto; 0 = sin ajustar (default 100)")
    ap.add_argument("--headless", action="store_true",
                    help="(NO recomendado: Udemy bloquea el modo headless con Cloudflare)")
    args = ap.parse_args()
    if args.headless:
        print("⚠ Aviso: Udemy suele bloquear el modo headless (Cloudflare). "
              "Si falla, ejecútalo sin --headless.")
    if not args.do_list and not args.course:
        ap.error("indica la URL/ID del curso, o usa --list para ver tus cursos.")
    langs = [x.strip() for x in args.lang.split(",") if x.strip()]

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=args.headless,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"])
        if args.token:
            context.add_cookies([{
                "name": "access_token", "value": args.token,
                "domain": ".udemy.com", "path": "/", "secure": True,
            }])
        page = context.pages[0] if context.pages else context.new_page()

        print("• Comprobando sesión…")
        ensure_login(page)

        if args.do_list:
            list_courses(page)
            context.close()
            return

        print("• Resolviendo curso…")
        course_id = resolve_course_id(page, args.course)
        info = api_get(page, f"{API}/courses/{course_id}/?fields%5Bcourse%5D=title")
        title = (info or {}).get("title", f"curso-{course_id}")
        print(f"  → {title} (id {course_id})")

        udemy_dir = Path(args.out) if args.out else Path(
            os.environ.get("UDEMY_OUT") or Path.home() / "Udemy-Transcripts")
        udemy_dir.mkdir(parents=True, exist_ok=True)
        course_dir = udemy_dir / safe_name(title)
        if not args.txt:                       # modo separado: carpeta del curso
            course_dir.mkdir(parents=True, exist_ok=True)

        print("• Leyendo temario…")
        items = fetch_curriculum(page, course_id)

        saved, skipped, parts = 0, 0, []
        section = "00 - General"
        for it in items:
            klass = it.get("_class")
            if klass == "chapter":
                ci = it.get("object_index") or 0
                section = f"{ci:02d} - {safe_name(it.get('title'))}"
                continue
            if klass != "lecture":
                continue
            asset = it.get("asset") or {}
            if asset.get("asset_type") != "Video":
                continue
            li = it.get("object_index")
            num = f"{li:03d}" if isinstance(li, int) else "000"
            ltitle = safe_name(it.get("title", f"leccion-{num}"))
            cap = pick_caption(asset.get("captions") or [], langs)
            if not cap or not cap.get("url"):
                print(f"  – [{num}] sin subtítulos: {ltitle}")
                skipped += 1
                continue
            r = context.request.get(cap["url"])
            if not r.ok:
                print(f"  – [{num}] no se pudo bajar el subtítulo: {ltitle}")
                skipped += 1
                continue
            text = vtt_to_text(r.text(), args.width)
            if args.txt:                       # acumular para el archivo único
                parts.append(f"{'='*70}\n[{num}] {section} — {ltitle}\n{'='*70}\n\n{text}")
            else:                              # un .txt por video, en la carpeta de su sección
                sec_dir = course_dir / section
                sec_dir.mkdir(parents=True, exist_ok=True)
                (sec_dir / f"{num} - {ltitle}.txt").write_text(text + "\n", encoding="utf-8")
            print(f"  ✓ [{num}] {ltitle}  ({cap.get('locale_id')})")
            saved += 1
            time.sleep(0.15)

        context.close()
        print(f"\n✓ Listo: {saved} transcripciones, {skipped} sin subtítulos.")
        if args.txt:
            single = udemy_dir / f"{safe_name(title)}.txt"
            single.write_text(f"{title}\n\n" + "\n\n".join(parts) + "\n", encoding="utf-8")
            print(f"  Archivo: {single}")
        else:
            print(f"  Carpeta: {course_dir}")


if __name__ == "__main__":
    main()
