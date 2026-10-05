"""Macro: ejecuta una secuencia de acciones con pausas opcionales."""
import time

from . import REGISTRY, action


@action("macro")
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
            fn(step.get("params") or {})
            executed += 1
        delay = step.get("delay_ms")
        if delay:
            time.sleep(int(delay) / 1000)

    return {"message": f"Macro completada ({executed} acciones)"}
