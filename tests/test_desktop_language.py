# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import desktop_language


def test_desktop_language_uses_system_default_without_saved_choice(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(desktop_language, "DESKTOP_LANGUAGE_PATH", tmp_path / "desktop_language")
    monkeypatch.setattr(desktop_language.locale, "getlocale", lambda: ("en_US", "UTF-8"))

    assert desktop_language.get_language() == "en"


def test_desktop_language_persists_explicit_choice(monkeypatch, tmp_path: Path):
    path = tmp_path / "settings" / "desktop_language"
    monkeypatch.setattr(desktop_language, "DESKTOP_LANGUAGE_PATH", path)

    assert desktop_language.set_language("es") == "es"
    assert path.read_text(encoding="utf-8") == "es\n"
    assert desktop_language.get_language() == "es"
