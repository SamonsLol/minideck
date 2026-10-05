#!/bin/bash
# MiniDeck — crear el instalador .dmg (arrastrar a Aplicaciones).
# Requiere dist/MiniDeck.app (ejecuta antes build/build.command). Uso:
#   bash build/make_dmg.command
set -e
cd "$(dirname "$0")/.."          # raíz del proyecto
APP="dist/MiniDeck.app"
DMG="dist/MiniDeck.dmg"

if [ ! -d "$APP" ]; then
  echo "No existe $APP — ejecuta primero:  bash build/build.command"
  exit 1
fi

echo ">> Preparando contenido del DMG..."
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"     # atajo para arrastrar

echo ">> Creando $DMG ..."
rm -f "$DMG"
hdiutil create -volname "MiniDeck" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"

echo ""
echo "OK -> $DMG"
echo "Ábrelo y arrastra MiniDeck a Aplicaciones."
open dist 2>/dev/null || true
