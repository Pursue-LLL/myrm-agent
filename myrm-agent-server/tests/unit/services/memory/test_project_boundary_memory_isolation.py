"""Tests for ClientProjectBoundaryZeroLeakageSandboxSuite.

Validates:
1. Deterministic project-scoped namespace derivation (primary_namespace is project:{project_id})
2. Cross-project memory zero-leakage immunity (foreign project:* namespaces stripped)
3. One-way read inheritance from global scope
4. Backward-compatible fallback when project_id is None
5. MemoryManager isolated storage & retrieval between different projects
6. Project workspace boundary confinement and escape rejection
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.context_bundle.spec import DEFAULT_BUNDLE_ID
from myrm_agent_harness.toolkits.memory import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.config import (
    AgentMemoryPolicy,
    MemoryScopeLevel,
    MemoryWritePolicy,
)
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

from app.core.memory.adapters.policy import derive_binding_namespaces
from app.core.memory.adapters.setup import resolve_context_binding
from app.services.project.workspace_boundary import (
    ProjectWorkspaceEscapeError,
    assert_project_workspace_boundary,
    is_cross_project_workspace_collision,
    validate_project_workspace_boundary,
)


def test_derive_binding_namespaces_project_isolation() -> None:
    """Project A and Project B must receive distinct project-scoped namespaces."""
    ns_a = derive_binding_namespaces(
        namespaces=None,
        shared_context_ids=None,
        agent_id="developer",
        channel_id="web_chat",
        conversation_id="conv-1",
        task_id=None,
        project_id="project_alpha",
        memory_policy=None,
    )
    ns_b = derive_binding_namespaces(
        namespaces=None,
        shared_context_ids=None,
        agent_id="developer",
        channel_id="web_chat",
        conversation_id="conv-2",
        task_id=None,
        project_id="project_beta",
        memory_policy=None,
    )

    # Primary namespace for Project A is project:project_alpha
    assert ns_a[0] == "project:project_alpha"
    assert "project:project_beta" not in ns_a
    assert "global" in ns_a

    # Primary namespace for Project B is project:project_beta
    assert ns_b[0] == "project:project_beta"
    assert "project:project_alpha" not in ns_b
    assert "global" in ns_b


def test_zero_leakage_strips_foreign_project_namespaces() -> None:
    """Foreign project namespaces passed in incoming namespaces must be sanitized."""
    contaminated_incoming = [
        "project:foreign_secret_project",
        "custom_label",
        "shared:team_notes",
    ]
    sanitized = derive_binding_namespaces(
        namespaces=contaminated_incoming,
        shared_context_ids=None,
        agent_id="developer",
        channel_id=None,
        conversation_id="conv-1",
        task_id=None,
        project_id="my_safe_project",
        memory_policy=None,
    )

    assert "project:foreign_secret_project" not in sanitized
    assert "project:my_safe_project" in sanitized
    assert sanitized[0] == "project:my_safe_project"
    assert "custom_label" in sanitized


def test_project_memory_policy_one_way_inheritance() -> None:
    """Project namespaces honor read_scopes while keeping project namespace as primary write target."""
    policy = AgentMemoryPolicy(
        read_scopes=(MemoryScopeLevel.GLOBAL,),
        write_policy=MemoryWritePolicy.INHERIT,
    )
    ns = derive_binding_namespaces(
        namespaces=None,
        shared_context_ids=None,
        agent_id="developer",
        channel_id="web_chat",
        conversation_id="conv-1",
        task_id=None,
        project_id="proj_shielded",
        memory_policy=policy,
    )

    # project namespace is primary write target, global is inherited read scope
    assert ns[0] == "project:proj_shielded"
    assert "global" in ns
    assert "agent:developer" not in ns


def test_fallback_when_project_id_is_none() -> None:
    """When project_id is None, namespace derivation falls back to standard multi-scope order."""
    ns = derive_binding_namespaces(
        namespaces=None,
        shared_context_ids=None,
        agent_id="developer",
        channel_id="web_chat",
        conversation_id="conv-default",
        task_id=None,
        project_id=None,
        memory_policy=None,
    )
    assert "global" in ns
    assert "agent:developer" in ns
    assert not any(item.startswith("project:") for item in ns)


def test_resolve_context_binding_carries_project_id() -> None:
    """ResolvedContextBinding carries normalized project_id."""
    binding = resolve_context_binding(
        namespaces=None,
        agent_id="developer",
        channel_id="web_chat",
        conversation_id="chat-abc",
        task_id=None,
        project_id="  proj_xyz  ",
        bundle_id="custom_bundle",
    )
    assert binding.project_id == "proj_xyz"
    assert binding.namespaces[0] == "project:proj_xyz"
    assert binding.bundle_id == "custom_bundle"

    # Default fallback
    binding_none = resolve_context_binding(
        namespaces=None,
        agent_id="developer",
        channel_id=None,
        conversation_id=None,
        task_id=None,
        project_id=None,
    )
    assert binding_none.project_id is None
    assert binding_none.bundle_id == DEFAULT_BUNDLE_ID


@pytest.mark.asyncio
async def test_cross_project_memory_manager_zero_leakage(tmp_path: Path) -> None:
    """Memories stored in Project A must be invisible to Project B."""
    embedding_config = EmbeddingConfig(model="openai/text-embedding-3-small", api_key="sk-test")

    binding_a = resolve_context_binding(
        namespaces=None,
        agent_id="general_agent",
        channel_id="web_chat",
        conversation_id="chat-a",
        task_id=None,
        project_id="project_finance",
    )
    binding_b = resolve_context_binding(
        namespaces=None,
        agent_id="general_agent",
        channel_id="web_chat",
        conversation_id="chat-b",
        task_id=None,
        project_id="project_health",
    )

    base_path_a = tmp_path / "proj_a_mem"
    base_path_b = tmp_path / "proj_b_mem"

    mgr_a = await create_local_memory_manager(
        base_path=base_path_a,
        embedding_config=embedding_config,
        namespaces=binding_a.namespaces,
        agent_id=binding_a.agent_id,
        channel_id=binding_a.channel_id,
        conversation_id=binding_a.conversation_id,
        task_id=binding_a.task_id,
    )
    mgr_b = await create_local_memory_manager(
        base_path=base_path_b,
        embedding_config=embedding_config,
        namespaces=binding_b.namespaces,
        agent_id=binding_b.agent_id,
        channel_id=binding_b.channel_id,
        conversation_id=binding_b.conversation_id,
        task_id=binding_b.task_id,
    )

    # Primary namespace verification: both managers scope to their respective project
    assert mgr_a.scope.primary_namespace == "project:project_finance"
    assert mgr_b.scope.primary_namespace == "project:project_health"

    # Write a project profile attribute into Project A
    await mgr_a.set_system_profile_attribute("project_secret", "finance_confidential_vault_token")

    # Read back from Project A
    val_a = await mgr_a.get_profile_attribute("project_secret")
    assert val_a == "finance_confidential_vault_token"

    # Project B reads the same key -> Zero-Leakage: must be None!
    val_b = await mgr_b.get_profile_attribute("project_secret")
    assert val_b is None

    # Write a rule into Project A
    await mgr_a.add_rule(
        trigger="when logging finance events",
        action="Audit requirements mandate full ledger hashing",
    )

    # Project A has the rule in its namespace
    rules_a = await mgr_a._relational.list_rules(namespaces=mgr_a.namespaces)
    assert len(rules_a) == 1
    assert "ledger hashing" in rules_a[0].action

    # Project B must not see Project A's rules -> Zero-Leakage!
    rules_b = await mgr_b._relational.list_rules(namespaces=mgr_b.namespaces)
    assert len(rules_b) == 0


def test_project_workspace_boundary_enforcement() -> None:
    """Workspace boundary rejects path traversal escapes and foreign directories."""
    with tempfile.TemporaryDirectory() as tmp_root:
        root_path = Path(tmp_root)
        proj_a = root_path / "project_a"
        proj_b = root_path / "project_b"
        proj_a.mkdir()
        proj_b.mkdir()

        safe_file = proj_a / "src" / "index.ts"
        safe_file.parent.mkdir(parents=True)
        safe_file.touch()

        # Valid subpath
        assert validate_project_workspace_boundary(safe_file, proj_a) is True
        assert assert_project_workspace_boundary(safe_file, proj_a) == str(safe_file.resolve())

        # Root itself is valid
        assert validate_project_workspace_boundary(proj_a, proj_a) is True

        # Escapes to sibling project via ../
        escape_path = proj_a / ".." / "project_b" / "secret.env"
        assert validate_project_workspace_boundary(escape_path, proj_a) is False
        with pytest.raises(ProjectWorkspaceEscapeError):
            assert_project_workspace_boundary(escape_path, proj_a)

        # Collision detection between projects
        assert is_cross_project_workspace_collision(proj_a, proj_b) is False
        assert is_cross_project_workspace_collision(proj_a, proj_a) is True
        nested_sub = proj_a / "subfolder"
        assert is_cross_project_workspace_collision(proj_a, nested_sub) is True
