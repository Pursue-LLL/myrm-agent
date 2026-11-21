"""The one definition of where each kind of share token is served.

[OUTPUT]
- ShareKind: the share token kinds that have a public page (artifact, chat)
- share_link_path: the relative public path of a share token
- share_link_url: the absolute link, a public base plus that path

[POS]
Server business layer. Every link handed to a recipient (share dialogs, the share list, IM buttons) is built here, so
a route prefix cannot drift away from the links that point at it. ``tests/architecture/test_public_share_admission.py``
checks each shape against the live route table and the auth admission rule.
"""

from __future__ import annotations

from enum import StrEnum

_PUBLIC_API_PREFIX = "/api/v1/public"


class ShareKind(StrEnum):
    """A share token kind; the value is the path segment its public routes are mounted under."""

    ARTIFACT = "artifact-share"
    CHAT = "chat-share"


def share_link_path(kind: ShareKind, token: str) -> str:
    """The relative public path that serves ``token``."""
    return f"{_PUBLIC_API_PREFIX}/{kind}/{token}"


def share_link_url(kind: ShareKind, token: str, base: str) -> str:
    """The absolute link to ``token`` under ``base`` (a public base without a trailing slash)."""
    return f"{base}{share_link_path(kind, token)}"
