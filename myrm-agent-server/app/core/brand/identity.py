"""Product identity: the official site, the sender address and the app identity announced to model gateways.

[INPUT]
- myrm_agent_harness.api.hooks::ClientAttribution (POS: the identity a host registers with the model factory)

[OUTPUT]
- OFFICIAL_SITE_URL: root of the official website, without a trailing slash
- NOREPLY_EMAIL: sender address for push claims and the IMAP client ID
- CLIENT_ATTRIBUTION: the identity OpenRouter and Vercel AI Gateway rank and meter this product by

[POS]
Single source of the brand values server code puts on the wire. The harness holds no brand of its own, so it learns
``CLIENT_ATTRIBUTION`` from ``app.server.lifespan.startup``. The categories are part of the identity: OpenRouter merges
them into the app's page, so they are settled here once rather than per call site.
"""

from __future__ import annotations

from myrm_agent_harness.api.hooks import ClientAttribution

OFFICIAL_SITE_URL = "https://myrmagent.ai"
NOREPLY_EMAIL = "noreply@myrmagent.ai"

CLIENT_ATTRIBUTION = ClientAttribution(
    site_url=OFFICIAL_SITE_URL,
    app_name="Myrm Agent",
    openrouter_categories=("personal-agent", "general-chat"),
    vercel_user_agent="Myrm/1.0 (Vercel-AI-Gateway-Client)",
)
