# udemy-transcripts

Descarga las **transcripciones (subtítulos)** de todos los videos de un curso de Udemy (personal o **Udemy Business**) y las guarda como **Markdown** listo para estudiar.

- Convierte los subtítulos a **párrafos legibles** con **marcas de tiempo que enlazan al segundo exacto del vídeo**.
- Cada lección lleva cabecera YAML (curso, sección, URL, duración, idioma…) y el curso un `README.md` índice: compatible con Obsidian, Notion y VS Code.
- Descarga también los **artículos** (convertidos a Markdown) y los **recursos de todo tipo** que deja el instructor (PDF, código, zips…), por curso completo, por rangos o por **ruta de aprendizaje**.
- **Estudio con IA** (opcional): `--study` genera un resumen por sección y flashcards listas para **Anki**, con la API de Claude o con prompts para pegar en un chat.
- **Subtítulos bilingües** (`--lang es+en`): cada párrafo con su traducción alineada por tiempo, útil para aprender inglés técnico.
- Tres salidas: **un archivo por video**, **todo el curso en un solo archivo** (con tabla de contenidos) o el `.txt` clásico.
- **`--update`** descarga solo lo nuevo o cambiado y reanuda una descarga cortada.
- Usa un navegador real (Playwright) para reutilizar tu sesión y atravesar la protección Cloudflare de Udemy.

