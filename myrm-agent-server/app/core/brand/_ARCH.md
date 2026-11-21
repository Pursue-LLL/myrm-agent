# brand/

## Overview
The brand values server code puts on the wire, defined once: the official site root, the system sender address and the application identity announced to model gateways.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports `CLIENT_ATTRIBUTION`, `NOREPLY_EMAIL`, `OFFICIAL_SITE_URL`. | — |
| identity.py | Core | `OFFICIAL_SITE_URL` and `NOREPLY_EMAIL`, and `CLIENT_ATTRIBUTION` (site URL, app name, OpenRouter categories, Vercel User-Agent) built on the harness `ClientAttribution`. `app.server.lifespan.startup` registers it with the model factory; the Vercel header writers of `core/wire`, `core/channel_bridge/model_resolver` and `api/integrations/llms` read it directly. | ✅ |

## POS
The harness carries no brand, so every brand URL, address and header value the server sends comes from here. The whole-tree gate `tests/architecture/test_brand_domain_gate.py` keeps retired brand domains out of the repository.
