"""Unit tests for translation_service (DeepL API, mocked via respx)."""

from __future__ import annotations

import httpx
import respx

from app.config import Settings
from app.services import translation_service
from app.services.translation_service import SUPPORTED_LANGS, translate_fields


def _settings(**overrides) -> Settings:
    defaults = {
        "require_secrets": False,
        "deepl_api_key": "test-deepl-key",
        "deepl_base_url": "https://api.deepl.example",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[call-arg]


def _patch_settings(monkeypatch, settings: Settings) -> None:
    monkeypatch.setattr(translation_service, "get_settings", lambda: settings)


def _deepl_response(texts: list[str]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"translations": [{"text": f"T:{t}"} for t in texts]},
    )


async def test_translate_fields_batches_one_request_per_language(monkeypatch):
    _patch_settings(monkeypatch, _settings())
    with respx.mock:
        route = respx.post("https://api.deepl.example/v2/translate").mock(
            return_value=_deepl_response(["Sun", "A star."]),
        )
        result = await translate_fields({"title": "Sun", "explanation": "A star."})

    assert route.call_count == len(SUPPORTED_LANGS)
    for lang in SUPPORTED_LANGS:
        assert result[lang] == {"title": "T:Sun", "explanation": "T:A star."}
    # Each request carries both texts (batched), not one call per field.
    last_request = route.calls.last.request
    body = last_request.read().decode()
    assert body.count("text=") == 2


async def test_translate_fields_empty_values_passed_through(monkeypatch):
    _patch_settings(monkeypatch, _settings())
    with respx.mock:
        respx.post("https://api.deepl.example/v2/translate").mock(
            return_value=_deepl_response(["Text"]),
        )
        result = await translate_fields({"title": "", "explanation": "Text"})

    for lang in SUPPORTED_LANGS:
        assert result[lang]["title"] == ""
        assert result[lang]["explanation"] == "T:Text"


async def test_translate_fields_per_language_failure_falls_back(monkeypatch):
    _patch_settings(monkeypatch, _settings())
    with respx.mock:
        route = respx.post("https://api.deepl.example/v2/translate")
        route.side_effect = [
            httpx.Response(500, json={"message": "server error"}),
            *[_deepl_response(["Sun"]) for _ in range(len(SUPPORTED_LANGS) - 1)],
        ]
        result = await translate_fields({"title": "Sun"})

    failed_lang = SUPPORTED_LANGS[0]
    assert result[failed_lang]["title"] == "Sun"  # fell back to English
    for lang in SUPPORTED_LANGS[1:]:
        assert result[lang]["title"] == "T:Sun"  # other languages still succeeded


async def test_translate_fields_missing_key_short_circuits(monkeypatch):
    _patch_settings(monkeypatch, _settings(deepl_api_key=""))
    with respx.mock:
        route = respx.post("https://api.deepl.example/v2/translate").mock(
            return_value=_deepl_response(["Sun"]),
        )
        result = await translate_fields({"title": "Sun"})

    assert route.call_count == 0
    for lang in SUPPORTED_LANGS:
        assert result[lang]["title"] == "Sun"


async def test_translate_fields_quota_exceeded_falls_back(monkeypatch):
    _patch_settings(monkeypatch, _settings())
    with respx.mock:
        respx.post("https://api.deepl.example/v2/translate").mock(
            return_value=httpx.Response(456, json={"message": "Quota exceeded"}),
        )
        result = await translate_fields({"title": "Sun"})

    for lang in SUPPORTED_LANGS:
        assert result[lang]["title"] == "Sun"


async def test_translate_fields_empty_input_skips_http_call(monkeypatch):
    _patch_settings(monkeypatch, _settings())
    with respx.mock:
        route = respx.post("https://api.deepl.example/v2/translate").mock(
            return_value=_deepl_response([]),
        )
        result = await translate_fields({})

    assert route.call_count == 0
    assert set(result.keys()) == set(SUPPORTED_LANGS)
    assert all(result[lang] == {} for lang in SUPPORTED_LANGS)


async def test_translate_fields_falsy_translation_falls_back(monkeypatch):
    _patch_settings(monkeypatch, _settings())
    with respx.mock:
        respx.post("https://api.deepl.example/v2/translate").mock(
            return_value=httpx.Response(200, json={"translations": [{"text": ""}]}),
        )
        result = await translate_fields({"title": "Sun"})

    for lang in SUPPORTED_LANGS:
        assert result[lang]["title"] == "Sun"
