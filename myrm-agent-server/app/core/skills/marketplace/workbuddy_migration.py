"""WorkBuddy Top 20 Essential Skills to Myrm Native Skills Migration Mapping.

[OUTPUT]
- WORKBUDDY_TOP_20_MIGRATION_MAP: SSOT dictionary mapping WB skills to Myrm prebuilt equivalents.
- resolve_workbuddy_migration_target(wb_skill_id: str) -> dict | None: Resolves migration details.

[POS]
Provides seamless 1:1 migration and adoption paths for users and teams transitioning from WorkBuddy.
"""

from __future__ import annotations

from typing import Final, TypedDict


class MigrationTarget(TypedDict):
    wb_id: str
    wb_name: str
    myrm_skill_id: str
    category: str
    rationale: str


WORKBUDDY_TOP_20_MIGRATION_MAP: Final[dict[str, MigrationTarget]] = {
    "wb_host_ops": {
        "wb_id": "wb_host_ops",
        "wb_name": "主机监控与巡检",
        "myrm_skill_id": "host-server-ops",
        "category": "engineering",
        "rationale": "Directly maps to Myrm's read-only, non-destructive host health inspection skill.",
    },
    "wb_office_doc": {
        "wb_id": "wb_office_doc",
        "wb_name": "Office 办公三件套",
        "myrm_skill_id": "office-document",
        "category": "productivity",
        "rationale": "Maps to Myrm's native openpyxl/python-docx/python-pptx document engineering suite.",
    },
    "wb_personal_dashboard": {
        "wb_id": "wb_personal_dashboard",
        "wb_name": "个人看板工作台",
        "myrm_skill_id": "personal-life-workbench",
        "category": "productivity",
        "rationale": "Maps to Myrm's 8-module theme-adaptive, localStorage persistent HTML workbench.",
    },
    "wb_crm_audit": {
        "wb_id": "wb_crm_audit",
        "wb_name": "客户沟通审核门禁",
        "myrm_skill_id": "customer-relationship-draft-review",
        "category": "business",
        "rationale": "Maps to Myrm's 4-dimensional sensitive communication compliance radar.",
    },
    "wb_evidence_pack": {
        "wb_id": "wb_evidence_pack",
        "wb_name": "六步证据复盘",
        "myrm_skill_id": "project-experience-evidence-pack",
        "category": "engineering",
        "rationale": "Maps to Myrm's verifiable 6-step project case study crystallization skill.",
    },
    "wb_brand_vi": {
        "wb_id": "wb_brand_vi",
        "wb_name": "品牌视觉规范抽取",
        "myrm_skill_id": "brand-vi-guidelines",
        "category": "design",
        "rationale": "Maps to Myrm's 5-pillar design token synthesis and presentation constraint pack.",
    },
    "wb_data_analysis": {
        "wb_id": "wb_data_analysis",
        "wb_name": "数据分析与流水线",
        "myrm_skill_id": "data-analysis-pipeline",
        "category": "analytics",
        "rationale": "Maps to Myrm's automated pandas/numpy/matplotlib data analysis pipeline.",
    },
    "wb_deep_research": {
        "wb_id": "wb_deep_research",
        "wb_name": "深度行业调研",
        "myrm_skill_id": "deep-research",
        "category": "research",
        "rationale": "Maps to Myrm's multi-hop citation-backed web research engine.",
    },
    "wb_pdf_generator": {
        "wb_id": "wb_pdf_generator",
        "wb_name": "专业 PDF 生成",
        "myrm_skill_id": "pdf-generator",
        "category": "productivity",
        "rationale": "Maps to Myrm's deterministic reportlab/typst PDF generator skill.",
    },
    "wb_web_scraping": {
        "wb_id": "wb_web_scraping",
        "wb_name": "网页智能采集",
        "myrm_skill_id": "web-scraping",
        "category": "data",
        "rationale": "Maps to Myrm's playwright/patchright headless scraping toolchain.",
    },
    "wb_db_diagnostics": {
        "wb_id": "wb_db_diagnostics",
        "wb_name": "数据库慢查询诊断",
        "myrm_skill_id": "db-diagnostics",
        "category": "engineering",
        "rationale": "Maps to Myrm's read-only SQL profiling and index advisor skill.",
    },
    "wb_frontend_dev": {
        "wb_id": "wb_frontend_dev",
        "wb_name": "前端交互开发",
        "myrm_skill_id": "frontend-development",
        "category": "engineering",
        "rationale": "Maps to Myrm's React/Next.js/Tailwind modern web development skill.",
    },
    "wb_code_review": {
        "wb_id": "wb_code_review",
        "wb_name": "工程代码评审",
        "myrm_skill_id": "code-review-pipeline",
        "category": "engineering",
        "rationale": "Maps to Myrm's automated git diff security and quality gate.",
    },
    "wb_github_workflow": {
        "wb_id": "wb_github_workflow",
        "wb_name": "GitHub CI 流水线",
        "myrm_skill_id": "github-workflow",
        "category": "devops",
        "rationale": "Maps to Myrm's GitHub Actions automation skill.",
    },
    "wb_daily_briefing": {
        "wb_id": "wb_daily_briefing",
        "wb_name": "晨间与行业简报",
        "myrm_skill_id": "daily-briefing",
        "category": "productivity",
        "rationale": "Maps to Myrm's multi-source daily summary crystallization skill.",
    },
    "wb_read_it_later": {
        "wb_id": "wb_read_it_later",
        "wb_name": "稍后读知识库提取",
        "myrm_skill_id": "read-it-later",
        "category": "knowledge",
        "rationale": "Maps to Myrm's web article clipping and LLM wiki crystallization skill.",
    },
    "wb_infographic": {
        "wb_id": "wb_infographic",
        "wb_name": "信息图表生成",
        "myrm_skill_id": "infographic",
        "category": "design",
        "rationale": "Maps to Myrm's SVG/HTML high-contrast visual diagram skill.",
    },
    "wb_wechat_formatter": {
        "wb_id": "wb_wechat_formatter",
        "wb_name": "公众号排版美化",
        "myrm_skill_id": "wechat-article-formatter",
        "category": "creative",
        "rationale": "Maps to Myrm's inline-CSS WeChat public article formatting engine.",
    },
    "wb_browser_automation": {
        "wb_id": "wb_browser_automation",
        "wb_name": "浏览器自动化操作",
        "myrm_skill_id": "browser-automation",
        "category": "automation",
        "rationale": "Maps to Myrm's patchright computer-use browser automation suite.",
    },
    "wb_seo_optimization": {
        "wb_id": "wb_seo_optimization",
        "wb_name": "网站 SEO 优化",
        "myrm_skill_id": "web-project-seo-optimization",
        "category": "marketing",
        "rationale": "Maps to Myrm's semantic tags, meta-header, and sitemap auditing skill.",
    },
}


def resolve_workbuddy_migration_target(wb_skill_id: str) -> MigrationTarget | None:
    """Resolve WorkBuddy skill ID to Myrm migration target specification."""
    return WORKBUDDY_TOP_20_MIGRATION_MAP.get(wb_skill_id.strip().lower())
