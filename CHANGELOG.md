# Changelog

## 0.5.0 — Fase 4: todo el material del curso

### Novedades
- **Artículos**: las lecciones de tipo artículo se descargan y se convierten de HTML a Markdown
  (títulos, listas anidadas, código con lenguaje, tablas, enlaces, imágenes, citas) o a texto plano con
  `--format txt`. Salen en su sección con `tipo: "articulo"` y entran en el índice y en `--single`.
- **Recursos de todo tipo** (`--resources`): cualquier adjunto descargable (`File` y otros con
  `download_urls`), sin filtrar por extensión, en `recursos/<NN - sección>/<NNN - lección>/`. Los
  enlaces externos se listan en cada lección y en `recursos/enlaces.md`.
  - Resumen previo con nº de archivos y tamaño total (petición `Range: bytes=0-0`) y confirmación si
    pasa de 500 MB (`--yes`); `--max-size` (default 500MB) omite los muy pesados.
  - Reanudable y sin duplicados (el manifest guarda ruta y tamaño); escritura atómica (`.part`).
  - Nombres repetidos numerados (`a (2).pdf`); extensión tomada del CDN si falta; ejecutables
    avisados y nunca ejecutados.
  - `--resource-types pdf,zip`, `--resources-only`.
- **Imágenes de artículos**: con `--resources` se guardan en `…/img/` y el Markdown las enlaza en local.
- **Rangos**: `--sections 3-5,8` y `--lectures 10-20` (también `12-`), con la numeración de Udemy. El
  índice sigue mostrando el curso completo.
- **Rutas de aprendizaje** (Business): `udemy "<url de la ruta>"` baja cada curso a `<ruta>/<NN - curso>/`
  con un `README.md` general; los laboratorios y evaluaciones se listan sin descargar; un curso que falla
  no detiene la ruta (sí la pérdida de sesión).
- Las lecciones listan sus recursos aunque no se descarguen («sin descargar (usa --resources)») y
  enlazan los que ya están en disco.

### Cambios de comportamiento
- Los artículos ahora se descargan siempre (antes se ignoraban) y cuentan en «Listo: N lecciones».
- El índice dice «N de M lecciones descargadas» (vídeos y artículos).
- Los archivos de lección cambian ligeramente (campo `tipo` y sección «Recursos»): con `--update` se
  reescriben una vez.

### Interno
- Módulos nuevos: `html2md`, `resources`, `ranges`, `paths`, `render/mdtext`. `download.py` procesa
  vídeos, artículos y recursos; `cli.py` se divide en `download_one` / `download_path`.
- `Client.download_bytes` (descargas binarias sin el tope de 30 s). 232 tests sin red.

### Verificado en vivo (seti.udemy.com, 2026-10-24)
- Curso Spring Boot con `--resources`: 298 lecciones (266 vídeos + 32 artículos) y 29 archivos (63.8 MB:
  pdf, zip, html, sql, md, png) en `recursos/`; `--update` posterior: 298 sin cambios y 29 ya descargados en 5 s.
- `--resources-only --resource-types pdf --max-size 5MB`: 4 PDF descargados, 21 omitidos por tipo, 4 por tamaño.
- `--sections 2 --lectures 5-8`: 4 lecciones. Ruta AWS (`/learning-paths/1283634/`): un curso descargado,
  otro con el 403 real de «Empezar curso» anotado en el índice, y laboratorios/evaluación listados.

### Sin verificar
- Imágenes de artículos y conversión de código/tablas con artículos reales (los 32 del curso de prueba no
  traen imágenes ni bloques de código; solo se cubren con tests).
- Descarga de archivos de varios cientos de MB (Playwright los carga enteros en memoria).

## 0.4.0 — Fase 3: salida pensada para estudiar

### Cambios de comportamiento
- **El formato por defecto ahora es Markdown** (`--format md`): un `.md` por lección con cabecera
  YAML y un `README.md` índice por curso. Para el comportamiento anterior usa `--format txt`; el
  modo de archivo único de siempre sigue siendo `--txt` (= `--single --format txt`).
- La salida ahora trae **párrafos** (separados por una línea en blanco) y **marcas de tiempo**
  `[mm:ss]` al inicio de cada uno. `--no-timestamps` las quita; en `.txt` el resto del texto es el de
  siempre (una oración por línea), salvo la línea en blanco entre párrafos.
- El archivo único lleva una tabla de contenidos al inicio.

### Novedades
- **Markdown**: cabecera YAML (`curso`, `seccion`, `leccion`, `numero`, `url`, `duracion`, `idioma`,
  `subtitulo_automatico`), `README.md` con secciones, duración e idioma de cada lección, y escape de los
  caracteres especiales de Markdown.
- **Marcas de tiempo enlazadas**: `[04:15](…/learn/lecture/<id>?start=255)` abre el vídeo en ese segundo.
  `--ts-every SEG` las espacia; `--no-timestamps` las quita.
