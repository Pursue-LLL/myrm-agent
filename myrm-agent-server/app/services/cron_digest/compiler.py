"""Natural language compiler for scheduled digest and cron tasks.

Parses unstructured requests like:
"总结一下群聊好记星最近24小时的AI消息，之后定时早上九点发我一个报告，按照新闻的实体做消息聚类和时间轴"
into a structured CompiledCronIntent object with cron expression, target channel, and time window.

[INPUT]
- .models::CompiledCronIntent, DigestScheduleFrequency
- re, time (standard library)

[OUTPUT]
- NaturalLanguageCronCompiler: Parses natural language strings into executable cron job intents.

[POS]
Domain service in app/services/cron_digest/.
"""

from __future__ import annotations

import re

from .models import CompiledCronIntent, DigestScheduleFrequency


class NaturalLanguageCronCompiler:
    """Compiles free-form natural language prompts into structured cron digest configurations."""

    _TIME_WINDOW_RE = re.compile(r"最近\s*(\d+)\s*(小时|天|h|d|day|hours?)", re.IGNORECASE)
    _GROUP_NAME_RE = re.compile(
        r"(?:群聊|群|频道|channel)\s*([a-zA-Z0-9_\u4e00-\u9fa5\-]+?)(?=(?:最近|前|的|在|里|中|\s|$))",
        re.IGNORECASE,
    )
    _DAILY_TIME_RE = re.compile(r"(?:每天|每日|每早|定时)?\s*(?:早上|上午|下午|晚上)?\s*([0-2]?\d)(?:点|:|：)(\d{0,2})", re.IGNORECASE)
    _HOURLY_RE = re.compile(r"(?:每小时|每个小时|整点)", re.IGNORECASE)
    _WEEKLY_RE = re.compile(r"(?:每周|每星期)([一二三四五六日天1-7])?\s*(?:早上|上午)?\s*([0-2]?\d)?(?:点)?", re.IGNORECASE)

    @classmethod
    def compile_intent(cls, prompt: str) -> CompiledCronIntent:
        """Parse natural language instruction into structured CompiledCronIntent."""
        clean_prompt = prompt.strip()
        if not clean_prompt:
            return CompiledCronIntent(
                cron_expr="",
                target_channel_or_group="",
                time_window_hours=24,
                frequency=DigestScheduleFrequency.DAILY,
                report_title="定时简报",
                focus_topic="",
                is_valid=False,
                error_message="Prompt is empty",
            )

        # 1. Extract time window (default 24h)
        time_window_hours = 24
        tw_match = cls._TIME_WINDOW_RE.search(clean_prompt)
        if tw_match:
            num = int(tw_match.group(1))
            unit = tw_match.group(2).lower()
            if "天" in unit or "d" in unit:
                time_window_hours = num * 24
            else:
                time_window_hours = num

        # 2. Extract target group / channel
        target_group = "默认群聊"
        grp_match = cls._GROUP_NAME_RE.search(clean_prompt)
        if grp_match and grp_match.group(1).strip():
            target_group = grp_match.group(1).strip()

        # 3. Extract Schedule / Cron Expression
        cron_expr = "0 9 * * *"  # default: daily at 09:00
        frequency = DigestScheduleFrequency.DAILY

        if cls._HOURLY_RE.search(clean_prompt):
            cron_expr = "0 * * * *"
            frequency = DigestScheduleFrequency.HOURLY
        else:
            time_match = cls._DAILY_TIME_RE.search(clean_prompt)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                if "下午" in clean_prompt or "晚上" in clean_prompt:
                    if hour < 12:
                        hour += 12
                cron_expr = f"{minute} {hour} * * *"
                frequency = DigestScheduleFrequency.DAILY

        # 4. Extract Focus Topic & Title
        focus_topic = "AI消息与行业动态"
        if "ai" in clean_prompt.lower() or "大模型" in clean_prompt:
            focus_topic = "AI与大模型动态"
        elif "业务" in clean_prompt or "销售" in clean_prompt:
            focus_topic = "业务与销售跟进"
        elif "研发" in clean_prompt or "技术" in clean_prompt:
            focus_topic = "技术研发与架构动态"

        report_title = f"{target_group} · {focus_topic} 定时研报"

        return CompiledCronIntent(
            cron_expr=cron_expr,
            target_channel_or_group=target_group,
            time_window_hours=time_window_hours,
            frequency=frequency,
            report_title=report_title,
            focus_topic=focus_topic,
            is_valid=True,
        )
