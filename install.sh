#!/usr/bin/env bash
# Instalador de udemy-transcripts para macOS y Linux.
# Crea un entorno aislado con Playwright + Chromium y el comando global `udemy`.
set -e

APP_DIR="$HOME/.local/share/udemy-transcripts"
VENV="$APP_DIR/venv"
BIN_DIR="$HOME/.local/bin"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "▶ Instalando udemy-transcripts…"

# 1) Python 3
if ! command -v python3 >/dev/null 2>&1; then
  echo "✗ Necesitas Python 3 instalado. Mac: 'brew install python'. Linux: usa tu gestor de paquetes."
  exit 1
fi

# 2) entorno aislado + script
mkdir -p "$APP_DIR" "$BIN_DIR"
cp "$SRC_DIR/udemy_transcripts.py" "$APP_DIR/udemy_transcripts.py"
echo "  • Creando entorno virtual…"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip >/dev/null
echo "  • Instalando Playwright…"
"$VENV/bin/pip" install playwright >/dev/null
echo "  • Descargando Chromium (~170 MB, puede tardar)…"
"$VENV/bin/python" -m playwright install chromium

# 3) comando global `udemy`
cat > "$BIN_DIR/udemy" <<EOF
#!/bin/bash
exec "$VENV/bin/python" "$APP_DIR/udemy_transcripts.py" "\$@"
EOF
chmod +x "$BIN_DIR/udemy"

echo ""
echo "✓ ¡Listo! Comando instalado: udemy"

# 4) avisar si ~/.local/bin no está en el PATH
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo ""
    echo "⚠ $BIN_DIR no está en tu PATH. Añádelo con:"
    echo "    echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc   # o ~/.bashrc"
    echo "  y reinicia la terminal."
    ;;
esac

echo ""
echo "Uso:"
echo "    udemy --list                                   # ver tus cursos"
echo "    udemy \"https://www.udemy.com/course/...\"         # un .txt por video"
echo "    udemy --txt \"https://www.udemy.com/course/...\"   # todo en un solo .txt"
