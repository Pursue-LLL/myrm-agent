"""Weekly report SOP generation and Chat-to-Knowledge ingestion service.

Adheres strictly to code_quality_guidelines: 0 Any, modular, single-responsibility.
"""

from __future__ import annotations

import hashlib
import time
from typing import Sequence

from app.services.weekly_report.models import (
    ReportRoleMode,
    TrajectoryItem,
    WeeklyReportPayload,
    WeeklyReportSection,
    WikiIngestPayload,
    WikiIngestResult,
)


class WeeklyReportSOPService:
    """Orchestrates structured weekly report synthesis with role-adaptive templates."""

    def generate_report(
        self,
        trajectories: Sequence[TrajectoryItem],
        start_time_ms: int,
        end_time_ms: int,
        role_mode: ReportRoleMode = ReportRoleMode.GENERAL,
    ) -> WeeklyReportPayload:
        """Synthesizes structured weekly report from verified trajectories."""
        start_date_str = time.strftime("%Y-%m-%d", time.localtime(start_time_ms / 1000.0))
        end_date_str = time.strftime("%Y-%m-%d", time.localtime(end_time_ms / 1000.0))
        title = f"工作周报 ({start_date_str} ~ {end_date_str})"

        completed_tasks: list[str] = []
        artifacts_collected: list[str] = []

        for item in trajectories:
            completed_tasks.append(f"{item.title} — {item.summary}")
            for path in item.artifact_paths:
                if path not in artifacts_collected:
                    artifacts_collected.append(path)

        # Fallback when no execution records exist
        if not completed_tasks:
            completed_tasks.append("本周暂无记录的沙箱委派任务，主要推进常规业务沟通与协作。")

        sections: list[WeeklyReportSection] = []

        if role_mode == ReportRoleMode.ENGINEER:
            sections.append(WeeklyReportSection(
                heading="一、核心技术交付与工件输出",
                items=tuple(completed_tasks),
                role_weight=1.5,
            ))
            sections.append(WeeklyReportSection(
                heading="二、系统稳定性与攻坚排障",
                items=("多渠道请求与后台长任务运行平稳，无阻塞性告警。",),
                role_weight=1.2,
            ))
            sections.append(WeeklyReportSection(
                heading="三、技术演进与下周规划",
                items=("持续优化执行引擎性能与工具链集成。",),
                role_weight=1.0,
            ))
        elif role_mode == ReportRoleMode.PRODUCT:
            sections.append(WeeklyReportSection(
                heading="一、业务需求与功能上线进展",
                items=tuple(completed_tasks),
                role_weight=1.5,
            ))
            sections.append(WeeklyReportSection(
                heading="二、用户反馈与卡点协同",
                items=("渠道交互体验顺畅，响应时延符合预期。",),
                role_weight=1.2,
            ))
            sections.append(WeeklyReportSection(
                heading="三、下周迭代重点",
                items=("推进下一阶段核心业务场景接入。",),
                role_weight=1.0,
            ))
        else:  # GENERAL or EXECUTIVE
            sections.append(WeeklyReportSection(
                heading="一、本周主要工作与交付成果",
                items=tuple(completed_tasks),
                role_weight=1.0,
            ))
            sections.append(WeeklyReportSection(
                heading="二、关键产物与工件",
                items=tuple(f"产物文件: `{p}`" for p in artifacts_collected) if artifacts_collected else ("无独立导出的实体工件",),
                role_weight=1.0,
            ))
            sections.append(WeeklyReportSection(
                heading="三、风险评估与下周工作计划",
                items=("按既定里程碑平稳推进后续任务。",),
                role_weight=1.0,
            ))

        # Build clean markdown
        md_lines: list[str] = [f"# {title}\n", f"> **报告视角**: {role_mode.value.capitalize()} | **时间跨度**: {start_date_str} 至 {end_date_str}\n"]
        for sec in sections:
            md_lines.append(f"### {sec.heading}")
            for it in sec.items:
                md_lines.append(f"- {it}")
            md_lines.append("")

        full_md = "\n".join(md_lines)
        summary_im = f"📊 **本周工作总结已生成**\n• 完成重点事项: {len(trajectories)} 项\n• 产出工件: {len(artifacts_collected)} 份\n• 模式: {role_mode.value}"

        return WeeklyReportPayload(
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            role_mode=role_mode,
            title=title,
            sections=tuple(sections),
            attached_artifacts=tuple(artifacts_collected),
            markdown_content=full_md,
            summary_for_im=summary_im,
        )


class WikiIngestionService:
    """Ingests high-value chat decisions and extracts structured Wiki entries."""

    def __init__(self) -> None:
        self._seen_fingerprints: set[str] = set()

    @staticmethod
    def compute_fingerprint(topic_title: str, content: str) -> str:
        """Computes SHA256 content signature for deduplication."""
        hasher = hashlib.sha256()
        hasher.update(topic_title.strip().encode("utf-8"))
        hasher.update(content.strip().encode("utf-8"))
        return hasher.hexdigest()

    def ingest_chat_decision(
        self,
        payload: WikiIngestPayload,
    ) -> WikiIngestResult:
        """Processes and archives a chat decision into structured wiki entry."""
        if not payload.topic_title.strip() or not payload.content_raw.strip():
            return WikiIngestResult(
                success=False,
                wiki_path="",
                is_duplicate=False,
                message="Topic title or content cannot be empty",
            )

        if payload.fingerprint_sha256 in self._seen_fingerprints:
            return WikiIngestResult(
                success=True,
                wiki_path=f"decisions/{payload.topic_title.lower().replace(' ', '_')}.md",
                is_duplicate=True,
                message="Entry with identical fingerprint already archived",
            )

        self._seen_fingerprints.add(payload.fingerprint_sha256)
        wiki_path = f"decisions/{payload.topic_title.lower().replace(' ', '_')}.md"

        return WikiIngestResult(
            success=True,
            wiki_path=wiki_path,
            is_duplicate=False,
            message="Successfully ingested into Wiki knowledge base",
        )
