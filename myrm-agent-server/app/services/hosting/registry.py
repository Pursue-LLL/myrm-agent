"""Hosting provider registry.

[POS] Map provider type strings to concrete HostingProvider implementations.

[INPUT]
- app.services.hosting.providers.* (POS: platform-specific providers)

[OUTPUT]
- get_hosting_provider: resolve provider instance by ProviderType
"""

from __future__ import annotations

from app.services.hosting.protocols import HostingProvider
from app.services.hosting.providers.cloudflare_pages import CloudflarePagesProvider
from app.services.hosting.providers.http_webhook import HttpWebhookProvider
from app.services.hosting.providers.netlify import NetlifyHostingProvider
from app.services.hosting.providers.vercel import VercelHostingProvider

_PROVIDERS: dict[str, HostingProvider] = {
    "vercel": VercelHostingProvider(),
    "cloudflare_pages": CloudflarePagesProvider(),
    "netlify": NetlifyHostingProvider(),
    "http_webhook": HttpWebhookProvider(),
}


def get_hosting_provider(provider_type: str) -> HostingProvider:
    provider = _PROVIDERS.get(provider_type)
    if provider is None:
        raise ValueError(f"Unsupported hosting provider: {provider_type}")
    return provider
