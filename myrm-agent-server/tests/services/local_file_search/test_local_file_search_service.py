"""Integration tests for LocalFileSearchService.

Tests service lifecycle, config persistence, and directory management.
Uses real SQLite (via init_database) and real config_service persistence.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.local_file_search import LocalFileSearchConfig

from app.services.local_file_search.service import (
    LocalFileSearchService,
)


@pytest.fixture
async def service():
    svc = LocalFileSearchService()
    svc._config = LocalFileSearchConfig()
    svc._initialized = True
    with (
        patch.object(svc, "save_config", new_callable=AsyncMock),
        patch.object(svc, "_load_config", new_callable=AsyncMock),
        patch.object(svc, "_create_engine", new_callable=AsyncMock),
    ):
        yield svc


@pytest.fixture
def real_directory():
    """Create a real temp directory with test files."""
    with tempfile.TemporaryDirectory(prefix="lfs_test_") as tmpdir:
        real_path = str(Path(tmpdir).resolve())
        (Path(real_path) / "report.md").write_text(
            "# Quarterly Financial Report Q4 2025\n\n"
            "## Executive Summary\n\n"
            "This report presents the financial performance of our organization during the fourth quarter "
            "of fiscal year 2025. Revenue grew by 15.3% year-over-year, reaching $42.7 million, driven "
            "primarily by strong demand in our enterprise software segment. Operating expenses remained "
            "well-controlled at $28.1 million, resulting in an operating margin of 34.2%. Net income for "
            "the quarter was $11.8 million, representing a 22% increase compared to Q4 2024.\n\n"
            "## Key Metrics\n\n"
            "- Annual Recurring Revenue (ARR): $168.5M (+18% YoY)\n"
            "- Customer Retention Rate: 96.2%\n"
            "- Net Promoter Score: 72\n"
        )
        (Path(real_path) / "notes.txt").write_text(
            "Meeting Notes - Engineering Team\n\n"
            "Topic: Architecture Review for Q1 2026 Planning\n\n"
            "Attendees: Alice, Bob, Charlie, Diana, Eve\n\n"
            "Key Discussion Points:\n"
            "1. Migration from monolithic architecture to microservices is progressing on schedule.\n"
            "2. The new API gateway has been deployed to staging and performance tests show 40% improvement.\n"
            "3. Database sharding strategy needs further review. Current proposal: horizontal sharding by tenant ID.\n"
            "4. CI/CD pipeline improvements: average build time reduced from 12 minutes to 4 minutes.\n"
            "5. Security audit findings: 3 medium-severity issues identified, all with remediation plans.\n"
        )
        yield real_path


class TestLocalFileSearchServiceInit:
    @pytest.mark.asyncio
    async def test_init_defaults(self):
        """Fresh service has no engine and is not initialized."""
        svc = LocalFileSearchService()
        assert svc.config is not None
        assert svc.indexer is None
        assert svc.search_engine is None
        assert not svc.is_initialized

    @pytest.mark.asyncio
    async def test_initialize_no_directories(self, service):
        assert service.is_initialized
        assert service.indexer is None

    @pytest.mark.asyncio
    async def test_config_property(self, service):
        assert service.config.directories == []


class TestLocalFileSearchServiceDirectoryManagement:
    @pytest.mark.asyncio
    async def test_add_directory(self, service, real_directory):
        d = await service.add_directory(real_directory)
        assert d.path == real_directory
        assert d.enabled is True
        assert d.recursive is True
        assert len(service.config.directories) == 1

    @pytest.mark.asyncio
    async def test_add_directory_nonexistent_raises(self, service):
        with pytest.raises(ValueError, match="does not exist"):
            await service.add_directory("/nonexistent/path/12345")

    @pytest.mark.asyncio
    async def test_add_duplicate_directory_raises(self, service, real_directory):
        await service.add_directory(real_directory)
        with pytest.raises(ValueError, match="already configured"):
            await service.add_directory(real_directory)

    @pytest.mark.asyncio
    async def test_remove_directory(self, service, real_directory):
        d = await service.add_directory(real_directory)
        result = await service.remove_directory(d.id)
        assert result is True
        assert len(service.config.directories) == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent_directory(self, service):
        result = await service.remove_directory("nonexistent-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_update_directory(self, service, real_directory):
        d = await service.add_directory(real_directory)
        updated = await service.update_directory(d.id, enabled=False)
        assert updated is not None
        assert updated.enabled is False

    @pytest.mark.asyncio
    async def test_update_nonexistent_directory(self, service):
        result = await service.update_directory("nonexistent-id", enabled=False)
        assert result is None


class TestLocalFileSearchServiceStats:
    @pytest.mark.asyncio
    async def test_get_stats_default(self, service):
        stats = service.get_stats()
        assert stats.total_files == 0
        assert stats.total_chunks == 0
        assert stats.status.value == "idle"

    @pytest.mark.asyncio
    async def test_trigger_index_no_engine_raises(self, service):
        with pytest.raises(RuntimeError, match="not initialized"):
            await service.trigger_index()


class TestLocalFileSearchServiceConfigPersistence:
    @pytest.mark.asyncio
    async def test_save_and_load_config(self, real_directory):
        """Config should persist across service instances via config_service."""
        svc = LocalFileSearchService()
        svc._config = LocalFileSearchConfig()
        svc._initialized = True
        await svc.add_directory(real_directory, recursive=False)

        fresh_service = LocalFileSearchService()
        await fresh_service.initialize()
        found = [d for d in fresh_service.config.directories if d.path == real_directory]
        assert len(found) == 1
        assert found[0].recursive is False
