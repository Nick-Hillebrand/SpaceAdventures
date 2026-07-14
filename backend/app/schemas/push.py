"""Pydantic schemas for Web Push endpoints (19-notification-channels-v2.md B1.2)."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from pydantic import BaseModel, field_validator


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


def _validate_push_endpoint(endpoint: str) -> str:
    """The browser controls `endpoint` at subscribe time, but this value is
    later replayed server-side (the worker POSTs to it via pywebpush) — an
    attacker can bypass the browser entirely and hand us any URL directly, so
    it's treated as untrusted (25-security-testing.md §2.5 threat model:
    "a malicious registered user"). Reject non-https schemes and literal
    private/loopback/link-local/reserved IP hosts to block the common SSRF
    targets (cloud metadata endpoints, internal services by IP). This does
    not resolve hostnames, so it is not a defense against DNS rebinding —
    that would require pinning the resolved IP at request time in the
    worker, out of scope for this pass.
    """
    parts = urlsplit(endpoint)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("endpoint must be an https:// URL")
    try:
        ip = ipaddress.ip_address(parts.hostname)
    except ValueError:
        return endpoint  # not an IP literal — hostname, allowed
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        raise ValueError("endpoint must not point to a private or reserved address")
    return endpoint


class PushSubscribeRequest(BaseModel):
    """Shape matches the browser's `PushSubscription.toJSON()` output."""

    endpoint: str
    keys: PushSubscriptionKeys

    @field_validator("endpoint")
    @classmethod
    def _endpoint_is_safe(cls, v: str) -> str:
        return _validate_push_endpoint(v)


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


class VapidPublicKeyOut(BaseModel):
    public_key: str
