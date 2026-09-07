"""Unit tests for NaturalLanguageCronCompiler and EntityTimelineClusterer.

Validates:
1. Natural language instruction parsing to cron schedule and target channel.
2. Noise filtering of high-frequency chatter messages.
3. Multi-entity extraction, grouping, and chronological timeline generation.
4. Markdown digest formatting and structure integrity.
"""

from __future__ import annotations

import time

from app.services.cron_digest.clusterer import EntityTimelineClusterer
from app.services.cron_digest.compiler import NaturalLanguageCronCompiler
from app.services.cron_digest.models import DigestScheduleFrequency


def test_nl_cron_compiler_daily_schedule() -> None:
    prompt = "总结一下群聊好记星最近24小时的AI消息，之后定时早上九点发我一个报告，按照新闻的实体做消息聚类和时间轴"
    intent = NaturalLanguageCronCompiler.compile_intent(prompt)

    assert intent.is_valid is True
    assert intent.cron_expr == "0 9 * * *"
    assert intent.target_channel_or_group == "好记星"
    assert intent.time_window_hours == 24
    assert intent.frequency == DigestScheduleFrequency.DAILY
    assert "好记星" in intent.report_title
    assert "AI" in intent.focus_topic


def test_nl_cron_compiler_hourly_schedule() -> None:
    prompt = "每小时汇总群聊研发核心群最近3小时的技术研发动态"
    intent = NaturalLanguageCronCompiler.compile_intent(prompt)

    assert intent.is_valid is True
    assert intent.cron_expr == "0 * * * *"
    assert intent.target_channel_or_group == "研发核心群"
    assert intent.time_window_hours == 3
    assert intent.frequency == DigestScheduleFrequency.HOURLY


def test_entity_timeline_clusterer_noise_filtering() -> None:
    assert EntityTimelineClusterer.filter_noise("收到") is False
    assert EntityTimelineClusterer.filter_noise("666") is False
    assert EntityTimelineClusterer.filter_noise("+1") is False
    assert EntityTimelineClusterer.filter_noise("DeepSeek 发布了全新架构模型 DeepSeek-V3") is True
    assert EntityTimelineClusterer.filter_noise("OpenAI o3-mini 开始向所有付费用户灰度推送") is True


def test_entity_timeline_clusterer_pipeline() -> None:
    prompt = "总结一下群聊好记星最近24小时的AI消息，之后定时早上九点发我一个报告"
    intent = NaturalLanguageCronCompiler.compile_intent(prompt)

    now = time.time()
    raw_messages = [
        (now - 3600, "OpenAI 正式宣布启动 Sora 商业化开放内测", "msg_1"),
        (now - 3500, "收到", "msg_noise_1"),
        (now - 2400, "Anthropic 发布了 Claude 3.7 Sonnet 具备思考模式", "msg_2"),
        (now - 1200, "DeepSeek-R1 论文在学术界引发大模型推理讨论", "msg_3"),
        (now - 600, "字节跳动发布豆包工作桌面版，打通飞书企业协作", "msg_4"),
        (now - 300, "大家觉得这次的模型升级谁最亮眼？", "msg_5"),
    ]

    digest = EntityTimelineClusterer.cluster_messages_to_timeline(
        intent=intent,
        raw_messages=raw_messages,
    )

    assert digest.channel_or_group == "好记星"
    assert len(digest.entity_groups) >= 3

    # Check that OpenAI group exists and has 1 fact
    openai_group = next((g for g in digest.entity_groups if g.entity_name == "OpenAI"), None)
    assert openai_group is not None
    assert len(openai_group.facts) == 1
    assert "Sora" in openai_group.facts[0].fact_text

    # Check that Anthropic group exists
    anthropic_group = next((g for g in digest.entity_groups if g.entity_name == "Anthropic"), None)
    assert anthropic_group is not None

    # Check Markdown output
    md = digest.to_markdown()
    assert "# ⏱️" in md
    assert "好记星" in md
    assert "OpenAI" in md
    assert "事件时间轴" in md
