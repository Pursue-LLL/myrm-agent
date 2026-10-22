"""Reuse the instance fixtures of the service-level tests."""

from tests.services.instance_archive.conftest import source_state, target_state

__all__ = ["source_state", "target_state"]
