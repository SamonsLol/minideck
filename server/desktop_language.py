# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Persistent language preference for MiniDeck's native desktop shell."""
from __future__ import annotations

import locale

from paths import DESKTOP_LANGUAGE_PATH

SUPPORTED_LANGUAGES = ("en", "es")


def system_language() -> str:
    """Return a supported language inferred from the host, defaulting to English."""
    language = (locale.getlocale()[0] or "").lower()
    return "es" if language.startswith("es") else "en"


def get_language() -> str:
    """Read the saved choice, or use the host language for a first launch."""
    try:
        language = DESKTOP_LANGUAGE_PATH.read_text(encoding="utf-8").strip().lower()
    except OSError:
        language = ""
    return language if language in SUPPORTED_LANGUAGES else system_language()


def set_language(language: str) -> str:
    """Persist a supported language and return it; reject invalid callers clearly."""
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported MiniDeck language: {language}")
    DESKTOP_LANGUAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = DESKTOP_LANGUAGE_PATH.with_suffix(".tmp")
    temp_path.write_text(language + "\n", encoding="utf-8")
    temp_path.replace(DESKTOP_LANGUAGE_PATH)
    return language
