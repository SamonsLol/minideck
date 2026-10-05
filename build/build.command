#!/bin/bash
# MiniDeck — construir la app de barra de menú (.app). Doble clic o:
#   bash build/build.command
set -e
cd "$(dirname "$0")/.."          # raíz del proyecto
ROOT="$(pwd)"
echo "== MiniDeck :: build en $ROOT =="

# 1) venv de build (de usuario)
if [ ! -x buildenv/bin/pyinstaller ]; then
  echo ">> Creando venv de build e instalando dependencias..."
  python3 -m venv buildenv
  ./buildenv/bin/pip install -q --upgrade pip
  ./buildenv/bin/pip install -q -r requirements-mac.txt
fi

# 2) limpiar y construir
rm -rf build/work dist/MiniDeck.app
./buildenv/bin/pyinstaller build/minideck.spec --noconfirm \
    --distpath dist --workpath build/work

# 3) firma ad-hoc (permite ejecutarla localmente)
codesign --deep --force --sign - "dist/MiniDeck.app" 2>/dev/null || true

echo ""
echo "OK -> dist/MiniDeck.app"
echo "Arrástrala a /Applications. En OTRO Mac, la primera vez: clic derecho -> Abrir"
echo "(o:  xattr -dr com.apple.quarantine /Applications/MiniDeck.app )"
open dist 2>/dev/null || true
