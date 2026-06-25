"""Skill-gated X/Twitter search tool — reads xAI credentials from session context.

[INPUT]
- user_credentials_ctx (issuer=xai, token=api_key, scope=base_url)
- app.ai_agents.general_agent.tools.x_search_provider::XSearchProvider

[OUTPUT]
- create_x_live_search_tool: deferred LangChain tool factory

[POS]
Server integration tool for x-live-search prebuilt skill. Credentials are injected by
session_credential_assembler into user_credentials_ctx, not baked into tool construction.
"""

from __future__ import annotations

from typing import Any

from langchain.tools import tool
from langchain_core.tools import BaseTool

from app.ai_agents.general_agent.tools.x_search_provider import (
    XSearchInput,
    XSearchProvider,
    XSearchProviderConfig,
    _X_SEARCH_DESCRIPTION,
)
from app.services.agent.session_credential_assembler import XAI_ISSUER

_DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"


def _resolve_xai_config_from_ctx() -> XSearchProviderConfig | None:
    from myrm_agent_harness.agent.security import user_credentials_ctx

    for cred in user_credentials_ctx.get():
        if cred.issuer != XAI_ISSUER or not cred.token.strip():
            continue
        base_url = cred.scope.strip() if cred.scope else _DEFAULT_XAI_BASE_URL
        return XSearchProviderConfig(api_key=cred.token, base_url=base_url)
    return None


def create_x_live_search_tool() -> BaseTool:
    """Create deferred x_search_tool that resolves xAI credentials at execution time."""

    @tool("x_search_tool", description=_X_SEARCH_DESCRIPTION, args_schema=XSearchInput)
    async def x_search_func(
        query: str,
        allowed_handles: list[str] | None = None,
        excluded_handles: list[str] | None = None,
        from_date: str = "",
        to_date: str = "",
    ) -> dict[str, Any]:
        config = _resolve_xai_config_from_ctx()
        if config is None:
            return {
                "content": (
                    "xAI API key not configured. Add an xAI provider in Settings → Models & Providers, "
                    "then enable the x-live-search skill on this agent."
                ),
                "metadata": {"error": True, "query": query},
            }

        provider = XSearchProvider(config)
        result = await provider.search(
            query=query,
            allowed_handles=allowed_handles,
            excluded_handles=excluded_handles,
            from_date=from_date,
            to_date=to_date,
        )

        if result.is_error:
            return {
                "content": result.snippet,
                "metadata": {"error": True, "query": query},
            }

        citations_text = ""
        if result.citations:
            citations_text = "\n\nSources:\n" + "\n".join(
                f"- [{c.title or c.url}]({c.url})" for c in result.citations
            )

        return {
            "content": result.snippet + citations_text,
            "metadata": {
                "query": query,
                "source": "x_search",
                "citations": [{"url": c.url, "title": c.title} for c in result.citations],
                "total_citations": len(result.citations),
            },
        }

    return x_search_func
