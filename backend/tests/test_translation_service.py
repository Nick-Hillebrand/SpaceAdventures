"""Unit tests for translation_service (GoogleTranslator mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.translation_service import SUPPORTED_LANGS, translate_fields


def _mock_translator_factory(side_effect=None, translate=None):
    """Return a GoogleTranslator class mock whose instances translate via *translate*."""
    factory = MagicMock()
    instance = MagicMock()
    if side_effect is not None:
        instance.translate.side_effect = side_effect
    else:
        instance.translate.side_effect = translate
    factory.return_value = instance
    return factory


async def test_translate_fields_success():
    factory = _mock_translator_factory(translate=lambda text: f"T:{text}")
    with patch("deep_translator.GoogleTranslator", factory):
        result = await translate_fields({"title": "Sun", "explanation": "A star."})

    assert set(result.keys()) == set(SUPPORTED_LANGS)
    for lang in SUPPORTED_LANGS:
        assert result[lang] == {"title": "T:Sun", "explanation": "T:A star."}


async def test_translate_fields_empty_values_passed_through():
    factory = _mock_translator_factory(translate=lambda text: f"T:{text}")
    with patch("deep_translator.GoogleTranslator", factory):
        result = await translate_fields({"title": "", "explanation": "Text"})

    for lang in SUPPORTED_LANGS:
        assert result[lang]["title"] == ""
        assert result[lang]["explanation"] == "T:Text"
    # Empty values never hit the translator
    assert factory.return_value.translate.call_count == len(SUPPORTED_LANGS)


async def test_translate_fields_error_falls_back_to_english():
    factory = _mock_translator_factory(side_effect=RuntimeError("quota"))
    with patch("deep_translator.GoogleTranslator", factory):
        result = await translate_fields({"title": "Sun"})

    for lang in SUPPORTED_LANGS:
        assert result[lang]["title"] == "Sun"


async def test_translate_fields_falsy_translation_falls_back():
    factory = _mock_translator_factory(translate=lambda text: "")
    with patch("deep_translator.GoogleTranslator", factory):
        result = await translate_fields({"title": "Sun"})

    for lang in SUPPORTED_LANGS:
        assert result[lang]["title"] == "Sun"


async def test_translate_fields_empty_input():
    factory = _mock_translator_factory(translate=lambda text: f"T:{text}")
    with patch("deep_translator.GoogleTranslator", factory):
        result = await translate_fields({})

    assert set(result.keys()) == set(SUPPORTED_LANGS)
    assert all(result[lang] == {} for lang in SUPPORTED_LANGS)
    factory.return_value.translate.assert_not_called()
