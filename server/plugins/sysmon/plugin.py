"""Plugin de ejemplo: monitor de CPU y RAM del PC.

Anatomía de un plugin de MiniDeck:
  server/plugins/sysmon/
      plugin.py     ← este archivo: acciones Python
      widget.js     ← el widget de frontend (opcional)
      widget.css    ← sus estilos (opcional)

Con @action("...", state=True) el vigilante sondea la acción cada
segundo y difunde sus cambios a todos los clientes automáticamente.
"""
import psutil

from actions import action

_GB = 1024 ** 3


@action("sysmon_get", state=True)
def sysmon_get(params: dict):
    """CPU, RAM y disco actuales (porcentaje + GB usados/totales). params: {}"""
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    data = {
        "cpu": round(psutil.cpu_percent(interval=None)),
        "ram": round(vm.percent),
        "ram_used": round(vm.used / _GB, 1),
        "ram_total": round(vm.total / _GB, 1),
        "disk": round(du.percent),
        "disk_used": round(du.used / _GB),
        "disk_total": round(du.total / _GB),
    }
    try:
        bat = psutil.sensors_battery()
        if bat is not None:
            data["battery"] = round(bat.percent)
            data["charging"] = bool(bat.power_plugged)
    except Exception:  # noqa: BLE001
        pass
    return {"state": {"sysmon": data}}
