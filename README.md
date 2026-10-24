# udemy-transcripts

Descarga las **transcripciones (subtítulos)** de todos los videos de un curso de Udemy (personal o **Udemy Business**) y las guarda como **Markdown** listo para estudiar.

- Convierte los subtítulos a **párrafos legibles** con **marcas de tiempo que enlazan al segundo exacto del vídeo**.
- Cada lección lleva cabecera YAML (curso, sección, URL, duración, idioma…) y el curso un `README.md` índice: compatible con Obsidian, Notion y VS Code.
- Tres salidas: **un archivo por video**, **todo el curso en un solo archivo** (con tabla de contenidos) o el `.txt` clásico.
- **`--update`** descarga solo lo nuevo o cambiado y reanuda una descarga cortada.
- Usa un navegador real (Playwright) para reutilizar tu sesión y atravesar la protección Cloudflare de Udemy.

> ⚠️ **Uso responsable:** descarga solo cursos a los que **tú tienes acceso** y úsalo para estudio personal. No redistribuyas el contenido.

---

## Requisitos

- **Python 3.8+**
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

El instalador crea un entorno aislado (no toca tu Python del sistema) y deja el comando global **`udemy`**. Si la terminal no lo reconoce, reiníciala (o añade la carpeta indicada al PATH).

---

## Uso

```bash
udemy --list                                     # lista tus cursos y su id
udemy "https://www.udemy.com/course/mi-curso/"   # Markdown: un .md por video + README.md índice
udemy --single "https://www.udemy.com/course/mi-curso/"   # todo el curso en un solo .md
udemy --format txt "https://www.udemy.com/course/mi-curso/"   # texto plano, un .txt por video
udemy --update "https://www.udemy.com/course/mi-curso/"   # solo lo nuevo o cambiado
```

Puedes pasarle la URL de la página del curso **o** la del reproductor (`/learn/lecture/...`), o directamente el id numérico.

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
url: "https://miempresa.udemy.com/course/java-spring-boot-guia-definitiva/learn/lecture/51621647"
duracion: "09:58"
idioma: "es_LA"
subtitulo_automatico: false
---

# Spring boot: @Controller parte 1

[00:05](https://…/learn/lecture/51621647?start=5) Hola a todos, bienvenidos a un nuevo vídeo…

[00:38](https://…/learn/lecture/51621647?start=38) Importante que tengamos esta versión…
```

- **Párrafos:** se corta tras una pausa de 2,5 s o más, o cuando el párrafo pasa de ~400 caracteres y termina una oración. Si el subtítulo es automático y no tiene puntuación, solo corta por pausas.
- **Marcas de tiempo:** una por párrafo (`--ts-every 60` las espacia a una por minuto como mucho; `--no-timestamps` las quita). En `.txt` salen como `[04:15]`, sin enlace.
- **Texto:** en Markdown se escapan los caracteres especiales (`_`, `*`, `<`…) para que `snake_case` o `Map<K, V>` se vean tal cual.

### `--update` y reanudar

`<curso>/.udemy-transcripts.json` guarda, por lección, el archivo generado, el idioma y la huella del
subtítulo. Con `--update` solo se baja una lección si es nueva, si el instructor cambió el subtítulo,
si cambiaste el formato o las opciones, o si borraste su archivo; lo demás se omite sin descargar
nada. Si una descarga se corta (Ctrl-C, red, error), vuelve a lanzar el mismo comando con `--update`
y continúa donde quedó. Si una lección cambia de nombre, se escribe con el nombre nuevo y el archivo
anterior se conserva (se avisa). `--update` no aplica a `--single`.

---

## Opciones

| Flag | Para qué |
|------|----------|
| `--format md\|txt` | Formato de salida (default `md`) |
| `--single` | Todo el curso en UN solo archivo, con tabla de contenidos |
| `--txt` | El modo clásico: equivale a `--single --format txt` |
| `--update` | Solo lo nuevo o cambiado; reanuda una descarga cortada |
| `--no-timestamps` | Sin marcas de tiempo al inicio de los párrafos |
| `--ts-every SEG` | Como mucho una marca de tiempo cada SEG segundos (default: una por párrafo) |
| `--list` | Lista tus cursos suscritos (con su id) y termina |
| `--lang es,en` | Orden de preferencia del idioma del subtítulo (default `es,en`) |
| `--out RUTA` | Carpeta base de salida (default `~/Udemy-Transcripts`) |
| `--width N` | Ancho de línea (solo `--format txt`); `0` = no ajustar (default `100`) |
| `--business ORG` | Organización de Udemy Business (`miempresa` para `miempresa.udemy.com`); también `UDEMY_BUSINESS` |
| `--token TOK` | `access_token` de la cookie, para evitar el login manual (avanzado) |

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

Solo necesita Playwright (el instalador lo incluye). Diseño interno: [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md);
hoja de ruta: [docs/PLAN.md](docs/PLAN.md).

---

## Desarrollo

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"    # en Windows: .venv\Scripts\pip
.venv/bin/python -m pytest                                    # tests sin red
```

`python udemy_transcripts.py ...` sigue funcionando desde el repositorio (envoltorio del paquete).

---

## Licencia

MIT — ver [LICENSE](LICENSE).
