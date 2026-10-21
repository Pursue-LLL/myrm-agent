"""OpenAI-compatible API router.

[INPUT]
- app.api.openai_compat.completions::router (POS: /v1/chat/completions)
- app.api.openai_compat.models::router (POS: /v1/models)

[OUTPUT]
- openai_compat_router: Combined router mounted at /v1

[POS]
Aggregates all OpenAI-compatible sub-routers under the /v1 prefix.
"""

from fastapi import APIRouter

from app.api.openai_compat.completions import router as completions_router
from app.api.openai_compat.models import router as models_router

openai_compat_router = APIRouter(prefix="/v1", tags=["openai-compat"])

openai_compat_router.include_router(completions_router)
openai_compat_router.include_router(models_router)