- **Párrafos naturales** a partir de los tiempos de los cues: corte tras una pausa de 2,5 s o al pasar
  de ~400 caracteres en un final de oración. Los valores salen de medir 4 178 cues reales (con 1,5 s / 500
  el 18 % de los párrafos era de una sola frase).
- **`--update` y reanudación** con `<curso>/.udemy-transcripts.json` (archivo, idioma, huella del
  subtítulo, hash del VTT, opciones de render). Una lección se omite solo si nada de lo que afecta al
  archivo cambió; el manifest se guarda tras cada lección, así que una descarga cortada se reanuda con
  el mismo comando. Las lecciones renombradas se reescriben y se conserva el archivo anterior.
- `--format`, `--single`.

### Correcciones
- En Windows, una carpeta de salida profunda con títulos largos superaba los 260 caracteres y la descarga
  fallaba con un traceback (`FileNotFoundError`): ahora se usan rutas extendidas y un fallo de escritura
  da un error claro.

### Interno
- Nuevos módulos `paragraphs`, `manifest`, `download`, `render/common`, `render/markdown`;
  `course_title` pasa a `course_info` (título y slug). 150 tests sin red.

### Verificado en vivo (seti.udemy.com, 2026-10-24)
- Curso de 266 lecciones: Markdown + índice, `--single`, `--txt --ts-every 60`.
- `--update`: 266 lecciones sin cambios en 6 s y sin descargar nada; regenera solo lo borrado o lo
  afectado por un cambio de opciones.

## 0.3.0 — Fase 2: Udemy Business

- **Portal de Business**: el host se toma de la URL (`https://<org>.udemy.com/...`) y todas las
  llamadas (login, API, landing) van a ese host, así que viaja la sesión SSO. Si pasas un id o
  un slug, indica la organización con `--business ORG` (o `UDEMY_BUSINESS`): acepta `seti`,
  `seti.udemy.com` o una URL del portal. Si la URL y `--business` no coinciden, manda la URL (con aviso).
- `--list` en Business suma `subscribed-courses` y `subscription-course-enrollments` sin duplicados
  (la segunda lista es de mejor esfuerzo: si falla se ignora).
- `--token` inyecta la cookie `access_token` en el host del portal (en www sigue siendo `.udemy.com`).
- Un 403 en el temario de Business explica cómo inscribirse: abrir el curso en el portal y pulsar
  «Empezar curso».
- Cursos de www: sin cambios de comportamiento (cubierto por los tests existentes).
- 93 tests sin red.

### Verificado en vivo (seti.udemy.com, 2026-10-24)
- `udemy --business seti --list` → 202 cursos, sesión reutilizada del perfil sin volver a pedir login.
- `udemy --business seti --txt java-spring-boot-guia-definitiva` (solo slug) → 266/266 transcripciones, 0 errores.

### Sin verificar
- `--token` en Business (no se probó con un token real).
- El formato de `subscription-course-enrollments` (vacío en la cuenta de prueba).
- Regresión contra www.udemy.com con una cuenta personal (solo cubierta por tests).

## 0.2.0 — Fase 1: base sólida

### Cambios internos
- El script único pasa a ser el paquete `udemy_transcripts/` (cliente, cursos, temario,
  subtítulos, render, CLI). `udemy_transcripts.py` queda como envoltorio.
- `pyproject.toml` con el comando `udemy`; los instaladores ahora hacen `pip install` del
  repositorio (ya no copian un solo archivo).
- Tests con `pytest` y sin red (69 casos).
- Playwright se importa solo cuando se necesita (`--help` y los tests no lo requieren).

### Correcciones
- **B1** El `--out` de la ayuda muestra la ruta real (`$UDEMY_OUT` o `~/Udemy-Transcripts`).
- **B2** El README documenta las subcarpetas por sección.
- **B3** Los 401/403/404 y los fallos de red dan un error explícito (sin sesión / sin acceso /
  Cloudflare) en lugar de terminar en «Listo: 0». Código de salida 1 si no se guardó nada.
- **B4** Parser VTT por bloques de cue: ya no se pierden frases que sean solo un número ni se
  cuelan identificadores no numéricos; soporta CRLF, BOM, `NOTE`/`STYLE`/`REGION` y tiempos con o sin horas.
- **B5** Aviso cuando se usa otro idioma del pedido (`usando en_US, no hay es`). Entre subtítulos
  del mismo idioma se prefiere el manual al automático.
- **B6** El `course_id` sacado de la landing se prioriza por `data-clp-course-id` y se **valida
  con la API** contra el slug antes de usarlo.
- **B7** (parcial) Reintentos con backoff ante 429/5xx/red, respetando `Retry-After`. La
  reanudación llega con el manifest de la Fase 3.

### Novedades
- Progreso por lección: `[37/312] sección › 037 - lección`.
- Nombres de archivo válidos en Windows (sin punto/espacio final ni caracteres de control).
- `--version`.
- El portal se toma de la URL (`<org>.udemy.com`); el soporte completo de Udemy Business llega en la Fase 2.

### Sin cambios de comportamiento
- La salida sigue siendo `.txt` con el mismo texto que antes (verificado contra el parser original).
