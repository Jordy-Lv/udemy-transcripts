# Changelog

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
