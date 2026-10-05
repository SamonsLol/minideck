# Política de seguridad

MiniDeck controla tu equipo de forma remota (teclado, comandos, apagado…), así que la seguridad es prioritaria.

## Modelo de amenazas

- **Protegido:** otros dispositivos de tu red local sin el token, y webs maliciosas abiertas en tu navegador (CSRF, *cross-site WebSocket hijacking*, DNS rebinding).
- **No protegido:** quien tenga tu token (equivale a acceso total), quien tenga acceso a tu cuenta de usuario del equipo, y plugins de terceros (son código que corre con tus permisos).
- Sin certificados TLS, el tráfico va **sin cifrar** por la red local. En redes no confiables (WiFi pública, oficina), genera certificados (ver README_MAC.md, sección 11) o no uses MiniDeck.

## Buenas prácticas

- No expongas el puerto 8765 a Internet. Para acceso remoto, usa una VPN (Tailscale, WireGuard).
- Para revocar todos los dispositivos emparejados, borra `auth_token` de la carpeta de config y reinicia.
- Nunca subas a git `deck.json`, `discord.json` ni `auth_token` (ya están en `.gitignore`).

## Reportar una vulnerabilidad

**No abras un issue público.** Usa [GitHub Security Advisories](https://github.com/SamonsLol/minideck/security/advisories/new) ("Report a vulnerability"). Incluye versión, sistema operativo, pasos para reproducirla e impacto. Intentaremos responder en 7 días.

## Versiones soportadas

Solo la última versión publicada recibe parches de seguridad.
