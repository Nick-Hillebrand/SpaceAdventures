"""Unit tests for the upstream-URL sanitiser."""

from __future__ import annotations

import pytest

from app.services.url_utils import sanitise_url


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/img.jpg",
        "http://example.com/path?q=1&r=2",
        "  https://example.com/padded  ",
    ],
)
def test_accepts_http_and_https(value):
    assert sanitise_url(value) == value.strip()


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
        "ftp://example.com/file",
        "//example.com/protocol-relative",
        "/relative/path.jpg",
        "example.com/no-scheme",
        "https://",  # no host
        "",
        "   ",
    ],
)
def test_rejects_non_http_or_malformed(value):
    assert sanitise_url(value) is None


@pytest.mark.parametrize("value", [None, 42, {"url": "https://x"}, ["https://x"]])
def test_rejects_non_strings(value):
    assert sanitise_url(value) is None


def test_rejects_overlong_urls():
    url = "https://example.com/" + "a" * 3000
    assert sanitise_url(url) is None
    assert sanitise_url(url, max_len=5000) == url


def test_rejects_unparseable_url():
    # urlparse raises ValueError on invalid IPv6 literals
    assert sanitise_url("https://[invalid/path") is None


def test_case_insensitive_scheme_smuggling_rejected():
    assert sanitise_url("JaVaScRiPt:alert(1)") is None
