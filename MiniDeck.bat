@echo off
rem SPDX-License-Identifier: AGPL-3.0-or-later
rem SPDX-FileCopyrightText: 2026 Samons
rem MiniDeck: doble clic para arrancar el servidor con icono en la bandeja.
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0server\run.ps1"
