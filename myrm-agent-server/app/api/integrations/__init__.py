"""External integrations API module

Provides validation endpoints for external services:
- LLM providers
- Search services
- MCP servers
- Retrieval services (embedding, reranker)
"""

from app.api.integrations.router import router

__all__ = ["router"]
