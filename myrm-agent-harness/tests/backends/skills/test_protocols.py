"""Tests for skill backend protocols.

Note: Protocols are not @runtime_checkable, so we test structural conformance
by verifying the concrete classes have the required methods with correct signatures.
"""

import inspect

from myrm_agent_harness.backends.skills.protocols import SnapshotStoreProtocol


class TestSnapshotStoreProtocol:
    def test_concrete_class_has_required_methods(self):
        """Verify SnapshotStoreProtocol requires get_active_version."""

        class ConcreteStore:
            async def get_active_version(self, skill_id: str) -> object | None:
                return None

        store = ConcreteStore()
        assert hasattr(store, "get_active_version")
        assert inspect.iscoroutinefunction(store.get_active_version)

    def test_protocol_defines_interface(self):
        assert hasattr(SnapshotStoreProtocol, "get_active_version")
