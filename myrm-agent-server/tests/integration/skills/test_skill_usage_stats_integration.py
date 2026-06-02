"""Integration test for A9 Skill Usage Statistics & Forgetting Mechanism.

Tests the complete flow from skill invocation to stats collection in real Agent execution.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector


@pytest.fixture
def temp_workspace() -> Path:
    """Create temporary workspace for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        skills_dir = workspace / "skills"
        skills_dir.mkdir()
        yield workspace


@pytest.fixture
def test_mcp_skill_dir(temp_workspace: Path) -> Path:
    """Create a test MCP skill directory."""
    skill_dir = temp_workspace / "skills" / "test_skill"
    skill_dir.mkdir(parents=True)

    # Create skill.yaml
    skill_yaml = {
        "name": "test_skill",
        "description": "A test skill for integration testing",
        "mcp": {
            "command": "echo",
            "args": ["test"],
            "env": {},
        },
    }
    (skill_dir / "skill.yaml").write_text(
        f"name: {skill_yaml['name']}\n"
        f"description: {skill_yaml['description']}\n"
        f"mcp:\n"
        f"  command: {skill_yaml['mcp']['command']}\n"
        f"  args:\n"
        f"    - {skill_yaml['mcp']['args'][0]}\n"
    )

    return skill_dir


@pytest.mark.integration
def test_skill_usage_stats_recorded_on_invocation(
    temp_workspace: Path,
    test_mcp_skill_dir: Path,
) -> None:
    """Test that skill usage stats are correctly recorded via SkillStatsCollector.

    This test verifies the core stats collection mechanism that powers A9 — the
    collector writes a durable ``.stats.json`` that the curator service reads.
    """
    # Setup: Ensure .stats.json doesn't exist yet
    stats_file = test_mcp_skill_dir / ".stats.json"
    assert not stats_file.exists(), "Stats file should not exist initially"

    # Exercise the collector directly (the unit that records each invocation).
    collector = SkillStatsCollector(temp_workspace)

    collector.record_usage(test_mcp_skill_dir, success=True, duration_ms=150.0)
    collector.flush()

    # Verify: Stats file should now exist
    assert stats_file.exists(), "Stats file should be created after invocation"

    # Verify: Stats content is correct
    stats_data = json.loads(stats_file.read_text())
    assert stats_data["call_count"] == 1
    assert stats_data["success_count"] == 1
    assert stats_data["failure_count"] == 0
    assert stats_data["total_duration_ms"] == 150.0
    assert stats_data["last_used_at"] is not None

    # Verify: SkillUsageStats can be loaded
    loaded_stats = collector.get_stats(test_mcp_skill_dir)
    assert loaded_stats.call_count == 1
    assert loaded_stats.success_count == 1
    assert loaded_stats.success_rate == 1.0
    assert loaded_stats.avg_duration_ms == 150.0


@pytest.mark.integration
def test_skill_usage_stats_accumulation(
    temp_workspace: Path,
    test_mcp_skill_dir: Path,
) -> None:
    """Test that multiple skill invocations accumulate stats correctly."""
    collector = SkillStatsCollector(temp_workspace)

    # First invocation (success)
    collector.record_usage(test_mcp_skill_dir, success=True, duration_ms=100.0)
    collector.flush()

    stats = collector.get_stats(test_mcp_skill_dir)
    assert stats.call_count == 1
    assert stats.success_rate == 1.0

    # Second invocation (success)
    collector.record_usage(test_mcp_skill_dir, success=True, duration_ms=200.0)
    collector.flush()

    stats = collector.get_stats(test_mcp_skill_dir)
    assert stats.call_count == 2
    assert stats.success_count == 2
    assert stats.success_rate == 1.0
    assert stats.avg_duration_ms == 150.0  # (100 + 200) / 2

    # Third invocation (failure)
    collector.record_usage(test_mcp_skill_dir, success=False, duration_ms=50.0)
    collector.flush()

    stats = collector.get_stats(test_mcp_skill_dir)
    assert stats.call_count == 3
    assert stats.success_count == 2
    assert stats.failure_count == 1
    assert stats.success_rate == pytest.approx(0.666, abs=0.01)  # 2/3
    assert stats.avg_duration_ms == pytest.approx(116.67, abs=0.5)  # (100 + 200 + 50) / 3


@pytest.mark.integration
def test_skill_stats_persistence_across_collectors(
    temp_workspace: Path,
    test_mcp_skill_dir: Path,
) -> None:
    """Test that skill stats persist across different SkillStatsCollector instances."""
    # First collector: record some usage
    collector1 = SkillStatsCollector(temp_workspace)
    collector1.record_usage(test_mcp_skill_dir, success=True, duration_ms=100.0)
    collector1.flush()

    # Second collector: should load existing stats
    collector2 = SkillStatsCollector(temp_workspace)
    stats = collector2.get_stats(test_mcp_skill_dir)
    assert stats.call_count == 1
    assert stats.success_count == 1

    # Add more usage with second collector
    collector2.record_usage(test_mcp_skill_dir, success=True, duration_ms=200.0)
    collector2.flush()

    # Third collector: verify accumulated stats
    collector3 = SkillStatsCollector(temp_workspace)
    stats = collector3.get_stats(test_mcp_skill_dir)
    assert stats.call_count == 2
    assert stats.success_count == 2
    assert stats.avg_duration_ms == 150.0
