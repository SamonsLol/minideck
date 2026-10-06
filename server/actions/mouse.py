# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Acciones de ratón: clic en coordenadas de pantalla.
Requiere: pip install pyautogui

Útil para automatizar apps que no tienen atajos ni línea de comandos
(como darle "Conectar" a un cliente VPN dentro de una macro).

Para averiguar las coordenadas de un punto de la pantalla, ejecuta en
una consola:  python -c "import pyautogui, time; time.sleep(3); print(pyautogui.position())"
y en esos 3 segundos pon el cursor sobre el botón que quieres.
"""
import pyautogui

from . import action

pyautogui.FAILSAFE = True  # mover el ratón a la esquina sup. izq. aborta


@action("mouse_click", schema={"x": {"type": "int", "required": True}, "y": {"type": "int", "required": True}, "clicks": {"type": "int", "min": 1, "max": 10}, "button": {"type": "str", "choices": ["left", "right", "middle"]}})
def mouse_click(params: dict):
    """Clic en coordenadas absolutas de pantalla.
    params: {"x": 960, "y": 540, "button": "left", "clicks": 1}
    """
    x = params.get("x")
    y = params.get("y")
    if x is None or y is None:
        raise ValueError("Faltan las coordenadas 'x' e 'y'")
    pyautogui.click(x=int(x), y=int(y),
                    clicks=int(params.get("clicks", 1)),
                    button=params.get("button", "left"))
    return {"message": f"Clic en ({x}, {y})"}


@action("mouse_move", schema={"x": {"type": "int", "required": True}, "y": {"type": "int", "required": True}})
def mouse_move(params: dict):
    """Mueve el cursor sin hacer clic. params: {"x": 100, "y": 200}"""
    pyautogui.moveTo(int(params.get("x", 0)), int(params.get("y", 0)))
    return {"message": "Cursor movido"}
