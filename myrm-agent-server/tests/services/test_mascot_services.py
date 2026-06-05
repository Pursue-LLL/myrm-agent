"""Unit tests for the Mascot services.

Tests state mapping logic and temporary matplotlib cache cleanup operations.
"""

import os
import time
from pathlib import Path

from app.services.mascot import (
    MascotLRUCacheCleanupService,
    MascotStateMapper,
    MascotStatus,
)


def test_mascot_state_mapper():
    """Verify raw agent framework events map to the correct mascot status states."""
    # Sleeping
    assert MascotStateMapper.map_event_to_mascot_state("agent_idle") == MascotStatus.SLEEPING
    assert MascotStateMapper.map_event_to_mascot_state("session_sleep") == MascotStatus.SLEEPING

    # Thinking
    assert MascotStateMapper.map_event_to_mascot_state("agent_start") == MascotStatus.THINKING
    assert MascotStateMapper.map_event_to_mascot_state("tool_call_start") == MascotStatus.THINKING

    # Panting (Budget Limits)
    assert MascotStateMapper.map_event_to_mascot_state("budget_warning") == MascotStatus.PANTING
    assert MascotStateMapper.map_event_to_mascot_state("token_limit_exceeded") == MascotStatus.PANTING

    # Celebrating
    assert MascotStateMapper.map_event_to_mascot_state("goal_completed") == MascotStatus.CELEBRATING
    assert MascotStateMapper.map_event_to_mascot_state("tests_passed") == MascotStatus.CELEBRATING

    # Dizzy (Errors/Lints)
    assert MascotStateMapper.map_event_to_mascot_state("tool_error", {"error_category": "compile"}) == MascotStatus.DIZZY


def test_mascot_lru_cache_cleanup(tmp_path: Path):
    """Verify that MascotLRUCacheCleanupService prunes expired WebP plots and preserves active ones."""
    # Setup test workspace structure
    plots_dir = tmp_path / ".myrm_plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    # Create an active plot file
    active_plot = plots_dir / "plot_active.webp"
    active_plot.touch()

    # Create an expired plot file (simulate modification time of 25 hours ago)
    expired_plot = plots_dir / "plot_expired.webp"
    expired_plot.touch()
    expired_time = time.time() - (25 * 3600)
    os.utime(expired_plot, (expired_time, expired_time))

    # Create a non-webp file (should be ignored)
    ignored_file = plots_dir / "ignored.txt"
    ignored_file.touch()
    os.utime(ignored_file, (expired_time, expired_time))

    # Run cleanup
    cleaned_count = MascotLRUCacheCleanupService.run_cleanup(tmp_path)

    # Assertions
    assert cleaned_count == 1
    assert active_plot.exists()
    assert ignored_file.exists()
    assert not expired_plot.exists()
