"""API Key management endpoints.

Provides CRUD operations for managing OpenAI-compatible API keys
used by the /v1/* endpoints.
"""

from app.api.api_keys.router import router

__all__ = ["router"]
