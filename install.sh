#!/usr/bin/env bash
# Instalador de udemy-transcripts para macOS y Linux (también sirve en Git Bash de Windows).
# Crea un entorno aislado con el paquete, Playwright y Chromium, y el comando global `udemy`.
#
#   bash install.sh                 instala (o actualiza)
#   bash install.sh --with-ai       además instala el SDK de Anthropic (para --study api; Python 3.10+)
#   bash install.sh --skip-browser  no descarga Chromium (ya lo tienes o lo harás luego)
#   bash install.sh --uninstall     borra el entorno y el comando (no toca tus descargas ni tu sesión)
#
# Variables opcionales: UDEMY_APP_DIR (default ~/.local/share/udemy-transcripts)
#                       UDEMY_BIN_DIR (default ~/.local/bin)
set -euo pipefail

APP_DIR="${UDEMY_APP_DIR:-$HOME/.local/share/udemy-transcripts}"
BIN_DIR="${UDEMY_BIN_DIR:-$HOME/.local/bin}"
VENV="$APP_DIR/venv"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
WITH_AI=0; SKIP_BROWSER=0; UNINSTALL=0

for arg in "$@"; do
  case "$arg" in
    --with-ai) WITH_AI=1 ;;
    --skip-browser) SKIP_BROWSER=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "✗ Opción desconocida: $arg (usa --help)"; exit 2 ;;
  esac
done

if [ "$UNINSTALL" = 1 ]; then
  rm -rf "$APP_DIR"
  rm -f "$BIN_DIR/udemy"
  echo "✓ udemy-transcripts desinstalado."
  echo "  Se conservan tus descargas (~/Udemy-Transcripts) y tu sesión de Udemy"
  echo "  (~/.cache/udemy-transcripts-profile): bórralos a mano si ya no los quieres."
  exit 0
fi

echo "▶ Instalando udemy-transcripts…"

# 1) Python: el primero de python3/python que sea 3.8+ (3.10+ con --with-ai)
MIN_MINOR=8; [ "$WITH_AI" = 1 ] && MIN_MINOR=10
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && \
     "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, $MIN_MINOR) else 1)" 2>/dev/null; then
    PY="$candidate"; break
  fi
done
if [ -z "$PY" ]; then
  echo "✗ Necesitas Python 3.$MIN_MINOR o superior. Mac: 'brew install python'. Linux: tu gestor de paquetes."
  [ "$WITH_AI" = 1 ] && echo "  (--with-ai requiere 3.10+; sin él basta con 3.8)"
  exit 1
fi
echo "  • Python: $("$PY" --version 2>&1)"

# 2) entorno aislado + paquete (instala también Playwright)
mkdir -p "$APP_DIR" "$BIN_DIR"
rm -f "$APP_DIR/udemy_transcripts.py"   # script suelto de versiones anteriores
echo "  • Creando entorno virtual…"
"$PY" -m venv "$VENV"
if [ -d "$VENV/Scripts" ]; then VBIN="$VENV/Scripts"; else VBIN="$VENV/bin"; fi   # Git Bash / Unix
"$VBIN/python" -m pip install --quiet --upgrade pip
TARGET="$SRC_DIR"; [ "$WITH_AI" = 1 ] && TARGET="$SRC_DIR[ai]"
echo "  • Instalando udemy-transcripts y Playwright…"
"$VBIN/python" -m pip install --quiet --upgrade "$TARGET"
if [ "$SKIP_BROWSER" = 1 ]; then
  echo "  • Chromium: omitido (--skip-browser). Instálalo con: $VBIN/python -m playwright install chromium"
else
  echo "  • Descargando Chromium (~170 MB, puede tardar)…"
  "$VBIN/python" -m playwright install chromium
fi

# 3) comando global `udemy`
cat > "$BIN_DIR/udemy" <<EOF
#!/usr/bin/env bash
exec "$VBIN/udemy" "\$@"
EOF
chmod +x "$BIN_DIR/udemy"

echo ""
echo "✓ ¡Listo! $("$VBIN/udemy" --version) → comando: udemy"

# 4) avisar si el directorio de comandos no está en el PATH
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo ""
    echo "⚠ $BIN_DIR no está en tu PATH. Añádelo con:"
    echo "    echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc   # o ~/.bashrc"
    echo "  y reinicia la terminal."
    ;;
esac

echo ""
echo "Uso:"
echo "    udemy --list                                          # ver tus cursos"
echo "    udemy \"https://www.udemy.com/course/...\"              # Markdown, un archivo por lección"
echo "    udemy --resources --update \"https://www.udemy.com/course/...\""
echo "    udemy --help                                          # todas las opciones"
