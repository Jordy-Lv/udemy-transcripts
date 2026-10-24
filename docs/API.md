# API interna de Udemy (verificada en Udemy Business)

> Verificado el 2026-10-24 en `https://seti.udemy.com` (Udemy Business, SSO) con una sesión real.
> Curso de prueba: *Java: Spring Boot - Guía definitiva* (`id 6737997`).
> La API **no es pública** y puede cambiar. Todo lo de abajo se probó con `fetch()` same-origin
> desde una página del portal, con `credentials: 'include'` y `Accept: application/json`.

## Conclusión principal

Business usa **los mismos endpoints `/api-2.0/...` que www**, pero en el host del portal
(`https://<org>.udemy.com`). La sesión (cookies del SSO) solo vale en ese host: por eso
todas las llamadas deben hacerse desde una página de `<org>.udemy.com`. La Fase 2 del plan
queda confirmada sin cambios de diseño.

## Endpoints confirmados

| Endpoint | Resultado |
|---|---|
| `GET /api-2.0/users/me/?fields[user]=title,id,display_name` | 200, `_class: user`. Sirve para validar la sesión |
| `GET /api-2.0/users/me/subscribed-courses/?fields[course]=id,title,url&page_size=100&ordering=-last_accessed` | 200, paginado (`count`, `next`). 202 cursos; incluye el de Spring Boot |
| `GET /api-2.0/users/me/subscription-course-enrollments/` | 200 pero **`count: 0`**: no sirve para `--list`; basta `subscribed-courses` |
| `GET /api-2.0/courses/<id>/?fields[course]=title,url,locale,num_lectures,content_info` | 200 |
| `GET /api-2.0/courses/<id>/subscriber-curriculum-items/` | 200, paginado (ver abajo) |
| `GET <caption.url>` (CDN `vtt-cdn77.udemycdn.com`) | 200, `text/vtt`. URL firmada con caducidad |
| `GET <download_urls.File[0].file>` (CDN `att-c.udemycdn.com`) | 200/206, PDF real. URL firmada |
| `GET /api-2.0/learning-paths/` | 200, `count: 140` (rutas disponibles en la organización) |
| `GET /api-2.0/learning-paths/<id>/` | 200 |
| `GET /api-2.0/learning-paths/<id>/sections/?page_size=9999&fields[learning_path_section]=id,title,description,items&fields[learning_path_section_has_item]=id,title,description,related_object_type,estimated_content_length,content,is_removed&fields[course_label]=id` | 200, **secciones con sus ítems** (esta es la petición que hace el portal) |
| `GET /api-2.0/learning-paths/<id>/enrollments/?fields[learning_path_has_user]=assignment&user_id=<uid>` | 200 |

No existen (404): `users/me/learning-paths/`, `learning-path-enrollments/`, `organizations/me/`,
`learning-paths/<id>/items|courses|steps|curriculum-items/`.
`learning-paths/<id>/sections/<sid>/items/` responde **403** (no usar; usar el `sections/` con `fields` de arriba).

## Temario: `subscriber-curriculum-items`

Campos útiles (formato `fields[...]` de la herramienta actual, ampliado):

```
fields[lecture]=title,object_index,asset,supplementary_assets,time_estimation
fields[chapter]=title,object_index
fields[asset]=asset_type,captions,title,time_estimation,body,filename,download_urls,external_url
fields[caption]=url,locale_id,video_label,file_name,source,status
```

- Con `page_size=200` el curso de ejemplo da **2 páginas** (330 ítems): seguir `next` es obligatorio.
- `_class` de los ítems: `chapter` (18), `lecture` (298), `quiz` (14).
- `asset.asset_type` de las lecciones: `Video` (163 en la 1.ª página), `Article` (19 en la 1.ª página).
- `chapter`/`lecture` traen `object_index` (numeración de Udemy, base 1 dentro de cada capítulo).
- `lecture.asset.time_estimation` = duración en **segundos** (vídeo) o tiempo estimado de lectura (artículo).
- `lecture.id` es el que va en la URL: `/course/<slug>/learn/lecture/<id>?start=<segundos>`.
- `quiz`: sin `asset`; se ignoran (campos: `title`, `type: simple-quiz`, `pass_percent`).

