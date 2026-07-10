"""Sanitisation for URLs received from upstream APIs.

Upstream data is untrusted input (CLAUDE.md rule 9). URLs are rendered by the
frontend into ``href``/``src``/``iframe src`` attributes, so a ``javascript:``
or ``data:`` scheme slipped into an upstream payload would execute as XSS.
Only absolute http(s) URLs are allowed through; anything else is dropped
before storage.
"""

from __future__ import annotations

from urllib.parse import urlparse

_ALLOWED_SCHEMES = ("http", "https")
_DEFAULT_MAX_LEN = 2000


def sanitise_url(value: object, max_len: int = _DEFAULT_MAX_LEN) -> str | None:
    """Return *value* if it is a well-formed absolute http(s) URL, else None."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > max_len:
        return None
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
        return None
    return value
