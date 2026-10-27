"""Read-scope guards for file_read_tool: the Fast-track path policy and the disabled-skill block.

[INPUT]
- agent.context_guard::KEPT_SPILLOVER_DIR, TRANSIENT_SPILLOVER_DIR (POS: spilled long-text directories, the constants the writer uses)
- agent.context_management.infra.evicted.content::normalize_delivery_chat_id (POS: UECD chat id normalization, symmetric with the writer)
- agent.meta_tools.file_search.skill_path_filter::get_disabled_skill_roots, is_under_disabled_skill_root (POS: disabled skill path blocking)
- core.context_vars::chat_id_var, workspace_root_var (POS: run-scoped chat id and workspace root)
- core.security.tool_registry::is_url (POS: the one definition of a network URL)
- utils.vault_read::is_vault_uri, path_base (POS: vault:// URI test and ``:range`` suffix stripping)
- utils.errors::ToolError (POS: tool error type)

[OUTPUT]
- partition_urls: splits a call into its local paths and the refusal naming the URLs the tool will not read
- normalize_path_hint / path_hint_allowed_for_evicted_uploaded: lexical check of a path against the Fast-track scope
- assert_evicted_uploaded_read_scope: restricts a Fast-track read to UECD spill, chat uploads and spilled long pastes
- assert_paths_allowed_for_read: blocks a path under a disabled skill

[POS]
Admission checks the tool facade runs before file_read_tool opens anything; the read handlers never call them.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.context_guard import KEPT_SPILLOVER_DIR, TRANSIENT_SPILLOVER_DIR
from myrm_agent_harness.agent.context_management.infra.evicted.content import (
    normalize_delivery_chat_id,
)
from myrm_agent_harness.agent.meta_tools.file_search.skill_path_filter import (
    get_disabled_skill_roots,
    is_under_disabled_skill_root,
)
from myrm_agent_harness.core.context_vars import chat_id_var, workspace_root_var
from myrm_agent_harness.core.security.tool_registry import is_url
from myrm_agent_harness.utils.errors import ToolError

from ...utils.vault_read import is_vault_uri, path_base

_URLS_NAMED = 3


def partition_urls(paths: list[str]) -> tuple[list[str], str]:
    """The local paths of a call, and the refusal that names its URLs (empty when it has none)."""
    local = [path for path in paths if not is_url(path)]
    urls = [path for path in paths if is_url(path)]
    if not urls:
        return local, ""
    named = ", ".join(urls[:_URLS_NAMED])
    more = f" (and {len(urls) - _URLS_NAMED} more)" if len(urls) > _URLS_NAMED else ""
    return (
        local,
        f"file_read_tool cannot read URLs: {named}{more}. This tool only supports local file paths, not web URLs.",
    )


def normalize_path_hint(raw_path: str) -> str:
    normalized = raw_path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _evicted_uploaded_scopes(chat_id: str) -> tuple[str, ...]:
    """Workspace-relative directories the Fast track may read: UECD spill, chat uploads, spilled long pastes."""
    return (f".context/{chat_id}/evicted", "_uploaded", KEPT_SPILLOVER_DIR, TRANSIENT_SPILLOVER_DIR)


def path_hint_allowed_for_evicted_uploaded(raw_path: str, chat_id: str) -> bool:
    normalized = normalize_path_hint(raw_path)
    # A ``..`` segment can leave a scope after its prefix matched: such a path is judged by where it resolves.
    if ".." in normalized.split("/"):
        return False
    return any(normalized == scope or normalized.startswith(f"{scope}/") for scope in _evicted_uploaded_scopes(chat_id))


async def assert_evicted_uploaded_read_scope(
    paths: list[str],
    *,
    chat_id: str,
    executor: object | None,
) -> None:
    """Restrict reads to UECD spill files, spilled long pastes and chat uploads (Fast / search track)."""
    # Persist side normalizes chat_<id> session keys to <id> (infra/evicted/content.py);
    # mirror it here so saved paths match the read scope check.
    session_chat_id = normalize_delivery_chat_id(chat_id.strip() or chat_id_var.get().strip())
    if not session_chat_id:
        raise ToolError(
            message="file_read_tool blocked: missing chat_id for evicted-read scope",
            user_hint="Cannot read evicted output without an active chat session.",
        )
    workspace_root = workspace_root_var.get().strip()
    resolve_path = getattr(executor, "resolve_path", None) if executor else None
    scopes = _evicted_uploaded_scopes(session_chat_id)
    hint = f"Fast search mode only allows reading spill, pasted-text and upload files under: {', '.join(scopes)}."
    for raw in paths:
        if is_vault_uri(raw):
            continue
        if path_hint_allowed_for_evicted_uploaded(raw, session_chat_id):
            continue
        if not workspace_root or resolve_path is None:
            raise ToolError(
                message=f"file_read_tool blocked: {raw}",
                user_hint=hint,
            )
        base = path_base(raw)
        try:
            resolved = await resolve_path(base)
        except ValueError:
            resolved = base
        resolved_path = Path(str(resolved)).resolve()
        allowed_roots = [(Path(workspace_root) / scope).resolve() for scope in scopes]
        if not any(resolved_path == root or root in resolved_path.parents for root in allowed_roots):
            raise ToolError(
                message=f"file_read_tool blocked: {raw}",
                user_hint=f"{hint} Switch to Agent mode for full workspace file access.",
            )


async def assert_paths_allowed_for_read(
    paths: list[str],
    config: RunnableConfig,
    executor: object | None,
) -> None:
    disabled_roots = get_disabled_skill_roots(config)
    if not disabled_roots or executor is None:
        return
    resolve_path = getattr(executor, "resolve_path", None)
    if resolve_path is None:
        return
    for raw in paths:
        if is_vault_uri(raw) or is_url(raw):
            continue
        base = path_base(raw)
        try:
            resolved = await resolve_path(base)
        except ValueError:
            resolved = base
        if is_under_disabled_skill_root(str(resolved), disabled_roots):
            raise ToolError(
                message=f"Path blocked: {raw}",
                user_hint="This path belongs to a disabled skill and cannot be read.",
            )
