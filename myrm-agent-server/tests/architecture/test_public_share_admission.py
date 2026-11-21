"""Every link the server hands out for a share is opened without credentials, in every method its page serves.

[POS]
tests/architecture/test_public_share_admission.py

[INPUT]
- app.core.security.share.share_links::ShareKind, share_link_path (POS: where each share token kind is served)
- app.core.security.auth.public_paths::is_public_path (POS: the admission rule the middlewares apply)
- tests.support.public_api_app: full OpenAPI path + method table

[OUTPUT]
- Fails when the link a share kind hands out is served by no GET route
- Fails when that link is not admitted without credentials: the recipient has none
- Fails when any operation under a share kind is not admitted: the password form posts back to the page it unlocks

A link that is correct but refused by the auth middleware reads as a dead link to its recipient and is invisible to
every test that mounts a single router, so the rule is checked against the assembled API.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.core.security.auth.public_paths import is_public_path
from app.core.security.share.share_links import ShareKind, share_link_path
from tests.support.public_api_app import API_VERBS, public_api_openapi

_SAMPLE_TOKEN = "sample-token"


def _accepts(template: str, concrete: str) -> bool:
    """Whether a route template (``/a/{token}``) serves a concrete path, segment by segment."""
    template_parts = template.split("/")
    concrete_parts = concrete.split("/")
    return len(template_parts) == len(concrete_parts) and all(
        t == c or (t.startswith("{") and t.endswith("}")) for t, c in zip(template_parts, concrete_parts, strict=True)
    )


def _operations(matches: Callable[[str], bool]) -> list[tuple[str, str]]:
    """``(METHOD, route template)`` of every API operation whose route template satisfies ``matches``."""
    return [
        (verb.upper(), template)
        for template, operations in public_api_openapi().paths.items()
        if matches(template)
        for verb in operations
        if verb.upper() in API_VERBS
    ]


@pytest.mark.parametrize("kind", list(ShareKind))
def test_share_link_is_served_by_a_get_route(kind: ShareKind) -> None:
    link = share_link_path(kind, _SAMPLE_TOKEN)
    serving = _operations(lambda template: _accepts(template, link))
    assert any(method == "GET" for method, _ in serving), f"{link} is handed out as a link but no GET route serves it"


@pytest.mark.parametrize("kind", list(ShareKind))
def test_share_link_is_admitted_without_credentials(kind: ShareKind) -> None:
    link = share_link_path(kind, _SAMPLE_TOKEN)
    assert is_public_path(link, "GET"), (
        f"{link} is handed out as a link but the auth middleware asks its recipient for credentials; "
        "add the share kind's path to PUBLIC_PATH_PREFIXES in app/core/security/auth/public_paths.py"
    )


@pytest.mark.parametrize("kind", list(ShareKind))
def test_every_operation_under_a_share_kind_is_admitted(kind: ShareKind) -> None:
    family = share_link_path(kind, "")
    refused = [
        f"{method} {template}"
        for method, template in _operations(lambda template: template.startswith(family))
        if not is_public_path(template, method)
    ]
    assert not refused, f"Operations of the {kind.value} page that the auth middleware would refuse: {refused}"
