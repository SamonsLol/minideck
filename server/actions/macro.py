# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Macro: ejecuta una secuencia de acciones con pausas opcionales."""
import time

from . import REGISTRY, action, validate_params


@action("macro", schema={"steps": {"type": "list", "required": True}}, timeout=300)
def macro(params: dict):
    """Ejecuta pasos en orden.
    params: {
      "steps": [
        {"action": "launch",  "params": {"path": "C:/.../obs64.exe"}},
        {"delay_ms": 2000},
        {"action": "hotkey",  "params": {"keys": "ctrl+shift+1"}}
      ]
    }
    Un paso puede ser una acción, una pausa ({"delay_ms": N}), o ambas
    (la pausa se aplica DESPUÉS de la acción).
    """
    steps = params.get("steps") or []
    if not steps:
        raise ValueError("La macro no tiene pasos ('steps')")

    executed = 0
    for i, step in enumerate(steps, start=1):
        name = step.get("action")
        if name:
            fn = REGISTRY.get(name)
            if fn is None:
                raise ValueError(f"Paso {i}: acción desconocida '{name}'")
            step_params = dict(step.get("params") or {})
            try:
                validate_params(name, step_params)
            except ValueError as exc:
                raise ValueError(f"Paso {i} ({name}): {exc}") from None
            fn(step_params)
            executed += 1
        delay = step.get("delay_ms")
        if delay:
            time.sleep(int(delay) / 1000)

    return {"message": f"Macro completada ({executed} acciones)"}
