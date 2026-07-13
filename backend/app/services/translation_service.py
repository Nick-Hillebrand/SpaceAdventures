"""Translation service using the DeepL API (P1.7 — replaces deep-translator).

Usage:
    from app.services.translation_service import translate_fields

    translations = await translate_fields({"title": "Sun", "explanation": "A star."})
    # → {"de": {"title": "Sonne", "explanation": "Ein Stern."}, "fr": {...}, ...}

Public interface is unchanged from the deep-translator implementation: callers
(`main.py` wiring, `launches_service.sync_launches`, etc.) are untouched.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

SUPPORTED_LANGS: tuple[str, ...] = ("de", "fr", "es", "ja", "ru")

_DEEPL_TARGET_LANG: dict[str, str] = {
    "de": "DE",
    "fr": "FR",
    "es": "ES",
    "ja": "JA",
    "ru": "RU",
}

# P6 (11-testing.md): one shared httpx.AsyncClient, created once — not per
# request/call. translate_fields()'s signature can't take a client param (its
# callers are untouched), so the client is a lazily-created module singleton
# instead of living on app.state like the other upstream clients.
_client: httpx.AsyncClient | None = None


async def _get_client(settings: Settings) -> httpx.AsyncClient:
    global _client
    if _client is None or str(_client.base_url) != settings.deepl_base_url.rstrip("/") + "/":
        if _client is not None:
            await _client.aclose()
        _client = httpx.AsyncClient(
            base_url=settings.deepl_base_url,
            timeout=settings.http_timeout_seconds,
            follow_redirects=False,
        )
    return _client


async def translate_fields(fields: dict[str, str]) -> dict[str, dict[str, str]]:
    """Translate a dict of {field_name: english_text} into all supported languages.

    Returns {lang_code: {field_name: translated_text}}.
    Empty/None values are passed through unchanged.
    Missing API key, per-language failures, and quota errors all fall back
    silently to the original English text — callers never see an exception.
    """
    settings = get_settings()

    field_names = list(fields.keys())
    texts = [fields[name] for name in field_names]
    non_empty = [i for i, text in enumerate(texts) if text]

    if not settings.deepl_api_key:
        logger.warning("DeepL API key not configured; falling back to English text")
        return {lang: dict(fields) for lang in SUPPORTED_LANGS}

    results: dict[str, dict[str, str]] = {}
    client = await _get_client(settings) if non_empty else None

    for lang in SUPPORTED_LANGS:
        lang_result = dict(fields)
        if non_empty:
            try:
                # httpx's `data=` form encoder does not support repeated keys
                # for a list of tuples on an AsyncClient (raises internally) —
                # build the urlencoded body ourselves instead.
                body = urlencode(
                    [
                        ("target_lang", _DEEPL_TARGET_LANG[lang]),
                        *[("text", texts[i]) for i in non_empty],
                    ]
                )
                response = await client.post(
                    "/v2/translate",
                    headers={
                        "Authorization": f"DeepL-Auth-Key {settings.deepl_api_key}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    content=body,
                )
                response.raise_for_status()
                translations = response.json()["translations"]
                for pos, idx in enumerate(non_empty):
                    translated = translations[pos].get("text")
                    lang_result[field_names[idx]] = translated if translated else texts[idx]
            except Exception as exc:  # noqa: BLE001 — any failure falls back to English
                logger.warning("Translation to %s failed: %s", lang, exc)
        results[lang] = lang_result

    return results