### Subtítulos (`asset.captions[]`)

```json
{"locale_id": "es_LA", "source": "manual", "status": 1, "video_label": "Español",
 "file_name": "<uuid>.vtt", "url": "https://vtt-cdn77.udemycdn.com/<asset>/es_LA/<uuid>.vtt?secure=..."}
```

- `locale_id` viene como **`es_LA`** (no `es`): la selección actual por prefijo (`startswith("es")`) sigue valiendo.
- `source`: `manual` (265) o `auto` (1) → permite avisar «subtítulo automático» en el índice (Fase 3).
- Las 266 lecciones de vídeo tenían subtítulos en este curso (0 sin subtítulos).
- **El VTT usa `\r\n`** como salto de línea y mete saltos *dentro* de la frase (cues de 1–2 líneas).
  Hay que parsear por bloques de cue y conservar los tiempos (`HH:MM:SS.mmm --> HH:MM:SS.mmm`). Es el caso del bug B4.
- Las URLs caducan (~minutos/horas): pedirlas del temario justo antes de bajarlas.

### Artículos (`asset_type: "Article"`)

`asset.body` trae el **HTML** del artículo (`<p><strong>…`). Convertir a Markdown en la Fase 4.

### Recursos (`lecture.supplementary_assets[]`)

| `asset_type` | Campos | Cuántos en el curso de ejemplo |
|---|---|---|
| `File` | `filename`, `title`, `download_urls.File[0].file` (URL firmada, PDF/zip…) | 29 |
| `ExternalLink` | `external_url`, `title` | 63 |

El PDF se descarga con un `GET` normal a la URL firmada (verificado con `Range`: 206, `application/pdf`).

### Recursos de todo tipo

Inventario de los **202 cursos** suscritos (2026-10-24), solo `supplementary_assets`:

| `asset_type` | Cantidad | Cómo se obtiene |
|---|---|---|
| `File` | 5 752 | `download_urls.File[0].file` (URL firmada en `att-c.udemycdn.com`) |
| `ExternalLink` | 2 765 | `external_url`; no hay nada que descargar |
| `Video` | 1 | `download_urls.Video[...]`; caso aislado, tratar genéricamente |

Las **lecciones** en sí solo son `Video` (23 669) o `Article` (1 867): no hay lecciones de tipo archivo/presentación en estos cursos.

Extensiones de los `File` (60+; las principales): `pdf` 1 824 · `zip` 1 174 · `sql` 588 · `txt` 438 ·
`xlsx` 211 · `png` 193 · `mp3` 176 · `yaml` 158 · `ipynb` 135 · `json` 108 · `csv` 101 · `java` 90 ·
`js` 77 · `docx` 58 · `ps1` 53 · `py` 36 · `pptx` 29 · `pbix` 34 · y una cola larga (`exe`, `msi`, `jar`, `war`,
`rar`, `tar`, `mp4`, `mov`, `glb`, `vsd`, `drawio`…). 18 `File` **no tienen extensión** en `filename`
(p. ej. `e.condicional-case.condicional_case`): la extensión real está en la ruta del CDN (`.../original.<ext>`).

Observaciones de descarga (probadas con `Range: bytes=0-0`, todas 206):

- El `Content-Type` es el correcto por tipo (`application/pdf`, `application/zip`, `audio/mpeg`,
  `application/x-msdownload`, `binary/octet-stream`…): no se puede asumir «solo PDF».
- La URL lleva `response-content-disposition=attachment; filename=...` firmado y caduca (`Expires`):
  pedirla del temario justo antes de bajarla.
