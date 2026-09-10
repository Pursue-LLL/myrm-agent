"""WorkBuddy Top 20 essential skills migration mapping.

Provides a canonical mapping from WorkBuddy high-frequency skill names/categories
to Myrm prebuilt skills, ensuring zero migration friction for enterprise users.
"""

from __future__ import annotations

from typing import Final
from pydantic import BaseModel, Field

class WorkBuddySkillMappingItem(BaseModel):
    wb_skill_name: str = Field(..., description="Original WorkBuddy skill name / identifier")
    wb_category: str = Field(..., description="WorkBuddy capability category")
    myrm_skill_id: str = Field(..., description="Corresponding Myrm prebuilt skill ID")
    description_zh: str = Field(..., description="Capability description in Chinese")
    recommended_tools: list[str] = Field(default_factory=list, description="Primary tools utilized")
    priority: str = Field("P1", description="Migration priority")


WORKBUDDY_TOP_20_ESSENTIAL_SKILLS_MAP: Final[list[WorkBuddySkillMappingItem]] = [
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-office-document",
        wb_category="Office & Productivity",
        myrm_skill_id="office-document",
        description_zh="商业公文、PPT 幻灯片与专业排版排查",
        recommended_tools=["bash_code_execute_tool", "file_write_tool"],
        priority="P0",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-deep-research",
        wb_category="Research & Intelligence",
        myrm_skill_id="deep-research",
        description_zh="全网多源行业调研与深度课题研究分析",
        recommended_tools=["web_search", "browser_navigate_tool", "file_write_tool"],
        priority="P0",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-competitive-analysis",
        wb_category="Market Intelligence",
        myrm_skill_id="competitive-analysis-pipeline",
        description_zh="竞品功能拆解、差异化对比与策略分析流水线",
        recommended_tools=["web_search", "file_write_tool"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-data-analysis",
        wb_category="Data & Analytics",
        myrm_skill_id="data-analysis-pipeline",
        description_zh="多源异构数据清洗、统计分析与图表生成",
        recommended_tools=["bash_code_execute_tool", "file_read_tool"],
        priority="P0",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-wechat-article-formatter",
        wb_category="Marketing & Content",
        myrm_skill_id="wechat-article-formatter",
        description_zh="微信公众号爆款排版与精美富文本渲染",
        recommended_tools=["file_write_tool", "file_read_tool"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-architecture-diagram",
        wb_category="Engineering & Architecture",
        myrm_skill_id="architecture-diagram",
        description_zh="C4/UML/网络拓扑架构图与流程图自动化生成",
        recommended_tools=["file_write_tool", "bash_code_execute_tool"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-code-review",
        wb_category="Engineering & Quality",
        myrm_skill_id="code-review-pipeline",
        description_zh="多文件 Git Diff 自动化审查与代码质量红线拦截",
        recommended_tools=["file_read_tool", "bash_code_execute_tool"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-web-scraping",
        wb_category="Data & Crawling",
        myrm_skill_id="web-scraping",
        description_zh="网页结构化数据抓取与抗反爬文本提取",
        recommended_tools=["browser_navigate_tool", "file_write_tool"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-browser-automation",
        wb_category="Automation & RPA",
        myrm_skill_id="browser-automation",
        description_zh="沙箱无头浏览器表单填报与多步 RPA 交互",
        recommended_tools=["browser_navigate_tool", "bash_code_execute_tool"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-pdf-generator",
        wb_category="Office & Productivity",
        myrm_skill_id="pdf-generator",
        description_zh="企业级矢量 PDF 报告与合同凭据排版渲染",
        recommended_tools=["bash_code_execute_tool", "file_write_tool"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-db-diagnostics",
        wb_category="Operations & Infra",
        myrm_skill_id="db-diagnostics",
        description_zh="数据库慢查询分析、连接池优化与索引诊断",
        recommended_tools=["bash_code_execute_tool", "file_read_tool"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-test-driven-development",
        wb_category="Engineering & Quality",
        myrm_skill_id="test-driven-development",
        description_zh="红绿重构严格 TDD 闭环与自动化测试覆盖",
        recommended_tools=["file_write_tool", "bash_code_execute_tool"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-brand-vi-guidelines",
        wb_category="Design & VI",
        myrm_skill_id="brand-vi-guidelines",
        description_zh="企业品牌视觉设计系统与规范设计 Token",
        recommended_tools=["file_write_tool", "file_read_tool"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-personal-life-workbench",
        wb_category="Productivity & Life",
        myrm_skill_id="personal-life-workbench",
        description_zh="8 模块个人工作台与生活自适应离线看板",
        recommended_tools=["file_write_tool", "file_read_tool"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-voice-memo-synthesizer",
        wb_category="Collaboration & Audio",
        myrm_skill_id="voice-memo-synthesizer",
        description_zh="会议录音转写纪要、待办分解与四维提炼",
        recommended_tools=["file_write_tool", "file_read_tool"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-content-distribution",
        wb_category="Marketing & Social",
        myrm_skill_id="content-distribution-pipeline",
        description_zh="跨平台多渠道内容分发与社交发布流水线",
        recommended_tools=["file_write_tool", "web_search"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-host-server-ops",
        wb_category="Operations & Infra",
        myrm_skill_id="host-server-ops",
        description_zh="远端服务器健康巡检与主机运维安全检查",
        recommended_tools=["bash_code_execute_tool", "file_read_tool"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-enterprise-branded-office",
        wb_category="Enterprise & Office",
        myrm_skill_id="enterprise-branded-office",
        description_zh="企业专属品牌 Office 模板母版与同事零配置交接",
        recommended_tools=["file_write_tool", "bash_code_execute_tool"],
        priority="P1",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-customer-relationship-draft-review",
        wb_category="Sales & CRM",
        myrm_skill_id="customer-relationship-draft-review",
        description_zh="对外商务邮件与客户沟通草稿合规安全审查",
        recommended_tools=["file_read_tool", "file_edit_tool"],
        priority="P0",
    ),
    WorkBuddySkillMappingItem(
        wb_skill_name="wb-project-experience-evidence-pack",
        wb_category="Engineering & Portfolio",
        myrm_skill_id="project-experience-evidence-pack",
        description_zh="项目实战交付全流程六步证据链与履历证明包",
        recommended_tools=["file_write_tool", "file_read_tool"],
        priority="P1",
    ),
]
