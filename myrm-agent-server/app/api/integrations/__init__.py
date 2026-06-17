"""External integrations API module

Provides validation endpoints for external services:
- LLM providers
- Search services
- MCP servers
- A2A agents (Agent-to-Agent discovery and management)
- Retrieval services (embedding, reranker)
"""

from app.api.integrations.router import router

__all__ = ["router"]
