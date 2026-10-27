"""Both subagent factories mount the file/shell meta tools the child's capability can use.

A custom agent whose workspace policy is read-only runs under a READ-only handle. The factories used to ask
for the full tool surface regardless, so the model was offered write and shell tools the executor would only
refuse at call time.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.sub_agents.spawn_capability import (
    derive_readonly_capability,
    derive_spawn_capability,
    derive_verifier_capability,
)
from myrm_agent_harness.agent.sub_agents.types import MemoryIsolationPolicy, SubagentConfig
from myrm_agent_harness.core.security.ocap import CapabilityHandle, capability_scope

from app.ai_agents.custom_agent_factory import CustomAgentFactory, EphemeralAgentFactory

_Mount = tuple[FileAccessMode, bool]
_FULL: _Mount = (FileAccessMode.FULL, True)
_VERIFIER: _Mount = (FileAccessMode.WORKSPACE_READ_ONLY, True)
_READ_ONLY: _Mount = (FileAccessMode.WORKSPACE_READ_ONLY, False)


def _writer_handle(workspace: Path) -> CapabilityHandle:
    parent = SimpleNamespace(_last_context={"workspace_path": str(workspace)})
    return derive_spawn_capability(parent_agent=parent, agent_type="writer", readonly=False)


_HANDLES: dict[str, tuple[Callable[[Path], CapabilityHandle | None], _Mount]] = {
    "no_handle": (lambda _: None, _FULL),
    "writer": (_writer_handle, _FULL),
    "verifier": (lambda _: derive_verifier_capability("verifier"), _VERIFIER),
    "read_only": (lambda _: derive_readonly_capability("reviewer"), _READ_ONLY),
}


@pytest.fixture
def captured_mount(monkeypatch: pytest.MonkeyPatch) -> list[_Mount]:
    """The (file_access_mode, enable_shell_tools) pair each built agent was assembled with."""
    mounts: list[_Mount] = []

    async def fake_create_skill_agent(**kwargs: object) -> SimpleNamespace:
        mounts.append((kwargs["file_access_mode"], kwargs["enable_shell_tools"]))  # type: ignore[arg-type]
        return SimpleNamespace()

    import myrm_agent_harness.api as api_module

    monkeypatch.setattr(api_module, "create_skill_agent", fake_create_skill_agent)
    monkeypatch.setattr("app.platform_utils.get_storage_provider", lambda: SimpleNamespace())
    return mounts


def _parent() -> SimpleNamespace:
    return SimpleNamespace(
        llm=SimpleNamespace(model="parent"),
        executor=None,
        memory_manager=None,
        enable_conversation_search=False,
        incognito_mode=False,
        enable_wiki=False,
        _last_context={"chat_id": "chat-mount"},
    )


async def _build_custom() -> None:
    profile = SimpleNamespace(
        display_name="Reviewer",
        skills=[],
        enabled_builtin_tools=(),
        max_iterations=8,
        memory_policy=None,
        metadata={},
    )
    factory = CustomAgentFactory(agent_id="reviewer", agent_profile=profile)
    factory._initialized = True
    config = SubagentConfig(
        display_name="Reviewer",
        system_prompt="You review code.",
        llm=SimpleNamespace(model="direct"),
        memory_isolation=MemoryIsolationPolicy.EPHEMERAL_SESSION,
    )
    await factory.build(config, [], "review auth.py", _parent(), current_depth=1)


async def _build_ephemeral() -> None:
    factory = EphemeralAgentFactory(agent_id="reviewer", metadata={"enabled_builtin_tools": []})
    config = SubagentConfig(display_name="Reviewer", system_prompt="You review code.")
    await factory.build(config, [], "review auth.py", _parent(), current_depth=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("build", [_build_custom, _build_ephemeral], ids=["custom", "ephemeral"])
@pytest.mark.parametrize("handle_kind", list(_HANDLES))
async def test_factory_mounts_what_the_childs_capability_allows(
    build: Callable[[], object], handle_kind: str, captured_mount: list[_Mount], tmp_path: Path
) -> None:
    make_handle, expected = _HANDLES[handle_kind]
    handle = make_handle(tmp_path)

    if handle is None:
        await build()  # type: ignore[misc]
    else:
        with capability_scope(handle):
            await build()  # type: ignore[misc]

    assert captured_mount == [expected]
