"""Search provider catalog SSOT."""

from app.core.integrations.search_catalog.models import SearchProviderManifestEntry
from app.core.integrations.search_catalog.registry import SearchProviderCatalogRegistry

__all__ = ["SearchProviderCatalogRegistry", "SearchProviderManifestEntry"]
