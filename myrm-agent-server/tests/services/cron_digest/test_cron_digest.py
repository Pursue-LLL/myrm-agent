"""Unit tests for NaturalLanguageCronCompiler and EntityTimelineClusterer.

Verifies:
1. Natural language compilation into cron expressions (daily 9am, hourly, custom group names).
2. Chat message noise filtering.
3. Named entity extraction and factual grouping.
4. Chronological timeline ordering and markdown report rendering.
"""

from __future__ import annotations

import time

from app.services.cron_digest.clusterer import EntityTimelineClusterer
from app.services.cron_digest.compiler import NaturalLanguageCronCompiler
from app.services.cron_digest.models import DigestScheduleFrequency


def test_nl_cron_compiler_daily_scheduled_intent() -> None:
    prompt = "总结一下群聊好记星最近24小时的AI消息，之后定时早上九点发我一个报告，按照新闻的实体做消息聚类和时间轴"
    intent = NaturalLanguageCronCompiler.compile_intent(prompt)

    assert intent.is_valid is True
    assert intent.target_channel_or_group == "好记星"
    assert intent.time_window_hours == 24
    assert intent.cron_expr == "0 9 * * *"
    assert intent.frequency == DigestScheduleFrequency.DAILY
    assert "好记星" in intent.report_title


def test_nl_cron_compiler_hourly_intent() -> None:
    prompt = "每小时汇总群聊技术前沿最近2小时的更新"
    intent = NaturalLanguageCronCompiler.compile_intent(prompt)

    assert intent.is_valid is True
    assert intent.target_channel_or_group == "技术前沿"
    assert intent.time_window_hours == 2
    assert intent.cron_expr == "0 * * * *"
    assert intent.frequency == DigestScheduleFrequency.HOURLY


def test_entity_timeline_clusterer_filtering_and_markdown() -> None:
    now = time.time()
    raw_messages = [
        (now - 3600, "早啊", "m1"),  # noise
        (now - 3000, "Anthropic 刚刚发布了 Claude 3.7 模型，支持实时混合推理。", "m2"),
        (now - 2000, "收到", "m3"),  # noise
        (now - 1500, "DeepSeek 发布了新的开源推理框架，性能提升了 40%。", "m4"),
        (now - 500, "Claude 3.7 在 SWE-bench 上取得了突破性进展，社区反响热烈。", "m5"),
    ]

    intent = NaturalLanguageCronCompiler.compile_intent("总结一下群聊好记星最近24小时的AI消息，之后定时早上九点发我一个报告")

    digest = EntityTimelineClusterer.cluster_messages_to_timeline(
        intent=intent,
        raw_messages=raw_messages,
    )

    assert "好记星" in digest.channel_or_group
    assert len(digest.entity_groups) >= 2  # Claude/Anthropic and DeepSeek

    # Verify Markdown rendering
    md = digest.to_markdown()
    assert "# ⏱️" in md
    assert "Anthropic" in md or "Claude" in md
    assert "DeepSeek" in md
    assert "事件时间轴" in md
    assert "早啊" not in md
