"""Tests for the ACP default permission manager."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.acp.core.permission import DefaultPermissionManager
from myrm_agent_harness.toolkits.acp.types import PermissionDecision


class TestDefaultPermissionManager:
    @pytest.mark.asyncio
    async def test_allow_all_mode(self) -> None:
        pm = DefaultPermissionManager(mode="allow_all")
        assert await pm.check("Write", {}, "s1") == PermissionDecision.ALLOW_ONCE

    @pytest.mark.asyncio
    async def test_safe_mode_allows_read(self) -> None:
        pm = DefaultPermissionManager(mode="safe")
        assert await pm.check("Read", {}, "s1") == PermissionDecision.ALLOW_ONCE
        assert await pm.check("read_file", {}, "s1") == PermissionDecision.ALLOW_ONCE

    @pytest.mark.asyncio
    async def test_safe_mode_denies_write(self) -> None:
        pm = DefaultPermissionManager(mode="safe")
        assert await pm.check("Write", {}, "s1") == PermissionDecision.DENY_ONCE

    @pytest.mark.asyncio
    async def test_bypass_mode(self) -> None:
        pm = DefaultPermissionManager(mode="bypass")
        assert await pm.check("anything", {}, "s1") == PermissionDecision.ALLOW_ONCE

    @pytest.mark.asyncio
    async def test_allowlist_exact_match(self) -> None:
        pm = DefaultPermissionManager(mode="safe", allowed_tools=["Write"])
        assert await pm.check("Write", {}, "s1") == PermissionDecision.ALLOW_ONCE

    @pytest.mark.asyncio
    async def test_allowlist_wildcard(self) -> None:
        pm = DefaultPermissionManager(mode="safe", allowed_tools=["Bash(npm run *)"])
        assert await pm.check("Bash", {"command": "npm run test"}, "s1") == PermissionDecision.ALLOW_ONCE
        assert await pm.check("Bash", {"command": "rm -rf /"}, "s1") == PermissionDecision.DENY_ONCE

    @pytest.mark.asyncio
    async def test_session_approval_cache(self) -> None:
        pm = DefaultPermissionManager(mode="ask")
        pm.record_approval("Write", "s1")
        assert await pm.check("Write", {}, "s1") == PermissionDecision.ALLOW_ONCE
        assert await pm.check("Write", {}, "s2") == PermissionDecision.DENY_ONCE


class TestPermissionManagerEdgeCases:
    @pytest.mark.asyncio
    async def test_clear_session_cache(self) -> None:
        pm = DefaultPermissionManager(mode="ask")
        pm.record_approval("Write", "s1")
        pm.clear_session_cache("s1")
        assert await pm.check("Write", {}, "s1") == PermissionDecision.DENY_ONCE

    @pytest.mark.asyncio
    async def test_allowlist_empty_pattern(self) -> None:
        pm = DefaultPermissionManager(mode="safe", allowed_tools=["Bash()"])
        assert await pm.check("Bash", {"command": "anything"}, "s1") == PermissionDecision.ALLOW_ONCE

    @pytest.mark.asyncio
    async def test_allowlist_no_match(self) -> None:
        pm = DefaultPermissionManager(mode="safe", allowed_tools=["Read"])
        assert await pm.check("Write", {}, "s1") == PermissionDecision.DENY_ONCE

    def test_mode_property(self) -> None:
        pm = DefaultPermissionManager(mode="safe")
        assert pm.mode == "safe"
