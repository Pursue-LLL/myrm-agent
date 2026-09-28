"""Integration tests for CapabilitySurface execution engine security gate.

Validates that capabilityMatrix configurations are correctly mapped, expanded,
and enforced by the security engine across all 6 core capability surfaces:
- knowledge_read (wiki_query_tool)
- knowledge_write (wiki_apply_tool, wiki_ingest_tool)
- web_egress (net_fetch, web_search_tool)
- candidate_create (artifact_create, artifact_update)
- remote_tools (mcp__*)
- local_filesystem (bash, view_file, write_to_file)
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.config import parse_security_config
from myrm_agent_harness.agent.security.engine import evaluate_tool_call
from myrm_agent_harness.core.security.types import PermissionAction


def test_capability_surface_matrix_deny_enforcement() -> None:
    """Verify that setting knowledge_write and web_egress to deny strictly blocks them."""
    sec_cfg = parse_security_config(
        {
            "capabilityMatrix": {
                "knowledge_write": "deny",
                "web_egress": "deny",
                "remote_tools": "ask",
                "knowledge_read": "allow",
            },
        }
    )

    # 1. 知识库写操作严格硬拒绝 (Deny)
    action, _ = evaluate_tool_call(
        permission="knowledge_write",
        tool_input={"title": "Test", "content": "mutation"},
        config=sec_cfg,
        tool_name="wiki_apply_tool",
    )
    assert action == PermissionAction.DENY

    action_ingest, _ = evaluate_tool_call(
        permission="knowledge_write",
        tool_input={"doc": "raw data"},
        config=sec_cfg,
        tool_name="wiki_ingest_tool",
    )
    assert action_ingest == PermissionAction.DENY

    # 2. 知识库读操作放行 (Allow)
    action_read, _ = evaluate_tool_call(
        permission="knowledge_read",
        tool_input={"query": "my notes"},
        config=sec_cfg,
        tool_name="wiki_query_tool",
    )
    assert action_read == PermissionAction.ALLOW

    # 3. 网络出站操作严格硬拒绝 (Deny)
    action_net, _ = evaluate_tool_call(
        permission="net_fetch",
        tool_input={"url": "https://external.api/data"},
        config=sec_cfg,
        tool_name="web_fetch_tool",
    )
    assert action_net == PermissionAction.DENY

    # 4. 远程 MCP 工具操作触发审批 (Ask)
    action_mcp, _ = evaluate_tool_call(
        permission="remote_tools",
        tool_input={"prompt": "list repos"},
        config=sec_cfg,
        tool_name="mcp__github__list_repos",
    )
    assert action_mcp == PermissionAction.ASK


def test_capability_surface_autonomous_allow_all() -> None:
    """Verify autonomous preset where all surfaces are set to allow."""
    sec_cfg = parse_security_config(
        {
            "domainHitlEnabled": False,
            "capabilityMatrix": {
                "knowledge_read": "allow",
                "knowledge_write": "allow",
                "web_egress": "allow",
                "candidate_create": "allow",
                "remote_tools": "allow",
                "local_filesystem": "allow",
            },
        }
    )

    action_write, _ = evaluate_tool_call(
        permission="knowledge_write",
        tool_input={"title": "Notes"},
        config=sec_cfg,
        tool_name="wiki_apply_tool",
    )
    assert action_write == PermissionAction.ALLOW

    # web_search_tool (non-URL)
    action_search, _ = evaluate_tool_call(
        permission="web_egress",
        tool_input={"query": "test query"},
        config=sec_cfg,
        tool_name="web_search_tool",
    )
    assert action_search == PermissionAction.ALLOW

    # net_fetch with domainHitlEnabled=False
    action_net, _ = evaluate_tool_call(
        permission="net_fetch",
        tool_input={"url": "https://example.com"},
        config=sec_cfg,
        tool_name="web_fetch_tool",
    )
    assert action_net == PermissionAction.ALLOW


def test_capability_surface_guarded_posture() -> None:
    """Verify guarded preset (remote_tools deny, web_egress ask, knowledge_write ask)."""
    sec_cfg = parse_security_config(
        {
            "capabilityMatrix": {
                "knowledge_read": "allow",
                "knowledge_write": "ask",
                "web_egress": "ask",
                "candidate_create": "allow",
                "remote_tools": "deny",
                "local_filesystem": "ask",
            },
        }
    )

    # 远程外部工具被硬阻断
    action_mcp, _ = evaluate_tool_call(
        permission="mcp_invoke",
        tool_input={"cmd": "run"},
        config=sec_cfg,
        tool_name="mcp__dangerous__exec",
    )
    assert action_mcp == PermissionAction.DENY

    # 网络操作需要人工确认
    action_net, _ = evaluate_tool_call(
        permission="net_fetch",
        tool_input={"url": "https://api.github.com"},
        config=sec_cfg,
        tool_name="web_fetch_tool",
    )
    assert action_net == PermissionAction.ASK

    # 知识库写入需要确认
    action_write, _ = evaluate_tool_call(
        permission="knowledge_write",
        tool_input={"title": "Log"},
        config=sec_cfg,
        tool_name="wiki_apply_tool",
    )
    assert action_write == PermissionAction.ASK


def test_specific_rule_overrides_capability_surface() -> None:
    """Verify that specific permission rules take precedence over capabilityMatrix defaults."""
    sec_cfg = parse_security_config(
        {
            "capabilityMatrix": {
                "knowledge_write": "allow",
            },
            # 用户专门对 wiki_apply_tool 施加硬拒绝规则
            "permissions": {
                "wiki_apply_tool": "deny",
            },
        }
    )

    # 具体规则阻断 wiki_apply_tool
    action_apply, _ = evaluate_tool_call(
        permission="knowledge_write",
        tool_input={"title": "Denied doc"},
        config=sec_cfg,
        tool_name="wiki_apply_tool",
    )
    assert action_apply == PermissionAction.DENY

    # 但未单独覆写的 wiki_ingest_tool 继承 capabilityMatrix 的 allow
    action_ingest, _ = evaluate_tool_call(
        permission="knowledge_write",
        tool_input={"raw": "test"},
        config=sec_cfg,
        tool_name="wiki_ingest_tool",
    )
    assert action_ingest == PermissionAction.ALLOW
