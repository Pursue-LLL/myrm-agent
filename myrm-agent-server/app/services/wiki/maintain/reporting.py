"""What a maintain run tells the outside: the issue list, the cron summary and the weekly report.

[INPUT]
- myrm_agent_harness.toolkits.wiki.core.types::LintIssue (POS: maintenance issue DTO)
- app.services.wiki.maintain.schemas::WikiMaintainRunResult (POS: run result the summary describes)

[OUTPUT]
- MAX_REPORTED_ISSUES: issues listed in a run result; the counters still cover all of them
- lint_issue_payloads: issue DTOs of a run result
- build_summary_text: cron summary of a finished structural/full run, `[SILENT]` when there is nothing to tell
- build_list_only_report: Markdown weekly health report of the read-only listing

[POS]
Pure functions from result data to delivery text, kept out of the runner so the orchestration reads as steps.
"""

from __future__ import annotations

from collections.abc import Sequence

from myrm_agent_harness.toolkits.wiki.core.types import LintIssue

from app.services.wiki.maintain.schemas import WikiMaintainRunResult

MAX_REPORTED_ISSUES = 200

_SILENT = "[SILENT]"


def lint_issue_payloads(issues: Sequence[LintIssue]) -> list[dict[str, object]]:
    return [
        {
            "issue_type": item.issue_type,
            "severity": item.severity,
            "location": item.location,
            "description": item.description,
            "action_kind": item.action_kind,
            "suggested_fix": item.suggested_fix,
        }
        for item in issues[:MAX_REPORTED_ISSUES]
    ]


def build_summary_text(result: WikiMaintainRunResult) -> str:
    """Silent unless the run changed something or never reached the model it needed."""
    changed = result.issues_fixed > 0 or result.connections_discovered > 0 or result.raw_security_removed > 0
    if not changed and not result.ai_unavailable:
        return _SILENT

    parts = [
        f"Wiki maintain ({result.mode}): {result.issues_found} issue(s)",
        f"{result.issues_fixed} fixed",
    ]
    if result.connections_discovered > 0:
        parts.append(f"{result.connections_discovered} new link(s)")
    if result.raw_security_removed > 0:
        parts.append(f"{result.raw_security_removed} raw file(s) removed")
    if result.ai_unavailable:
        parts.append("the AI model did not respond, so page review and link discovery were skipped")
    return ", ".join(parts)


def build_list_only_report(issues: Sequence[LintIssue]) -> str:
    if not issues:
        return (
            "## 📋 Wiki 知识库健康周检报告\n\n"
            "✅ **全库状态极佳**：未发现断链、陈旧事实或格式异常。\n\n"
            "— [在知识库治理面板中查看详情](/settings/wiki)"
        )

    broken_links = [i for i in issues if i.issue_type in ("broken_link", "broken_wikilink")]
    stale_files = [i for i in issues if i.issue_type == "stale"]
    invalid_types = [i for i in issues if i.issue_type == "invalid_frontmatter_type"]
    provenance_gaps = [i for i in issues if i.issue_type == "provenance_gap"]
    incomplete = [i for i in issues if i.issue_type == "incomplete"]
    other_issues = [
        i
        for i in issues
        if i.issue_type
        not in (
            "broken_link",
            "broken_wikilink",
            "stale",
            "invalid_frontmatter_type",
            "provenance_gap",
            "incomplete",
        )
    ]

    summary_counts: list[str] = []
    if broken_links:
        summary_counts.append(f"🔴 严重断链: {len(broken_links)} 处")
    if stale_files:
        summary_counts.append(f"🟡 事实陈旧: {len(stale_files)} 篇")
    if invalid_types:
        summary_counts.append(f"🟠 元数据异常: {len(invalid_types)} 篇")
    if provenance_gaps:
        summary_counts.append(f"⚪ 溯源缺失: {len(provenance_gaps)} 篇")
    if incomplete:
        summary_counts.append(f"⚪ 草稿/未完: {len(incomplete)} 篇")
    if other_issues:
        summary_counts.append(f"⚪ 其他项: {len(other_issues)} 篇")

    lines = [
        "## 📋 Wiki 知识库健康周检报告\n",
        f"**总计发现 {len(issues)} 项待优化项**（{' · '.join(summary_counts)}）\n",
        "### 重点关注清单（Top 10）",
    ]

    for item in issues[:10]:
        icon = "🔴" if item.severity == "high" else ("🟡" if item.severity == "medium" else "⚪")
        desc = item.description or item.issue_type
        lines.append(f"- {icon} `{item.location}`: {desc}")

    if len(issues) > 10:
        lines.append(f"\n*(其余 {len(issues) - 10} 项已收拢)*")

    lines.append("\n👉 [在知识库设置中查看全量诊断与治理](/settings/wiki)")
    return "\n".join(lines)
