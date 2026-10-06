#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
# MiniDeck — genera un certificado HTTPS de confianza (con mkcert) para poder
# instalar la PWA sin barras en Android (Chrome/Brave exigen HTTPS de confianza).
#   bash build/make_cert.command
set -e
DEST="$HOME/Library/Application Support/MiniDeck/certs"
mkdir -p "$DEST"

if ! command -v mkcert >/dev/null 2>&1; then
  echo ">> Instalando mkcert (necesita Homebrew)..."
  brew install mkcert nss
fi

echo ">> Instalando la CA local en este Mac..."
mkcert -install

IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1)"
HOST="$(scutil --get LocalHostName 2>/dev/null || hostname -s)"

echo ">> Generando certificado para: localhost 127.0.0.1 $IP $HOST.local"
mkcert -cert-file "$DEST/cert.pem" -key-file "$DEST/key.pem" \
       localhost 127.0.0.1 "$IP" "$HOST.local"

cp "$(mkcert -CAROOT)/rootCA.pem" "$DEST/rootCA.pem"

echo ""
echo "OK. Certificado en: $DEST"
echo ""
echo "AHORA, en el teléfono Android (una sola vez):"
echo "  1) Envíate el archivo:  $DEST/rootCA.pem  (AirDrop no; usa correo, Drive, USB…)"
echo "  2) Ajustes → Seguridad → Cifrado y credenciales → Instalar un certificado"
echo "     → Certificado de CA → elige rootCA.pem"
echo "  3) Reinicia MiniDeck (ahora servirá por HTTPS) y abre:  https://$IP:8765"
echo "     Chrome/Brave: menú → Instalar app / Añadir a pantalla de inicio → se abre sin barras"
echo ""
echo "Si cambias de red WiFi (tu IP cambia), vuelve a ejecutar este script."
open "$DEST" 2>/dev/null || true
