# Arquitectura de udemy-transcripts

> Estado: versión inicial (`9a21915`), analizada el 2026-10-24.

Todo vive en un único script, [`udemy_transcripts.py`](../udemy_transcripts.py) (~310 líneas),
que solo depende de la librería estándar + **Playwright**.

## Flujo

```
udemy <url|slug|id> [--txt] [--lang] [--out] ...
   │
   ├─ 1. Abre Chromium con perfil persistente (~/.cache/udemy-transcripts-profile)
   │     · ventana visible: Cloudflare bloquea headless
   │     · --token → inyecta la cookie access_token en .udemy.com
   │
   ├─ 2. ensure_login()        → GET /api-2.0/users/me/  (si no hay sesión, pide login manual + ENTER)
   ├─ 3. resolve_course_id()   → busca el slug en /users/me/subscribed-courses/
   │                             fallback: regex sobre el HTML de /course/<slug>/
   ├─ 4. GET /courses/<id>/    → título del curso
   ├─ 5. fetch_curriculum()    → /courses/<id>/subscriber-curriculum-items/ (paginado)
   │                             capítulos (chapter) + lecciones (lecture → asset → captions[])
   ├─ 6. por cada lección de vídeo:
   │       pick_caption()  → elige subtítulo según --lang (fallback: el primero)
   │       context.request.get(caption.url) → archivo .vtt (CDN firmado)
   │       vtt_to_text()   → quita tiempos/etiquetas/duplicados, una oración por línea, ajuste a --width
   └─ 7. guarda:
           normal: <out>/<curso>/<NN - sección>/<NNN - lección>.txt
           --txt : <out>/<curso>.txt
```

## Piezas clave

| Función | Qué hace | Nota |
|---|---|---|
| `goto_cf` | Navega y espera a que pase el challenge "Just a moment" de Cloudflare | hasta 20 s |
| `api_get` | Ejecuta `fetch()` **dentro de la página** (same-origin, con cookies) y parsea JSON | así atraviesa Cloudflare; no mira el status HTTP |
| `ensure_login` | Valida sesión con `users/me` | |
| `list_courses` | `--list`: cursos suscritos, paginado | |
| `resolve_course_id` | URL/slug/id → id numérico | acepta URLs `/learn/lecture/...` |
| `fetch_curriculum` | Temario completo con captions | |
| `pick_caption` / `vtt_to_text` | Selección de idioma y limpieza del VTT | |

## Supuestos que hoy atan la herramienta a Udemy individual

1. `API = "https://www.udemy.com/api-2.0"` está fijo (línea 56).
2. `ensure_login` y el fallback de `resolve_course_id` navegan a `https://www.udemy.com/...`.
3. La cookie de `--token` se inyecta solo en `.udemy.com` con el flujo de login de www.

Como `api_get` hace `fetch` same-origin, si la página está en `www.udemy.com`, las llamadas
nunca llevan las cookies de sesión de `seti.udemy.com` (Udemy Business) → `users/me` falla
o devuelve un usuario anónimo, y el curso no aparece entre los suscritos.

Ver el plan de cambios en [PLAN.md](PLAN.md).
