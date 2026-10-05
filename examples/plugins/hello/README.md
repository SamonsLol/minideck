# Plugin de ejemplo: hello

Plantilla mínima pero completa de un plugin de MiniDeck:

- `hello_say`: acción que saluda (usa el ajuste `greeting`) y suma un contador.
- `hello_get`: fuente de estado que envía el contador al móvil.
- Widget `hello`: muestra el contador y ejecuta `hello_say` al tocarlo.

Instalación: copia esta carpeta `hello/` a tu carpeta de plugins (ver
[docs/PLUGINS.md](../../../docs/PLUGINS.md)) y reinicia MiniDeck. Luego, en el
editor del deck, añade un widget de tipo «Hola mundo».
