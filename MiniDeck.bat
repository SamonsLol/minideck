@echo off
rem MiniDeck: doble clic para arrancar el servidor con icono en la bandeja.
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0server\run.ps1"
