"""Integration Catalog - Preconfigured service directory for one-click MCP/OpenAPI setup."""

from app.core.integrations.catalog.models import (
    AuthRequirements,
    CatalogEntry,
    ConnectorType,
)
from app.core.integrations.catalog.registry import CatalogRegistry

__all__ = [
    "AuthRequirements",
    "CatalogEntry",
    "CatalogRegistry",
    "ConnectorType",
]
