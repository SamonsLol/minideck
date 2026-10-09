# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
# MiniDeck - genera un certificado HTTPS de confianza (con mkcert) en Windows.
# Hace falta para usar la cámara del móvil (webcam) y para instalar la PWA
# sin barras en Android.
#   powershell -ExecutionPolicy Bypass -File build\make_cert.ps1
$ErrorActionPreference = "Stop"
$dest = Join-Path $env:APPDATA "MiniDeck\certs"
New-Item -ItemType Directory -Force $dest | Out-Null

if (-not (Get-Command mkcert -ErrorAction SilentlyContinue)) {
    Write-Host ">> Instalando mkcert con winget..."
    winget install --id FiloSottile.mkcert -e --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "Machine")
}

Write-Host ">> Instalando la CA local en este PC..."
mkcert -install

$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.PrefixOrigin -ne "WellKnown" } |
    Select-Object -ExpandProperty IPAddress
$names = @("localhost", "127.0.0.1", "$env:COMPUTERNAME.local") + $ips

Write-Host ">> Generando certificado para: $($names -join ' ')"
mkcert -cert-file (Join-Path $dest "cert.pem") -key-file (Join-Path $dest "key.pem") @names
Copy-Item (Join-Path (mkcert -CAROOT) "rootCA.pem") (Join-Path $dest "rootCA.pem") -Force

$ip = $ips | Select-Object -First 1
Write-Host ""
Write-Host "OK. Certificado en: $dest"
Write-Host ""
Write-Host "AHORA, en el teléfono (una sola vez):"
Write-Host "  1) Envíate el archivo $dest\rootCA.pem (correo, Drive, USB...)"
Write-Host "  2) Android: Ajustes > Seguridad > Cifrado y credenciales > Instalar un certificado > Certificado de CA"
Write-Host "     iPhone: abre el archivo, instala el perfil y actívalo en Ajustes > General > Información > Confianza de certificados"
Write-Host "  3) Reinicia MiniDeck (ahora sirve por HTTPS) y abre https://${ip}:8765"
Write-Host ""
Write-Host "Si cambias de red WiFi (cambia tu IP), vuelve a ejecutar este script."
Start-Process explorer.exe $dest
