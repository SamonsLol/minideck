# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""El wheel de pip nunca debe incluir datos personales ni secretos.

Se construye con los archivos privados PRESENTES (como en el equipo de quien
desarrolla) y se comprueba que no entran. Requiere: pip install build hatchling
"""
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytest.importorskip("build")
pytest.importorskip("hatchling")

SECRETS = {
    "server/config/deck.json": '{"pages": [{"id": "p", "buttons": []}]}',
    "server/config/discord.json": '{"client_secret": "NO-DEBE-SALIR"}',
    "server/config/auth_token": "NO-DEBE-SALIR",
}


def test_wheel_has_no_private_data(tmp_path):
    created = []
    for rel, content in SECRETS.items():
        p = ROOT / rel
        if not p.exists():
            p.write_text(content, encoding="utf-8")
            created.append(p)
    try:
        subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation",
                        "--outdir", str(tmp_path), str(ROOT)],
                       check=True, capture_output=True, text=True, timeout=300)
    finally:
        for p in created:
            p.unlink()
    wheel = next(tmp_path.glob("*.whl"))
    names = zipfile.ZipFile(wheel).namelist()
    leaked = [n for n in names
              if n.endswith(("deck.json", "discord.json", "auth_token")) or "__pycache__" in n]
    assert not leaked, leaked
    assert "minideck_launcher.py" in names
    assert "minideck_app/frontend/index.html" in names
    assert "minideck_app/server/main.py" in names
    assert any(n.endswith("deck.default.windows.json") for n in names)
