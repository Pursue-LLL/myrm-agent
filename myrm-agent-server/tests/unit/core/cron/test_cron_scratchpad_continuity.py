"""Cron 跨轮记忆连续性测试：BoundedScratchpad 有界记事本的读写、截断、损坏自愈与路径清洗。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.cron.continuity.scratchpad import (
    BoundedScratchpad,
    InvalidJobIdError,
)


def test_bounded_scratchpad_save_load_and_atomic_replace() -> None:
    """测试 BoundedScratchpad 的常规读取、原子保存、1KB限制与环比上下文提示语。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        scratchpad = BoundedScratchpad(storage_dir)

        # 初始读取空状态
        assert scratchpad.load("job_daily_report") == {}
        assert scratchpad.format_continuity_context("job_daily_report") is None

        # 写入超长摘要与指标
        long_summary = "A" * 800  # 超出 500 限制
        metrics = {"error_count": "3", "p99_latency_ms": "120"}
        saved = scratchpad.save(
            job_id="job_daily_report",
            last_summary=long_summary,
            last_metrics=metrics,
        )
        assert saved is True

        # 读取并验证摘要被安全截断
        loaded = scratchpad.load("job_daily_report")
        assert len(loaded["last_summary"]) <= 500
        assert loaded["metric_error_count"] == "3"
        assert loaded["metric_p99_latency_ms"] == "120"

        # 验证提示语格式化
        context_prompt = scratchpad.format_continuity_context("job_daily_report")
        assert context_prompt is not None
        assert "[Previous Execution Memory]" in context_prompt
        assert "error_count: 3" in context_prompt

        # 测试文件损坏自愈：覆写为非 JSON
        file_path = storage_dir / "job_daily_report.scratchpad.json"
        file_path.write_text("corrupted{{{invalid_json", encoding="utf-8")
        healed = scratchpad.load("job_daily_report")
        assert healed == {}


def test_bounded_scratchpad_path_traversal_rejection() -> None:
    """测试 BoundedScratchpad 对目录遍历恶意标识符的严格清洗与拦截。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        scratchpad = BoundedScratchpad(Path(tmp_dir))

        malicious_ids = [
            "../../etc/passwd",
            "job/sub/123",
            "job name with spaces",
            "job$bad*char",
            "a" * 65,  # 超过 64 长度
        ]
        for bad_id in malicious_ids:
            with pytest.raises(InvalidJobIdError):
                scratchpad.load(bad_id)
            with pytest.raises(InvalidJobIdError):
                scratchpad.save(bad_id, last_summary="test")
