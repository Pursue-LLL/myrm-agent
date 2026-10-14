"""Review policy for security findings that background skill learning introduces.

[INPUT]
- myrm_agent_harness.backends.skills.scanning::scan_skill_content, compute_scan_summary (POS: 技能内容安全扫描)
- myrm_agent_harness.backends.skills.types::SecurityFindingDetail, SecurityScanSummary (POS: 扫描摘要 DTO)

[OUTPUT]
- ScanRiskAssessment: 一次评估的结论（新增风险类别、扫描是否失败、扫描摘要）
- assess_scan_risk: 对比"原内容 → 新内容"，判定后台学习是否需要人工复核
- NEW_FINDING_SIGNAL_PREFIX / SCAN_UNAVAILABLE_SIGNAL: 风控信号常量（审核卡片按信号本地化）

[POS]
后台自动学习（复盘 skill_draft 与进化提案）共用的"高危新增 → 人工复核"策略。CRITICAL 由各入口的硬拦截处理；
本策略只回答：这次改动是否让技能多出了需要人看一眼的 HIGH 级风险。
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from dataclasses import dataclass

from myrm_agent_harness.backends.skills.scanning import compute_scan_summary, scan_skill_content
from myrm_agent_harness.backends.skills.types import SecurityFindingDetail, SecurityScanSummary

logger = logging.getLogger(__name__)

NEW_FINDING_SIGNAL_PREFIX = "new_high_finding:"
SCAN_UNAVAILABLE_SIGNAL = "scan_unavailable"

# 这些类别的 HIGH 命中取决于技能用途：GUI 技能必然截图点击、联网技能必然访问网络、
# 文档技能会引用路径与提示词。对它们逐条人工复核会淹没真正的风险，因此只对 CRITICAL 生效。
CONTEXT_DEPENDENT_THREATS = frozenset(
    {
        "filesystem_access",
        "memory_config_snooping",
        "network_access",
        "path_traversal",
        "prompt_injection",
        "screen_input",
    }
)

_FindingKey = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class ScanRiskAssessment:
    """Outcome of scanning a proposed skill change against its original content."""

    new_threats: tuple[str, ...] = ()
    """Threat categories whose HIGH+ finding count grew; sorted and unique."""

    scan_failed: bool = False
    """The scanner raised; the change must not be trusted as clean."""

    scan_summary: dict[str, object] | None = None
    """Summary of the proposed content for the review card; None when the scan failed."""

    @property
    def requires_review(self) -> bool:
        return self.scan_failed or bool(self.new_threats)

    @property
    def signals(self) -> list[str]:
        """Risk signals in the ``reason_code`` vocabulary shared with the approval flow."""
        if self.scan_failed:
            return [SCAN_UNAVAILABLE_SIGNAL]
        return [f"{NEW_FINDING_SIGNAL_PREFIX}{threat}" for threat in self.new_threats]


def _needs_review(finding: SecurityFindingDetail) -> bool:
    if finding.severity == "critical":
        return True
    return finding.severity == "high" and finding.threat_type not in CONTEXT_DEPENDENT_THREATS


def _review_worthy_counts(summary: SecurityScanSummary) -> Counter[_FindingKey]:
    """Count review-worthy findings per (threat, description, severity); line numbers are positional noise."""
    return Counter((f.threat_type, f.description, f.severity) for f in summary.findings if _needs_review(f))


def _assess(skill_name: str, proposed: str, original: str | None) -> ScanRiskAssessment:
    proposed_summary = compute_scan_summary(scan_skill_content(skill_name, proposed))
    baseline: Counter[_FindingKey] = Counter()
    if original:
        baseline = _review_worthy_counts(compute_scan_summary(scan_skill_content(skill_name, original)))
    # Multiset difference: one more occurrence of an already-present finding still counts as new,
    # so duplicating a risky line cannot slip through as "already existed".
    introduced = _review_worthy_counts(proposed_summary) - baseline
    return ScanRiskAssessment(
        new_threats=tuple(sorted({threat for threat, _, _ in introduced})),
        scan_summary=proposed_summary.to_dict(),
    )


async def assess_scan_risk(skill_name: str, proposed: str, *, original: str | None = None) -> ScanRiskAssessment:
    """Decide whether ``proposed`` adds HIGH+ risk beyond ``original`` (``None`` for a brand-new skill).

    Runs the regex scan in a worker thread so large skills never stall the event loop. A scanner
    failure is reported as ``scan_failed`` instead of being swallowed, because letting unscanned
    content through automatically is the one outcome this policy exists to prevent.
    """
    try:
        return await asyncio.to_thread(_assess, skill_name, proposed, original)
    except Exception as exc:
        logger.error("Skill scan risk assessment failed for '%s': %s", skill_name, exc)
        return ScanRiskAssessment(scan_failed=True)
