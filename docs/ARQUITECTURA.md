# Arquitectura de udemy-transcripts

> Estado: **Fase 4 (0.5.0)**. El diseño original de un solo script (`9a21915`) se reorganizó
> en un paquete; el plan de cambios está en [PLAN.md](PLAN.md) y la API en [API.md](API.md).

## Estructura

```
udemy_transcripts/
  cli.py          argumentos y orquestación: download_one (un curso) y download_path (una ruta)
  client.py       Client (navegador + portal), ApiResult, reintentos, errores por status, login
  portal.py       Portal: host (www / <org>.udemy.com) y URLs base
  courses.py      lista de cursos, URL/slug/id → course_id (validado con la API)
  curriculum.py   modelo Section/Lecture/Resource y lectura del temario (artículos y adjuntos incluidos)
  ranges.py       --sections/--lectures: `3-5,8,12-` → selector de lecciones
  html2md.py      HTML de los artículos → Markdown o texto plano (sin dependencias)
  resources.py    adjuntos: nombres, plan con tamaños, confirmación, descarga atómica, imágenes
  paths.py        rutas de aprendizaje (Business): cursos de la ruta e índice
  captions.py     parser WebVTT por bloques → Cue(start, end, text); elección de idioma
  paragraphs.py   cues → párrafos (pausa 2,5 s / ~400 car.) y qué párrafos llevan marca de tiempo
  manifest.py     .udemy-transcripts.json: estado por lección para --update y reanudar
  download.py     bucle de descarga: recursos → imágenes → ¿vigente? → render → escribe + manifest
  render/         common (opciones, tiempos), markdown (lección, artículo, README, enlaces, archivo único),
                  mdtext (escape), txt
  errors.py       UdemyError y subclases (el mensaje se muestra al usuario)
  util.py         safe_name y fs_path (rutas de más de 259 caracteres en Windows)
udemy_transcripts.py   envoltorio: `python udemy_transcripts.py` sigue funcionando
tests/                 pytest sin red (FakePage / FakeContext en conftest.py)
```

Solo depende de la librería estándar + **Playwright** (importado de forma diferida).

## Flujo

```
udemy <url|slug|id> [--format md|txt] [--single] [--update] [--lang] [--out] ...
   │
   ├─ 1. Portal: host de la URL › --business/UDEMY_BUSINESS › www.udemy.com (portal.choose_portal)
   ├─ 2. Chromium con perfil persistente (~/.cache/udemy-transcripts-profile), ventana visible
   │        · --token → cookie access_token (host del portal en Business, .udemy.com en www)
   ├─ 3. ensure_login()      GET users/me  → si no hay sesión, login manual + ENTER
   ├─ 4. resolve_course_id() subscribed-courses; si no, landing + candidatos validados con courses/<id>/
   ├─ 5. fetch_curriculum()  subscriber-curriculum-items (paginado) → [Section[Lecture]]
   ├─ 6. por cada lección de vídeo (download.py):
   │        pick_caption() → ¿vigente en el manifest? (--update) → download_text(.vtt)
   │        → parse_vtt() → build_paragraphs() → render markdown|txt → escribe + manifest.save()
   └─ 7. guarda  <out>/<curso>/<NN - sección>/<NNN - lección>.md|txt  + README.md + manifest
                (o <out>/<curso>.md|txt con --single / --txt)
```

## Capa de red

- `Client.get()` ejecuta `fetch()` **dentro de la página** (same-origin, con cookies), lo que
  atraviesa Cloudflare, y devuelve un `ApiResult(status, text, retry_after)`.
- `with_retries()` reintenta status 0 (red), 429 y 5xx con backoff exponencial (1, 2, 4 s…;
  `Retry-After` manda si existe). La página de verificación de Cloudflare no se reintenta.
- `raise_for_status()` traduce el status a un error con mensaje (`NotLoggedInError`,
  `AccessDeniedError`, `NotFoundError`, `BlockedError`, `ApiError`). La CLI los imprime y sale con 1.
- Los `.vtt` (CDN firmado) se bajan con `context.request.get`, también con reintentos.

## Tests

`FakePage.evaluate()` devuelve respuestas guiadas y `FakeContext.request.get()` sirve archivos,
así que todo el flujo (cliente, temario, resolución de curso, descarga) se prueba sin navegador.
Lo único que no cubren es el navegador real: ver la prueba manual de cada fase en el plan.

## Límites actuales

1. `--single`/`--txt` escribe el archivo al final: una interrupción pierde lo acumulado, y
   `--update` no aplica (hace falta el texto de todas las lecciones para recomponerlo).
2. `--update` decide por la huella del subtítulo (`file_name` del CDN) sin descargarlo; si Udemy
   cambiara el contenido sin cambiar ese nombre no lo detectaría (el hash del VTT se guarda, pero solo
   como referencia).
3. Los recursos se leen enteros en memoria (Playwright no hace streaming): por eso `--max-size`
   (500MB por defecto). Los tamaños se sondean con `Range: bytes=0-0`; si el servidor lo ignora se baja el archivo.
4. En una ruta de aprendizaje la confirmación de tamaño se pide por curso, no para toda la ruta.
