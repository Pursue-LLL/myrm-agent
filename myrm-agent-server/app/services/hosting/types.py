"""Hosting domain types for artifact publication flows.

[POS] Shared dataclasses and literals for multi-target artifact publishing.

[INPUT]
- dataclasses (POS: immutable value objects)

[OUTPUT]
- HostingTarget, PublicationResult, TargetCredentialStatus, ProviderType, is_provider_type
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeGuard, get_args

ProviderType = Literal["vercel", "http_webhook"]


def is_provider_type(value: str) -> TypeGuard[ProviderType]:
    """Whether *value* names a hosting provider this server can publish to."""
    return value in get_args(ProviderType)


@dataclass(frozen=True)
class PublicationResult:
    """Structured result from a publication attempt."""

    success: bool
    url: str
    publication_id: str
    project_ref: str
    status: str
    error: str | None = None
    latest_version_id: str | None = None
    publication_row_id: str | None = None


@dataclass
class HostingTarget:
    """User-configured hosting destination."""

    id: str
    name: str
    provider_type: ProviderType
    config: dict[str, str] = field(default_factory=dict)
    is_default: bool = False


@dataclass(frozen=True)
class TargetCredentialStatus:
    configured: bool
    platform_available: bool = False
