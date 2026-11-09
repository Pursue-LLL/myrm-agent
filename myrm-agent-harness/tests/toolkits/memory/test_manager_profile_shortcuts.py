"""The manager's profile shortcuts act on the real stores: system writes skip approval and a rollback restores keys."""

from __future__ import annotations

from collections.abc import Callable

from myrm_agent_harness.toolkits.memory import MemoryManager

NewManager = Callable[..., MemoryManager]


async def test_a_system_profile_write_is_stored_even_when_approval_is_required(new_manager: NewManager) -> None:
    manager = new_manager(approval_required=True)

    await manager.set_system_profile_attribute("browser_sessions", "[]")

    assert await manager.get_profile_attribute("browser_sessions") == "[]"


async def test_a_system_profile_key_is_removed_without_approval(new_manager: NewManager) -> None:
    manager = new_manager(approval_required=True)
    await manager.set_system_profile_attribute("browser_sessions", "[]")

    assert await manager.delete_system_profile_attribute("browser_sessions") is True
    assert await manager.get_profile_attribute("browser_sessions") is None
    assert await manager.delete_system_profile_attribute("browser_sessions") is False


async def test_a_profile_snapshot_reports_whether_the_key_exists_and_its_value(new_manager: NewManager) -> None:
    manager = new_manager()

    missing = await manager.get_profile_attribute_snapshot("tone")
    await manager.set_system_profile_attribute("tone", "formal")
    present = await manager.get_profile_attribute_snapshot("tone")

    assert (missing.exists, missing.value) == (False, None)
    assert (present.exists, present.value) == (True, "formal")


async def test_a_rollback_restores_values_and_removes_the_keys_that_did_not_exist(new_manager: NewManager) -> None:
    manager = new_manager()
    await manager.set_system_profile_attribute("tone", "formal")
    await manager.set_system_profile_attribute("language", "zh")

    restored = await manager.restore_profile_attributes({"tone": "casual", "language": None, "never_set": None})

    # Only the keys that changed count: the one rewritten and the one removed.
    assert restored == 2
    assert await manager.get_profile_attribute("tone") == "casual"
    assert await manager.get_profile_attribute("language") is None
