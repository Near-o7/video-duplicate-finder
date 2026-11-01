"""Application translations. English strings are the source of truth."""
from pathlib import Path
import json

_language = "en"
_spanish = json.loads((Path(__file__).parent / "locales" / "es.json").read_text(encoding="utf-8")) if (Path(__file__).parent / "locales" / "es.json").exists() else {}


def set_language(language):
    global _language
    if language == "system":
        from PySide6.QtCore import QLocale
        language = "es" if QLocale.system().name().startswith("es") else "en"
    _language = language if language in ("es", "en") else "en"
    return _language


def language():
    return _language


def tr(message, **values):
    translated = _spanish.get(message, message) if _language == "es" else message
    return translated.format(**values) if values else translated
