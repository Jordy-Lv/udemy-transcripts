# udemy-transcripts

Descarga las **transcripciones (subtítulos)** de todos los videos de un curso de Udemy y las guarda como `.txt` limpio, listo para estudiar.

- Convierte los subtítulos a texto legible (sin marcas de tiempo, sin líneas repetidas, con ajuste de línea).
- Dos modos: **un archivo por video** o **todo el curso en un solo `.txt`**.
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
udemy --list                                    # lista tus cursos y su id
udemy "https://www.udemy.com/course/mi-curso/"  # un .txt por cada video
udemy --txt "https://www.udemy.com/course/mi-curso/"  # todo en un solo .txt
```

Puedes pasarle la URL de la página del curso **o** la del reproductor (`/learn/lecture/...`), o directamente el id numérico.

### La primera vez
Se abre una ventana de Chromium. **Inicia sesión en Udemy ahí.** La sesión queda guardada, así que las siguientes veces no tendrás que volver a loguearte.

> El modo con ventana es obligatorio: Udemy bloquea los navegadores "headless" con Cloudflare.

---

## Dónde se guardan

| Modo | Resultado |
|------|-----------|
| normal | `~/Udemy-Transcripts/<curso>/001 - título.txt`, `002 - …` (un archivo por video) |
| `--txt` | `~/Udemy-Transcripts/<curso>.txt` (todo el curso en uno) |

Cambia la carpeta base con `--out RUTA` o con la variable de entorno `UDEMY_OUT`.

---

## Opciones

| Flag | Para qué |
|------|----------|
| `--txt` | Todo el curso en un solo `.txt` en vez de uno por video |
| `--list` | Lista tus cursos suscritos (con su id) y termina |
| `--lang es,en` | Orden de preferencia del idioma del subtítulo (default `es,en`) |
| `--out RUTA` | Carpeta base de salida (default `~/Udemy-Transcripts`) |
| `--width N` | Ancho de línea del texto; `0` = no ajustar (default `100`) |
| `--token TOK` | `access_token` de la cookie, para evitar el login manual (avanzado) |

---

## Cómo funciona

1. Abre Chromium con tu sesión de Udemy.
2. Lee el temario del curso por la API interna de Udemy.
3. Descarga el archivo de subtítulos (`.vtt`) de cada video.
4. Lo limpia y lo guarda como `.txt`.

Solo necesita la librería estándar de Python + Playwright.

---

## Licencia

MIT — ver [LICENSE](LICENSE).
