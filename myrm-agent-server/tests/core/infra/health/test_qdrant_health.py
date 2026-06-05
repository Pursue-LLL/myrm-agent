from unittest.mock import patch

import pytest
from myrm_agent_harness.infra.health.health_checker import HealthStatus, RecoveryStatus

from app.core.infra.health.qdrant import QdrantHealthChecker


@pytest.mark.asyncio
async def test_qdrant_health_checker_not_exists(tmp_path):
    with patch("app.core.infra.health.qdrant.settings") as mock_settings:
        mock_settings.database.qdrant_path = str(tmp_path / "nonexistent")
        checker = QdrantHealthChecker()
        result = await checker.check()

        assert result.status == HealthStatus.HEALTHY
        assert "does not exist yet" in result.message
        assert result.details["path"] == str(tmp_path / "nonexistent")


@pytest.mark.asyncio
async def test_qdrant_health_checker_exists(tmp_path):
    with patch("app.core.infra.health.qdrant.settings") as mock_settings:
        mock_settings.database.qdrant_path = str(tmp_path)
        checker = QdrantHealthChecker()
        result = await checker.check()

        assert result.status == HealthStatus.HEALTHY
        assert "Lock management is handled natively" in result.message
        assert result.details["path"] == str(tmp_path)


@pytest.mark.asyncio
async def test_qdrant_health_checker_recover():
    with patch("app.core.infra.health.qdrant.settings") as mock_settings:
        mock_settings.database.qdrant_path = "/tmp"
        checker = QdrantHealthChecker()
        result = await checker.recover()

        assert result.status == RecoveryStatus.SUCCESS
        assert "No manual recovery needed" in result.message
        assert result.actions_taken == ["None"]
