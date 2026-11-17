# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_dynamic_widgets_use_translation_keys_for_their_ui_copy():
    app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    for spanish_literal in (
        'toast("Sin conexión"', 'toast("Buscando letra…"', '"Sin título"',
        '"Conectando…"', 'title="Silenciar micro"', 'placeholder="Mensaje al canal…"',
        'title="Enviar"', '"RPC desconectado"', '"Sin canal de voz"',
        '"Sin audio activo"', '"Perfil por app: activado"',
    ):
        assert spanish_literal not in app


def test_every_new_runtime_translation_has_an_english_value():
    strings = (ROOT / "frontend" / "i18n.js").read_text(encoding="utf-8")

    for value in (
        '"toast.searchingLyrics": "Finding lyrics…"',
        '"discord.connecting": "Connecting…"',
        '"mixer.noAudio": "No active audio"',
        '"profile.enabled": "App-based profile: on"',
        '"pwa.installPrompt": "Install MiniDeck as an app (full screen)."',
    ):
        assert value in strings


def test_built_in_deck_labels_are_displayed_in_english_without_mutating_config():
    strings = (ROOT / "frontend" / "i18n.js").read_text(encoding="utf-8")
    app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    assert '"Principal": "Home"' in strings
    assert '"Silenciar": "Mute"' in strings
    assert 'const deckText = (text) => window.MiniDeckI18n.deckText(text);' in app
    assert 'tab.textContent = deckText(page.name);' in app
    assert 'label.textContent = deckText(btn.label ?? "");' in app
