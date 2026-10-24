# Arquitectura de udemy-transcripts

> Estado: **Fase 2 (0.3.0)**. El diseño original de un solo script (`9a21915`) se reorganizó
> en un paquete; el plan de cambios está en [PLAN.md](PLAN.md) y la API en [API.md](API.md).

## Estructura

```
udemy_transcripts/
  cli.py          argumentos, orquestación, descarga y guardado
  client.py       Client (navegador + portal), ApiResult, reintentos, errores por status, login
  portal.py       Portal: host (www / <org>.udemy.com) y URLs base
  courses.py      lista de cursos, URL/slug/id → course_id (validado con la API)
  curriculum.py   modelo Section/Lecture y lectura del temario
  captions.py     parser WebVTT por bloques → Cue(start, end, text); elección de idioma
  render/txt.py   texto plano: una oración por línea, ajuste de ancho, archivo único
  errors.py       UdemyError y subclases (el mensaje se muestra al usuario)
  util.py         safe_name
udemy_transcripts.py   envoltorio: `python udemy_transcripts.py` sigue funcionando
tests/                 pytest sin red (FakePage / FakeContext en conftest.py)
```

Solo depende de la librería estándar + **Playwright** (importado de forma diferida).

## Flujo

```
udemy <url|slug|id> [--txt] [--lang] [--out] ...
   │
   ├─ 1. Portal: host de la URL › --business/UDEMY_BUSINESS › www.udemy.com (portal.choose_portal)
   ├─ 2. Chromium con perfil persistente (~/.cache/udemy-transcripts-profile), ventana visible
   │        · --token → cookie access_token (host del portal en Business, .udemy.com en www)
   ├─ 3. ensure_login()      GET users/me  → si no hay sesión, login manual + ENTER
   ├─ 4. resolve_course_id() subscribed-courses; si no, landing + candidatos validados con courses/<id>/
   ├─ 5. fetch_curriculum()  subscriber-curriculum-items (paginado) → [Section[Lecture]]
   ├─ 6. por cada lección de vídeo:
   │        pick_caption() → download_text(.vtt) → parse_vtt() → cues_to_text()
   └─ 7. guarda  <out>/<curso>/<NN - sección>/<NNN - lección>.txt   (o <out>/<curso>.txt con --txt)
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

1. El formato de salida es solo `.txt` (Markdown, marcas de tiempo y `--update` llegan en la Fase 3).
2. El modo `--txt` escribe al final: una interrupción pierde lo acumulado (la reanudación llega con el manifest).