**Índice:** [Instalación](#instalación) · [Uso](#uso) · [Recetas](#recetas) · [Dónde se guardan](#dónde-se-guardan) · [Recursos, rangos y rutas](#recursos-rangos-y-rutas-de-aprendizaje) · [Bilingüe](#subtítulos-bilingües) · [Estudio con IA](#estudio-con-ia-resúmenes-y-flashcards) · [Opciones](#opciones) · [Problemas frecuentes](#problemas-frecuentes)

> ⚠️ **Uso responsable:** descarga solo cursos a los que **tú tienes acceso** y úsalo para estudio personal. No redistribuyas el contenido.

---

## Requisitos

- **Python 3.8+** (3.10+ solo si usas `--study api`)
- ~300 MB libres (Playwright descarga su propio Chromium)
- Una cuenta de Udemy con el curso comprado/disponible

---

## Instalación

### macOS / Linux
```bash
git clone https://github.com/Jordy-Lv/udemy-transcripts.git
cd udemy-transcripts
bash install.sh
```

### Windows (PowerShell)
```powershell
git clone https://github.com/Jordy-Lv/udemy-transcripts.git
cd udemy-transcripts
powershell -ExecutionPolicy Bypass -File install.ps1
```

El instalador crea un entorno aislado (no toca tu Python del sistema), descarga Chromium y deja el comando global **`udemy`**. Si la terminal no lo reconoce, reiníciala (o añade la carpeta indicada al PATH).

| Opción (bash / PowerShell) | Para qué |
|---|---|
| `--with-ai` / `-WithAI` | Instala también el SDK de Anthropic (para `--study api`; exige Python 3.10+) |
| `--skip-browser` / `-SkipBrowser` | No descarga Chromium (ya lo tienes o lo harás luego) |
| `--uninstall` / `-Uninstall` | Borra el entorno y el comando; **no** toca tus descargas ni tu sesión de Udemy |
| `UDEMY_APP_DIR`, `UDEMY_BIN_DIR` / `-AppDir`, `-BinDir` | Dónde se instala el entorno y el comando |

Para **actualizar**, haz `git pull` y vuelve a ejecutar el instalador. Comprueba la versión con `udemy --version`.

---

## Uso

```bash
udemy --list                                     # lista tus cursos y su id
udemy "https://www.udemy.com/course/mi-curso/"   # Markdown: un .md por video + README.md índice
udemy --single "https://www.udemy.com/course/mi-curso/"   # todo el curso en un solo .md
udemy --format txt "https://www.udemy.com/course/mi-curso/"   # texto plano, un .txt por video
udemy --update "https://www.udemy.com/course/mi-curso/"   # solo lo nuevo o cambiado
udemy --resources "https://www.udemy.com/course/mi-curso/"   # + PDFs, código y demás adjuntos
```

Puedes pasarle la URL de la página del curso **o** la del reproductor (`/learn/lecture/...`), o directamente el id numérico.

### Recetas

```bash
udemy --list                                                  # ¿qué cursos tengo y cuál es su id?
udemy "<url>"                                                 # lo básico: Markdown con índice
udemy --update "<url>"                                        # volver a lanzarlo: solo lo nuevo o cambiado
udemy --resources --update "<url>"                            # lecciones + PDFs, código y adjuntos
udemy --lang es+en "<url>"                                    # texto en español con el inglés debajo
udemy --sections 3-5 --lectures 40- "<url>"                   # solo una parte
udemy --single --no-timestamps "<url>"                        # todo en un archivo, sin marcas de tiempo
udemy --format txt --width 80 "<url>"                         # texto plano a 80 columnas
udemy --update --study prompt "<url>"                         # prompts para pegar en un chat (gratis)
udemy --study api --ai-model claude-sonnet-5-5 "<url>"        # resumen y flashcards con la API
udemy --business miempresa --list                             # cursos de tu Udemy Business
udemy "https://miempresa.udemy.com/learning-paths/<id>/"      # toda una ruta de aprendizaje
```

### Udemy Business

Si tu empresa te da acceso por Udemy Business (SSO), pasa la URL del portal tal cual:

```bash
udemy "https://miempresa.udemy.com/course/mi-curso/learn/lecture/123456"
```

o indica la organización cuando uses un id/slug o `--list`:

```bash
udemy --business miempresa --list
udemy --business miempresa mi-curso          # o export UDEMY_BUSINESS=miempresa
```

El login (SSO) lo haces tú en la ventana de Chromium. Si el curso responde «sin acceso», ábrelo
una vez en el portal y pulsa **Empezar curso**.

### La primera vez
Se abre una ventana de Chromium. **Inicia sesión en Udemy ahí.** La sesión queda guardada, así que las siguientes veces no tendrás que volver a loguearte.

> El modo con ventana es obligatorio: Udemy bloquea los navegadores "headless" con Cloudflare.

---

## Dónde se guardan

```
~/Udemy-Transcripts/<curso>/
  README.md                       índice: secciones, lecciones, duración, idioma y enlaces
  .udemy-transcripts.json         estado de la descarga (para --update)
  01 - Introducción/
    001 - Bienvenida.md
    002 - ...
```

| Modo | Resultado |
|------|-----------|
| por defecto (`--format md`) | un `.md` por video, en la carpeta de su sección, con la numeración de Udemy, y el `README.md` índice |
| `--format txt` | lo mismo con `.txt` (sin cabecera YAML ni índice) |
| `--single` | `~/Udemy-Transcripts/<curso>.md` (o `.txt` con `--format txt`) con tabla de contenidos |
| `--txt` | el modo clásico: `--single --format txt` |

Cambia la carpeta base con `--out RUTA` o con la variable de entorno `UDEMY_OUT`.

### Cómo se ve una lección

```markdown
---
curso: "Java: Spring Boot - Guía definitiva"
seccion: "Introducción a Spring boot"
leccion: "Spring boot: @Controller parte 1"
numero: 11
tipo: "video"
url: "https://miempresa.udemy.com/course/java-spring-boot-guia-definitiva/learn/lecture/51621647"
duracion: "09:58"
idioma: "es_LA"
subtitulo_automatico: false
---

# Spring boot: @Controller parte 1

[00:05](https://…/learn/lecture/51621647?start=5) Hola a todos, bienvenidos a un nuevo vídeo…

[00:38](https://…/learn/lecture/51621647?start=38) Importante que tengamos esta versión…

## Recursos

- [spring-boot-3-template-main.zip](../recursos/02%20-%20…/009%20-%20…/spring-boot-3-template-main.zip)
- [Instalaciones necesarias](https://gist.github.com/…)
```

- **Párrafos:** se corta tras una pausa de 2,5 s o más, o cuando el párrafo pasa de ~400 caracteres y termina una oración. Si el subtítulo es automático y no tiene puntuación, solo corta por pausas.
- **Marcas de tiempo:** una por párrafo (`--ts-every 60` las espacia a una por minuto como mucho; `--no-timestamps` las quita). En `.txt` salen como `[04:15]`, sin enlace.
- **Texto:** en Markdown se escapan los caracteres especiales (`_`, `*`, `<`…) para que `snake_case` o `Map<K, V>` se vean tal cual.
- **Artículos:** las lecciones de tipo artículo se convierten de HTML a Markdown (títulos, listas, código, tablas, enlaces e imágenes) y salen en su sección con `tipo: "articulo"`.
- **Recursos:** cada lección lista sus adjuntos (los archivos locales enlazados y los enlaces externos).

### `--update` y reanudar

`<curso>/.udemy-transcripts.json` guarda, por lección, el archivo generado, el idioma y la huella del
subtítulo. Con `--update` solo se baja una lección si es nueva, si el instructor cambió el subtítulo,
si cambiaste el formato o las opciones, o si borraste su archivo; lo demás se omite sin descargar
nada. Si una descarga se corta (Ctrl-C, red, error), vuelve a lanzar el mismo comando con `--update`
y continúa donde quedó. Si una lección cambia de nombre, se escribe con el nombre nuevo y el archivo
anterior se conserva (se avisa). `--update` no aplica a `--single`.

---

## Recursos, rangos y rutas de aprendizaje

### Recursos de todo tipo (`--resources`)

Los instructores adjuntan PDFs, código, zips, hojas de cálculo, audio… Con `--resources` se descargan
**todos**, sea cual sea su tipo, y las imágenes de los artículos:

```
<curso>/recursos/
  enlaces.md                          todos los enlaces externos del curso
  02 - Introducción a Spring boot/
    009 - Spring boot- Creando el proyecto/
      spring-boot-3-template-main.zip
```

- Antes de bajar nada muestra el resumen (`29 archivo(s) por descargar (63.8 MB)`) y pide confirmación
  si el total pasa de 500 MB (`--yes` para aceptar sin preguntar).
- **Seguro:** los archivos pesados se omiten (`--max-size`, default 500MB); los ejecutables e
  instaladores (`.exe`, `.msi`, `.jar`…) se guardan con un aviso y **nunca se ejecutan**.
- **Reanudable:** un archivo completo (misma ruta y tamaño) no se vuelve a bajar; uno a medias nunca
  queda en su sitio (se escribe como `.part` y se renombra al terminar).
- Dos adjuntos con el mismo nombre en una lección se numeran: `datos.csv`, `datos (2).csv`. Si el
  nombre no tiene extensión se usa la del archivo en el servidor.
- `--resource-types pdf,zip` limita por extensión y `--resources-only` baja solo los recursos, sin
  transcripciones ni artículos.

```bash
udemy --resources "<url del curso>"                       # todo: lecciones + recursos
udemy --resources-only --resource-types pdf --max-size 50MB "<url>"
```

### Solo una parte del curso

```bash
udemy --sections 3-5,8 "<url>"        # secciones 3, 4, 5 y 8 (la numeración «NN» de las carpetas)
udemy --lectures 10-20 "<url>"        # lecciones 010 a 020 (el «NNN» de los archivos)
udemy --sections 12- "<url>"          # de la 12 hasta el final
```

El índice `README.md` sigue mostrando el curso completo; las lecciones que no bajaste figuran como
«pendiente de descargar». Combinado con `--update`, puedes ir completando el curso por partes.

### Rutas de aprendizaje (Udemy Business)

Pasa la URL de una ruta y cada curso va a su carpeta numerada, con un índice general:

```bash
udemy "https://miempresa.udemy.com/learning-paths/1283634/"
```

```
<ruta>/
  README.md                           secciones de la ruta y enlaces a cada curso
  01 - Curso uno/   (con su README.md, lecciones y .udemy-transcripts.json)
  02 - Curso dos/
```

Solo se descargan los **cursos**; los laboratorios y las evaluaciones se listan en el índice como «no
se descarga». Si un curso falla (p. ej. pide «Empezar curso»), se anota en el índice y se sigue con el
siguiente; si se pierde la sesión, se detiene. `--sections`, `--lectures`, `--resources` y `--update`
se aplican a cada curso de la ruta.

---

## Subtítulos bilingües

`--lang es+en` descarga **dos pistas** del mismo vídeo y las junta por tiempo: el texto principal es el
primer idioma y debajo de cada párrafo va el mismo tramo en el segundo.

```markdown
[00:00](https://…/learn/lecture/26140426?start=0) Hola y bienvenido a este curso. En este curso, aprenderá todo sobre Amazon Web Services…

> **en** · Hello and welcome to this course. In this course you're going to learn all about Amazon Web Services…
```

- **Alineación:** cada cue de la segunda pista va al párrafo en cuya ventana de tiempo cae su punto medio,
  así que no importa que las dos pistas partan las frases de forma distinta.
- **Formatos:** en Markdown, un bloque `> **en** · …` bajo cada párrafo; en `.txt`, una línea con sangría
  `    ↳ en: …`. La cabecera YAML añade `idioma_secundario` y el índice muestra `es_ES + en_US`.
- **Qué pasa si falta una pista:** una lección sin la segunda pista sale en un solo idioma y se avisa
  (`sin pista en`); si la descarga de la segunda falla, se avisa y `--update` lo reintenta.
- **Idiomas disponibles:** depende del curso. Algunos solo traen uno (los de ejemplo, `es_LA`); otros traen
  decenas de pistas, a veces traducidas automáticamente (se marcan «(automático)»). Usa los códigos de
  idioma (`es`, `en`, `pt_BR`, `fr`…). Con un par, ese idioma pasa a ser la primera preferencia; puedes
  añadir alternativas: `--lang es+en,pt`.
- El estudio con IA (`--study`) **no** envía la segunda columna al modelo.

---

## Estudio con IA: resúmenes y flashcards

`--study` convierte lo descargado en material de repaso, **por sección**:

```
<curso>/
  flashcards.csv                      todas las tarjetas del curso (para importarlas de una vez en Anki)
  02 - Introducción a Spring boot/
    RESUMEN.md                        ideas clave, conceptos, código y comandos mencionados, preguntas de repaso
    flashcards.csv                    pregunta;respuesta;etiquetas
```

Dos modos:

| Modo | Qué hace | Coste |
|---|---|---|
| `--study api` | Llama a la API de Claude con **tu clave**, una petición por sección (las muy largas se parten). **Antes de empezar estima los tokens y el coste y pide confirmación** (`--yes` para aceptar). | El de la API (p. ej. ≈ 5 USD el curso de 35 h con `claude-opus-5-5`; usa `--ai-model claude-sonnet-5-5` o `claude-haiku-5-5` para gastar menos) |
| `--study prompt` | Escribe en `prompts/` un archivo por sección, listo para pegar en Claude o ChatGPT con tu suscripción. Tú guardas las respuestas. | Ninguno |

```bash
udemy --update --study prompt "<url>"                 # descarga lo que falte y genera los prompts
udemy --study api --ai-model claude-sonnet-5-5 "<url>"
udemy --study api --study-from ~/Udemy-Transcripts/Mi\ curso --sections 2-4   # sin abrir Udemy
```

- **Requisitos del modo `api`:** `pip install "udemy-transcripts[ai]"` (Python 3.10+) y credenciales de
  Anthropic (`ANTHROPIC_API_KEY`, o `ant auth login`). Modelo por defecto: `claude-opus-5-5`
  (`--ai-model`). Usa salida estructurada (JSON con esquema) y esfuerzo `low`; en los modelos que lo
  admiten activa el *fallback* del servidor, de modo que si el modelo rechaza una petición, Anthropic la
  repite con otro.
- **Caché:** `.estudio/<sección>.json` guarda lo generado con la huella del texto, el modelo y la versión
  de las instrucciones. Si repites el comando solo se regeneran las secciones cuyo texto cambió
  (`--regenerate` lo fuerza). Si una sección falla, las demás se conservan y se reintenta solo esa.
- **Anki:** `flashcards.csv` lleva las directivas `#separator:semicolon`, `#html:false` y
  `#tags column:3`, sin fila de cabecera: *Archivo → Importar* y listo. Cada tarjeta lleva además la
  etiqueta `seccion-NN`.
- **Fidelidad:** los prompts piden trabajar solo con lo que dicen las transcripciones y no inventar
  código; aun así el resultado de un modelo puede tener errores: revísalo antes de memorizarlo.
- **Privacidad:** con `--study api` el texto de las lecciones **sale hacia la API de Anthropic**. Comprueba
  que las condiciones de tu curso o de tu empresa (en Udemy Business, el contrato de tu organización) lo
  permiten; `--study prompt` también obliga a pegar ese texto en un chat. Úsalo solo para estudio personal.

---

## Opciones

| Flag | Para qué |
|------|----------|
| `--format md\|txt` | Formato de salida (default `md`) |
| `--single` | Todo el curso en UN solo archivo, con tabla de contenidos |
| `--txt` | El modo clásico: equivale a `--single --format txt` |
| `--update` | Solo lo nuevo o cambiado; reanuda una descarga cortada |
| `--resources` | Descarga también los adjuntos (PDF, código, zip…) y las imágenes de los artículos |
| `--resources-only` | Solo los recursos, sin transcripciones ni artículos |
| `--resource-types EXT` | Solo estas extensiones (`pdf,zip`) |
| `--max-size TAM` | Omite archivos más grandes (default `500MB`) |
| `--yes` | No pedir confirmación cuando los recursos pesan mucho |
| `--sections R` / `--lectures R` | Solo estas secciones / lecciones (`3-5,8`, `12-`) |
| `--study api\|prompt` | Resumen y flashcards por sección con IA (ver «Estudio con IA») |
| `--ai-model MODELO` | Modelo de `--study api` (default `claude-opus-5-5`) |
| `--study-from CARPETA` | Estudia un curso ya descargado, sin abrir el navegador |
| `--regenerate` | Ignora la caché del estudio |
| `--no-timestamps` | Sin marcas de tiempo al inicio de los párrafos |
| `--ts-every SEG` | Como mucho una marca de tiempo cada SEG segundos (default: una por párrafo) |
| `--list` | Lista tus cursos suscritos (con su id) y termina |
| `--lang es,en` | Orden de preferencia del idioma del subtítulo (default `es,en`); `es+en` = bilingüe |
| `--out RUTA` | Carpeta base de salida (default `~/Udemy-Transcripts`) |
| `--width N` | Ancho de línea (solo `--format txt`); `0` = no ajustar (default `100`) |
| `--business ORG` | Organización de Udemy Business (`miempresa` para `miempresa.udemy.com`); también `UDEMY_BUSINESS` |
| `--token TOK` | `access_token` de la cookie, para evitar el login manual (avanzado; también `UDEMY_TOKEN`) |
| `--headless` | No recomendado: Udemy bloquea el modo sin ventana con Cloudflare |
| `--version` | Muestra la versión |

---

### Variables de entorno

| Variable | Equivale a |
|---|---|
| `UDEMY_OUT` | `--out` (carpeta base) |
| `UDEMY_BUSINESS` | `--business` |
| `UDEMY_TOKEN` | `--token` |
| `ANTHROPIC_API_KEY` | Credencial de `--study api` (o inicia sesión con `ant auth login`) |

### Códigos de salida

`0` todo bien (o hay lecciones nuevas/ya vigentes) · `1` error o no se pudo guardar nada · `2` argumentos
inválidos · `130` interrumpido con Ctrl-C (lo ya descargado se conserva: sigue con `--update`).

---

## Problemas frecuentes

| Síntoma | Qué hacer |
|---|---|
| «Cloudflare bloqueó la petición» | Ejecuta con la ventana visible (sin `--headless`) y espera a que termine la verificación. |
| «La sesión no es válida o caducó» | Vuelve a lanzar el comando: se abre Chromium y inicias sesión de nuevo. |
| «Sin acceso al temario… Empezar curso» (Business) | Abre el curso una vez en el portal y pulsa **Empezar curso**; repite. |
| «No hay sesión y no puedo pedir el login sin terminal» | Lanza el comando una vez desde una terminal interactiva (o usa `--token`). |
| La descarga se cortó | Repite el mismo comando con `--update`: continúa donde quedó. |
| Un archivo de recursos no se guardó | Mira el aviso (`HTTP 403 ¿URL caducada?`, tamaño > `--max-size`) y repite con `--update`/`--max-size`. |
| `FileNotFoundError` o rutas largas en Windows | La herramienta ya usa rutas largas; si instalas en una carpeta muy profunda, usa `-AppDir C:\udemy`. |
| `--study api` pide `--yes` | No hay terminal para confirmar el envío a la API: añade `--yes` si aceptas el coste estimado. |
| Los subtítulos salen en otro idioma | Se avisa en el log (`usando en_US, no hay es`); revisa `--lang`. |

---

## Errores y reintentos

- Los fallos transitorios (HTTP 429/5xx, red) se reintentan solos con espera creciente.
- Si no hay sesión, no estás inscrito en el curso o Cloudflare bloquea la petición, la herramienta
  termina con un mensaje claro y código de salida 1 (ya no acaba en «Listo: 0»).
- Si el idioma pedido no existe para una lección se avisa: `usando en_US, no hay es`.
- Si ninguna transcripción se pudo guardar, el código de salida es 1.

---

## Cómo funciona

1. Abre Chromium con tu sesión de Udemy.
2. Lee el temario del curso por la API interna de Udemy.
3. Descarga el archivo de subtítulos (`.vtt`) de cada video.
4. Lo agrupa en párrafos con marcas de tiempo y lo guarda como Markdown (o `.txt`).
5. Convierte los artículos y, con `--resources`, descarga los adjuntos.
6. Con `--study`, genera resúmenes y flashcards por sección.

Solo necesita Playwright (el instalador lo incluye). Diseño interno: [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md);
hoja de ruta: [docs/PLAN.md](docs/PLAN.md).

---

## Desarrollo

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev,ai]"    # en Windows: .venv\Scripts\pip
.venv/bin/python -m pytest                                    # tests sin red
```

`python udemy_transcripts.py ...` sigue funcionando desde el repositorio (envoltorio del paquete).

---

## Licencia

MIT — ver [LICENSE](LICENSE).
