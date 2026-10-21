"""Four standard markdown templates seeded into concepts/templates/.

[INPUT]
- myrm_agent_harness.toolkits.wiki::WikiStructure (POS: templates_dir SSOT)

[OUTPUT]
- STANDARD_TEMPLATE_NAMES / standard_templates(): four bilingual template definitions
- seed_standard_templates(): idempotent vault seeding guarded by a marker file

[POS]
The four standard templates (Daily Review / Project / Knowledge / Method) mirror the
four-dimension knowledge system. Seeding is idempotent per template file; a marker file
prevents startup seeding from resurrecting templates the user deliberately deleted,
while POST /wiki/templates/seed re-seeds on explicit demand.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.wiki import WikiStructure

logger = logging.getLogger(__name__)

_TEMPLATE_MARKER = ".standard-templates-seeded"

STANDARD_TEMPLATE_NAMES: tuple[str, ...] = (
    "Daily Review Template",
    "Project Template",
    "Knowledge Note Template",
    "Method Template",
)


def _template_body(sections: tuple[tuple[str, str], ...]) -> str:
    lines = []
    for heading, hint in sections:
        lines.append(f"## {heading}")
        lines.append(hint)
        lines.append("")
    return "\n".join(lines)


def standard_templates() -> dict[str, str]:
    """Four standard templates: bilingual frontmatter description + structured sections."""
    return {
        "Daily Review Template": (
            "---\n"
            "type: template\n"
            'title: "每日复盘模板 / Daily Review Template"\n'
            'description: "Record what happened, what was decided, and what to reuse tomorrow."\n'
            "tags:\n"
            "  - template\n"
            "  - daily-review\n"
            "---\n"
            + _template_body(
                (
                    ("今日进展 / Progress", "- 交付了什么、推进到哪里（量化优先）\n"),
                    ("关键决策 / Decisions", "- 决策 + 依据 + 备选被拒原因\n"),
                    ("教训与方法 / Lessons", "- 可复用的做法、踩过的坑、下次怎么做得更快\n"),
                    ("对比与权衡 / Trade-offs", "- 今天做过什么选型对比、结论是什么\n"),
                    ("明日计划 / Tomorrow", "- 最多三件事，按优先级排列\n"),
                )
            )
        ),
        "Project Template": (
            "---\n"
            "type: template\n"
            'title: "项目模板 / Project Template"\n'
            'description: "One page per project: goal, scope, milestones, and current state."\n'
            "tags:\n"
            "  - template\n"
            "  - project\n"
            "---\n"
            + _template_body(
                (
                    ("目标 / Goal", "- 一句话说清这个项目为什么存在\n"),
                    ("范围 / Scope", "- 做什么、明确不做什么\n"),
                    ("里程碑 / Milestones", "- 日期 + 可验收的交付物\n"),
                    ("当前状态 / Status", "- 最新进展与阻塞项\n"),
                    ("风险 / Risks", "- 风险 + 触发条件 + 缓解措施\n"),
                )
            )
        ),
        "Knowledge Note Template": (
            "---\n"
            "type: template\n"
            'title: "知识笔记模板 / Knowledge Note Template"\n'
            'description: "Capture a domain fact: definition, key points, and evidence sources."\n'
            "tags:\n"
            "  - template\n"
            "  - knowledge\n"
            "---\n"
            + _template_body(
                (
                    ("定义 / Definition", "- 用自己的话定义，一句话说清\n"),
                    ("要点 / Key Points", "- 分点展开，保留数字、日期、专名原文\n"),
                    ("证据来源 / Evidence", "- 原始出处（文件/链接/页码）\n"),
                    ("关联 / Related", "- [[相关概念]] 双链\n"),
                )
            )
        ),
        "Method Template": (
            "---\n"
            "type: template\n"
            'title: "方法模板 / Method Template"\n'
            'description: "A reusable procedure: when to use, steps, and known pitfalls."\n'
            "tags:\n"
            "  - template\n"
            "  - method\n"
            "---\n"
            + _template_body(
                (
                    ("适用场景 / When to Use", "- 什么情况下用这个方法\n"),
                    ("前置条件 / Prerequisites", "- 需要什么准备\n"),
                    ("步骤 / Steps", "- 可执行的操作序列\n"),
                    ("已知坑 / Pitfalls", "- 常见错误与规避方式\n"),
                )
            )
        ),
    }


def seed_standard_templates(
    structure: WikiStructure,
    *,
    force: bool = False,
) -> tuple[str, ...]:
    """Idempotently seed missing standard templates; return the written template names.

    Startup seeding stops permanently once the marker file exists (the user may have
    deliberately deleted templates); ``force=True`` re-seeds every template explicitly.
    """
    templates_dir = structure.templates_dir
    templates_dir.mkdir(parents=True, exist_ok=True)
    marker = templates_dir / _TEMPLATE_MARKER

    if not force and marker.exists():
        return ()

    written: list[str] = []
    for name, content in standard_templates().items():
        target = templates_dir / f"{name}.md"
        if force or not target.exists():
            target.write_text(content, encoding="utf-8")
            written.append(name)

    if not marker.exists():
        marker.write_text("v1\n", encoding="utf-8")
    if written:
        logger.info("Seeded standard templates into %s: %s", templates_dir, ", ".join(written))
    return tuple(written)


__all__ = ["STANDARD_TEMPLATE_NAMES", "seed_standard_templates", "standard_templates"]
