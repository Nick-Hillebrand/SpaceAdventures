"""Translation service using deep-translator (Google Translate, no API key required).

Usage:
    from app.services.translation_service import translate_fields

    translations = await translate_fields({"title": "Sun", "explanation": "A star."})
    # → {"de": {"title": "Sonne", "explanation": "Ein Stern."}, "fr": {...}, ...}
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

SUPPORTED_LANGS: tuple[str, ...] = ("de", "fr", "es", "ja", "ru")


async def translate_fields(fields: dict[str, str]) -> dict[str, dict[str, str]]:
    """Translate a dict of {field_name: english_text} into all supported languages.

    Returns {lang_code: {field_name: translated_text}}.
    Empty/None values are passed through unchanged.
    Per-field failures fall back silently to the original English text.
    """
    from deep_translator import GoogleTranslator  # noqa: PLC0415 — deferred to avoid import cost

    results: dict[str, dict[str, str]] = {}
    for lang in SUPPORTED_LANGS:
        lang_result: dict[str, str] = {}
        for field, text in fields.items():
            if not text:
                lang_result[field] = text
                continue
            try:
                translator = GoogleTranslator(source="en", target=lang)
                translated: str = await asyncio.to_thread(translator.translate, text)
                lang_result[field] = translated if translated else text
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Translation to %s for field '%s' failed: %s", lang, field, exc
                )
                lang_result[field] = text
        results[lang] = lang_result
    return results
