# Plan de evolución de udemy-transcripts

> Creado: 2026-10-24 · Estado: **completado (1.0.0)** — las fases 0-6 están implementadas y verificadas en vivo salvo lo anotado en el CHANGELOG («Sin verificar») y en [API.md](API.md)
> Objetivo: soportar **Udemy Business** y convertir la herramienta en un **kit de estudio completo**.
> Curso de ejemplo (Business): `https://seti.udemy.com/course/java-spring-boot-guia-definitiva/learn/lecture/51621647?start=255#overview`

Cómo funciona hoy: ver [ARQUITECTURA.md](ARQUITECTURA.md).

---

## Resumen por fases

| Fase | Contenido | Resultado |
|---|---|---|
| **0** ✓ | Verificación en vivo de la API de Business | Endpoints confirmados antes de programar |
| **1** ✓ | Base: paquete, tests, reintentos, bugs B1–B7 | Código mantenible y fiable |
| **2** ✓ | Soporte **Udemy Business** | `udemy "<url de seti>"` funciona |
| **3** ✓ | Salida de estudio: **Markdown, marcas de tiempo, párrafos, `--update`** | Apuntes legibles y enlazados al vídeo |
| **4** ✓ | Más contenido: **artículos, recursos de todo tipo (PDF, zip, código…), rangos, rutas de aprendizaje** | Todo el material del curso |
| **5** ✓ | **Resúmenes y flashcards con IA** (opcional) | Repaso activo / Anki |
| **6** ✓ | Extras: subtítulos bilingües, empaquetado, documentación final | Pulido |

Cada fase termina con tests en verde, prueba manual con el curso de ejemplo,
README/CHANGELOG actualizados y un commit (o PR) propio.

---

## Fase 0 — Verificación en vivo (con tu sesión)

Abrir `seti.udemy.com` en la ventana de Playwright; **tú** inicias sesión por SSO
(la herramienta nunca toca contraseñas). Comprobar y anotar en `docs/API.md`:

- `users/me`, `users/me/subscribed-courses`, `users/me/subscription-course-enrollments`
- `courses/<id>/subscriber-curriculum-items` con `captions`, `body` (artículos),
  `supplementary_assets`, `time_estimation`
- descarga de un `.vtt` y de un recurso
- endpoint de **rutas de aprendizaje** (inspeccionando las peticiones de red de una ruta en el portal)
- si el curso de Spring Boot ya figura como inscrito

---

## Fase 1 — Base sólida

El script único va a crecer mucho; se reorganiza en un paquete:

```
udemy_transcripts/
  cli.py          argumentos y orquestación
  client.py       navegador, login, api_get con status + reintentos
  portal.py       detección de host (www / <org>.udemy.com)
  curriculum.py   temario, filtros por rango, modelo Lecture/Section
  captions.py     parseo VTT → cues con tiempos, selección de idioma
  render/         txt.py, markdown.py
  manifest.py     estado de descarga (--update)
  resources.py    artículos y archivos adjuntos
  study.py        IA: resúmenes y flashcards (opcional)
tests/            pytest, sin red (fixtures JSON/VTT)
pyproject.toml    comando `udemy`, extras opcionales [ai]
```

- `udemy_transcripts.py` se mantiene como envoltorio para no romper instalaciones existentes.
- Ojo: hasta la Fase 3 la salida sigue siendo `.txt` como hoy; el cambio a Markdown por
  defecto entra en la Fase 3 (y se anota en el CHANGELOG como cambio de comportamiento).
- `api_get` devuelve status + JSON; reintentos con backoff ante 429/5xx/red.
- Progreso visible (`[37/312] sección › lección`).
- Corrección de bugs:

