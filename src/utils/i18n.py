from pathlib import Path
from html import escape
from typing import Any

import yaml

_translations: dict[str, dict] = {}
_display: dict[str, str] = {}
_default_lang: str = "en"

_TRANSLATIONS_DIR = Path(__file__).parent.parent / "translations"


def _load_all():
    for file in _TRANSLATIONS_DIR.glob("*.yaml"):
        with open(file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _translations[file.stem] = data.get("strings", {})
        _display[file.stem] = data.get("display", file.stem)


def _get_nested(data: dict, keys: list[str]) -> Any:
    node = data
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def get(key: str, lang: str | None = None, html_escape: bool = True) -> str:
    if not _translations:
        _load_all()

    def esc(txt):
        return escape(str(txt)) if html_escape else str(txt)

    lang = lang or _default_lang
    parts = key.split(".")

    if lang in _translations:
        value = _get_nested(_translations[lang], parts)
        if value is not None:
            return esc(str(value))

    if lang != _default_lang and _default_lang in _translations:
        value = _get_nested(_translations[_default_lang], parts)
        if value is not None:
            return esc(str(value))

    return key


def available_languages() -> list[str]:
    if not _translations:
        _load_all()
    return list(_translations.keys())


def display_name(lang: str) -> str:
    if not _translations:
        _load_all()
    return _display.get(lang, lang)


def set_default(lang: str):
    global _default_lang
    _default_lang = lang