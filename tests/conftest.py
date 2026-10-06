# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Configura un entorno aislado ANTES de importar el servidor: config,
token y plugins de usuario van a carpetas temporales."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "server"
sys.path.insert(0, str(SERVER))

_TMP = Path(tempfile.mkdtemp(prefix="minideck-test-"))
os.environ["MINIDECK_CONFIG_DIR"] = str(_TMP / "config")
os.environ["MINIDECK_PLUGINS_DIR"] = str(_TMP / "plugins")
os.environ["MINIDECK_TOKEN"] = "test-token"
os.environ.pop("MINIDECK_NO_AUTH", None)

# El plugin de ejemplo de la documentación se instala como plugin de usuario:
# si la plantilla se rompe, los tests fallan.
shutil.copytree(ROOT / "examples" / "plugins" / "hello", _TMP / "plugins" / "hello")

# Plugin para otra plataforma: debe saltarse
_other = _TMP / "plugins" / "otherplat"
_other.mkdir(parents=True)
(_other / "plugin.json").write_text(json.dumps({"platforms": ["nonexistent-os"]}),
                                    encoding="utf-8")
(_other / "plugin.py").write_text("raise RuntimeError('no debería cargarse')\n",
                                  encoding="utf-8")

# Plugin roto: debe reportar error sin tumbar el servidor
_broken = _TMP / "plugins" / "broken"
_broken.mkdir()
(_broken / "plugin.py").write_text("import paquete_que_no_existe_xyz\n", encoding="utf-8")