- Desde la página (`fetch`) no se leen `Content-Range`/`Content-Length` por CORS; con
  `context.request` de Playwright sí hay cabeceras completas → úsalo para estimar tamaños.
- `title` puede diferir de `filename` (p. ej. `x86_64` vs `x86-64`): usar `filename` como nombre en disco.

### Imágenes dentro de artículos

En los 1 867 artículos hay 533 `<img src="https://img-c.udemycdn.com/redactor/raw/...">` (CDN público,
sin firma) y ~1 920 enlaces externos; ningún enlace apunta a archivos de Udemy ni hay `<iframe>`.

## Rutas de aprendizaje

Estructura obtenida de `learning-paths/<id>/sections/?...items...`:

```
learning_path_section { id, title, description, items[] }
  learning_path_section_has_item {
    id, title, description, is_removed, estimated_content_length,
    related_object_type: "course" | "lab" | "adaptive_assessment_assessment" | ...,
    content: { ... }   // para "course": id, title, url ("/course/<slug>/"), num_published_lectures, ...
  }
```

- Solo `related_object_type == "course"` se puede descargar con el flujo normal; los `lab` y las
  evaluaciones adaptativas no tienen temario/subtítulos y se omiten (se listan en el índice).
- El portal usa la URL `https://<org>.udemy.com/learning-paths/<id>/`.
- Hay secciones vacías (`title: ""`, 0 ítems): ignorarlas.
- Un curso de una ruta puede no estar en `subscribed-courses`; ver la sección siguiente.

## Inscripción (hallazgo importante)

Se pidió `subscriber-curriculum-items` de un curso **no inscrito** (`2645936`, AWS CLF-C02, de una ruta):
respondió **200** con el temario (234 ítems) y, **verificado en la Fase 2**, también con los `captions`:
las 34 lecciones de vídeo muestreadas traían subtítulos y el VTT se descargó con 200. Es decir, en este
portal se puede bajar el temario y las transcripciones de un curso **sin inscribirse**, y ese curso trae
28 idiomas (`es_ES`, `en_US`, `pt_BR`, `fr_FR`, `de_DE`, `ja_JP`…): sirve para probar `--lang es+en` (Fase 6).
El plan asumía un 403 («pulsa Empezar curso»): la herramienta conserva ese mensaje para cuando ocurra
(Business + 403 en el temario), pero no es lo que se observó aquí. Sigue sin verificarse si los
recursos (`File`) de un curso no inscrito se descargan.

## Efectos sobre el plan

| Fase | Ajuste |
|---|---|
| 1 | VTT con `\r\n` y cues multilínea → confirma B4. `api_get` debe devolver `status` (los 403/404 devuelven `{"detail": ...}` y hoy se leen como datos válidos) |
| 2 | Sin cambios: mismo `/api-2.0` en el host del portal. `--list` solo con `subscribed-courses` (la otra lista está vacía) |
| 3 | `source: auto/manual` y `locale_id` disponibles para la cabecera YAML; `time_estimation` para duración |
| 4 | Endpoint de rutas **resuelto** (`sections/?fields...items`). Solo `course` es descargable. Recursos `File` y `ExternalLink` confirmados |
| 6 | Los cursos del ejemplo solo tienen un idioma (`es_LA`): para probar `--lang es+en` hace falta otro curso con varias pistas |

## Pendiente de verificar

- `subscription-course-enrollments` devuelve 0 aunque haya 202 cursos suscritos: no se sabe qué lista.
- Captions de un curso no inscrito (ver arriba).
- Cuota/límite de peticiones (`429`): no se alcanzó con ~15 llamadas; el backoff de la Fase 1 sigue siendo necesario.
- Cloudflare con Playwright/Chromium propio: aquí se usó el navegador integrado de la app y no hubo challenge;
  la herramienta real sigue necesitando ventana visible (no probado en esta fase).