| # | Problema | Arreglo |
|---|---|---|
| B1 | help de `--out` muestra una ruta que no es la real | alinear con `~/Udemy-Transcripts` |
| B2 | README no refleja las subcarpetas por sección | actualizar tabla |
| B3 | un 403/401 acaba en "Listo: 0" | errores explícitos (sin sesión / no inscrito) |
| B4 | se borran frases que son solo un número; IDs de cue no numéricos se cuelan | parser VTT real basado en bloques de cue |
| B5 | cambio de idioma silencioso | avisar `(usando en, no hay es)` |
| B6 | regex de `courseId` puede capturar otro número | priorizar `data-clp-course-id` y validar con la API |
| B7 | sin reintentos ni reanudación | backoff (fase 1) + manifest (fase 3) |

## Fase 2 — Udemy Business

| | Individual | Business |
|---|---|---|
| Host | `www.udemy.com` | `<org>.udemy.com` |
| API | `/api-2.0/...` | **mismos endpoints** en el host del portal |
| Login | email / Google | SSO corporativo |
| Acceso | comprado | requiere inscribirse ("Empezar curso") |

- Host tomado de la URL; `--business ORG` / `UDEMY_BUSINESS` para id, slug y `--list`.
- `ensure_login` y todas las llamadas usan el host del portal (el `fetch` same-origin lleva sus cookies).
- `--token` inyecta la cookie en el dominio del portal.
- `--list` combina `subscribed-courses` + `subscription-course-enrollments`.
- 403 en el temario → *"Abre el curso en el portal y pulsa 'Empezar curso'"*.
- Regresión: un curso de www debe seguir funcionando igual.

## Fase 3 — Salida pensada para estudiar

### 3.1 Markdown (formato por defecto; `--format txt` para el comportamiento actual)
```
<curso>/
  README.md                     índice: secciones, lecciones, duración, enlaces
  01 - Introducción/
    001 - Bienvenida.md
```
Cada lección lleva cabecera YAML (curso, sección, lección, URL, duración, idioma,
si el subtítulo es automático) → compatible con Obsidian, Notion y VS Code.
El modo un-solo-archivo (`--single`, alias del actual `--txt`) funciona en ambos formatos,
con tabla de contenidos al inicio.

### 3.2 Marcas de tiempo enlazadas
Al inicio de cada párrafo (o cada `--ts-every 60` s):
`[04:15](https://seti.udemy.com/course/<slug>/learn/lecture/<id>?start=255)`.
`--no-timestamps` para quitarlas. En `txt` se muestran como `[04:15]` sin enlace.

### 3.3 Párrafos naturales
El parser VTT conserva los tiempos de cada cue. Nuevo párrafo cuando hay una pausa
de 2,5 s o más o cuando el párrafo supera ~400 caracteres y termina en punto
(valores medidos con subtítulos reales; con 1,5 s / 500 salían demasiados párrafos de una frase).
Si el subtítulo es automático y no tiene puntuación, se corta solo por pausas.

### 3.4 `--update` / reanudar
`<curso>/.udemy-transcripts.json` guarda por lección: id, archivo, idioma y hash.
Con `--update` solo se bajan lecciones nuevas o cuyo subtítulo cambió, y se regenera
el índice. Una descarga cortada se reanuda donde quedó.

## Fase 4 — Todo el material del curso

