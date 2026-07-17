"""Build an ``OversizedResultHandler`` that persists large MCP outputs into ArtifactVault.

The handler is injected into MCP server configs at agent-build time so the
harness ``_timeout_wrapper`` can call it instead of silently truncating data.

[INPUT]
- myrm_agent_harness.agent.artifacts.vault::ArtifactVault (POS: Shared Artifact Vault)
- myrm_agent_harness.agent.artifacts::infer_artifact_type_from_extension, push_inline_artifact (POS: Inline artifact SSE queue for frontend delivery)

[OUTPUT]
- build_mcp_vault_handler: factory that returns an OversizedResultHandler closure

[POS]
Server-layer bridge between MCP oversized-output callback (harness) and ArtifactVault (harness).
Keeps the harness toolkits layer free of agent.artifacts imports (architecture boundary).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

_SUMMARY_HEAD_CHARS = 2_000
_SUMMARY_TAIL_CHARS = 1_000


def build_mcp_vault_handler(workspace_root: str) -> Callable[[str, str], str | None]:
    """Return a closure that vaults oversized MCP tool output.

    The returned callable has signature ``(content, tool_name) -> str | None``.
    It stores the full content in ``ArtifactVault`` and returns a compact
    summary with a ``vault://`` pointer.  Returns ``None`` on any failure so
    the harness falls back to head-truncation.
    """

    def _handler(content: str, tool_name: str) -> str | None:
        from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

        try:
            vault = ArtifactVault(workspace_root)
            filename = f"mcp_{tool_name.replace(':', '_')}_result.txt"
            pointer = vault.put(
                content,
                filename,
                "text/plain",
                f"MCP tool '{tool_name}' output ({len(content):,} chars)",
            )
        except Exception:
            logger.warning("Vault write failed for MCP tool '%s'", tool_name, exc_info=True)
            return None

        try:
            from myrm_agent_harness.agent.artifacts import (
                infer_artifact_type_from_extension,
                push_inline_artifact,
            )

            push_inline_artifact(
                filename=filename,
                preview_url=pointer,
                artifact_type=infer_artifact_type_from_extension(filename),
                content_type="text/plain",
            )
        except Exception:
            logger.debug("Failed to push inline artifact for MCP vault pointer", exc_info=True)

        head = content[:_SUMMARY_HEAD_CHARS]
        tail_start = max(_SUMMARY_HEAD_CHARS, len(content) - _SUMMARY_TAIL_CHARS)
        tail = content[tail_start:]
        omitted = tail_start - _SUMMARY_HEAD_CHARS

        if omitted > 0:
            summary = f"{head}\n\n... ({omitted:,} chars omitted) ...\n\n{tail}"
        else:
            summary = head

        return (
            f"{summary}\n\n[Full result stored in vault: {pointer}]\n"
            f'To read full content: file_read_tool(paths=["{pointer}"])'
        )

    return _handler