- **Artículos** (lecciones `Article`): HTML del campo `body` → Markdown, en su sección.
- **Recursos de todo tipo** (`supplementary_assets`), sin filtrar por extensión. Inventario
  real en 202 cursos de Business (ver [API.md](API.md#recursos-de-todo-tipo)): `File` (5 752, en
  más de 60 extensiones: pdf, zip, sql, xlsx, ipynb, pptx, mp3, exe, jar…), `ExternalLink` (2 765)
  y algún `Video` suelto. Reglas:
  - Cada recurso se guarda en `recursos/<NN - sección>/<NNN - lección>/<nombre original>`
    (el nombre sale de `filename`; si no tiene extensión se usa la del archivo en el CDN).
  - Se descarga cualquier clave de `download_urls` (`File`, `Video`…), no solo PDF.
  - Los `ExternalLink` no se descargan: se listan en la lección (`.md`) y en `recursos/enlaces.md`.
  - Antes de bajar, resumen con nº de archivos y **tamaño total** (cabecera `Content-Length` con
    `context.request`) y confirmación si pasa de un umbral (`--yes` para saltarla).
  - Reanudable y sin duplicados: el manifest guarda ruta y tamaño; un archivo ya completo se omite.
  - Nombres duplicados en una misma lección se desambiguan (`nombre (2).ext`); aviso si un archivo
    ejecutable (`.exe`, `.msi`, `.jar`…) se descargó, sin ejecutarlo nunca.
  - Flags: `--resources` (descarga todo), `--resources-only` (solo recursos, sin subtítulos),
    `--resource-types pdf,zip` (filtro opcional), `--max-size 200MB` (omitir archivos mayores).
- **Imágenes de artículos** (`<img src="img-c.udemycdn.com/redactor/...">`, 533 en 1 867 artículos):
  con `--resources` se bajan a `recursos/<sección>/<lección>/img/` y el Markdown las enlaza en local.
- **Rangos**: `--sections 3-5,8` y `--lectures 10-20` (numeración de Udemy; también `12-`).
- **Rutas de aprendizaje** (Business): `udemy "<url de la ruta>"` → descarga cada curso en
  `<ruta>/<NN - curso>/` con un índice general. Endpoint a confirmar en la Fase 0.

## Fase 5 — Estudio con IA (opcional)

`--study` genera, por sección:
- `RESUMEN.md`: ideas clave, conceptos y ejemplos de código mencionados.
- `flashcards.csv`: pregunta;respuesta;etiquetas, importable directo en **Anki**.

Dos modos:
1. **API** (`--study api`): usa la API de Claude (requiere `ANTHROPIC_API_KEY`, extra
   `pip install .[ai]`). Antes de empezar estima el costo y pide confirmación.
   Modelo configurable con `--ai-model`.
2. **Prompt** (`--study prompt`, sin costo de API): genera archivos de prompt listos para
   pegar en Claude/ChatGPT con tu suscripción.

Se procesa por sección para respetar límites de contexto, y se cachea para no
regenerar lo que no cambió (en la práctica: caché propia `.estudio/` con la huella del texto, el
modelo y la versión de las instrucciones, en vez de colgar del manifest).

## Fase 6 — Extras y pulido

- **Subtítulos bilingües** (`--lang es+en`): dos columnas/bloques alineados por tiempo,
  útil para aprender inglés técnico. *(Hecho: bloque bajo cada párrafo; ver README.)*
- Instaladores (`install.ps1`/`install.sh`) basados en `pip install .` en vez de copiar el script.
- README completo con ejemplos de todas las opciones, `CHANGELOG.md`, `docs/API.md`.

---

## CLI objetivo

```bash
udemy --business seti --list
udemy "https://seti.udemy.com/course/java-spring-boot-guia-definitiva/"   # md por defecto
udemy --format txt --single "<url>"
udemy --update "<url>"
udemy --sections 3-5 --resources "<url>"
udemy --resources-only --max-size 200MB "<url>"   # solo PDFs, código y demás adjuntos
udemy "https://seti.udemy.com/learning-paths/<id>/"
udemy --study api "<url>"
```

**Decisión (2026-10-24):** el formato por defecto pasa a ser **Markdown**;
`--format txt` conserva el comportamiento actual.

## Riesgos y notas

- **Términos de uso**: el contrato de Udemy Business es de tu empresa; usar el material
  solo para estudio personal y no redistribuirlo.
- **SSO**: el login siempre lo haces tú en la ventana.
- La API interna de Udemy no es pública: puede cambiar. La Fase 0 y `docs/API.md` lo
  documentan, y los errores explícitos de la Fase 1 lo hacen evidente si ocurre.
- Algunos cursos no tienen subtítulos o solo automáticos: se indica en el índice.
