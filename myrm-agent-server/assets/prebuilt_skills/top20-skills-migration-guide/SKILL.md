---
name: top20-skills-migration-guide
description: >-
  WorkBuddy Top 20 essential workplace & developer skills to Myrm native prebuilt
  skills 1:1 authoritative migration mapping guide. Explains feature parity, architectural
  enhancements, and zero-configuration adoption strategies.
version: 1.0.0
category: productivity
tags:
  - migration
  - workbuddy
  - guide
  - prebuilt-skills
  - top20
  - 迁移指南
  - 技能映射
  - 核心技能
allowed-tools: file_read_tool
contract:
  steps:
    - 1. Identify source WorkBuddy skill or workflow category
    - 2. Map to corresponding Myrm native prebuilt skill
    - 3. Check for architectural advantages (sandbox security, WYSIWYG, zero external CDN)
    - 4. Provide turnkey prompt and activation guidance
  potential_traps:
    - description: Confusing framework-level tools with user-level skills
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Expecting external CDN dependencies inside sandboxed HTML artifacts
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
  verification_steps:
    - Verify target skill exists in assets/prebuilt_skills/
    - Confirm permissions and allowed tools align with security presets
  success_criteria:
    - Complete 1:1 mapping for all 20 essential workplace workflows
---

# WorkBuddy Top 20 必备高频技能迁移与 Myrm 官方映射指南

针对从 WorkBuddy 等平台迁移至 Myrm 的个人与企业用户，本指南提供 20 大核心工作流技能的权威 1:1 映射速查表，并说明 Myrm 在架构与安全性上的代际增强。

## 20 大核心技能映射速查表

| # | WorkBuddy 常见技能 | Myrm 原生 Prebuilt Skill | Myrm 核心代际增强与架构亮点 |
|---|---|---|---|
| 1 | 会议纪要与录音整理 | `voice-memo-synthesizer` | 四维降解：纪要/看板任务/长期记忆/表格四位一体，幂等去重 |
| 2 | 办公文档处理 (Word/Excel/PPT) | `office-document` | python-pptx 16:9 商业幻灯片生成、openpyxl 公式防丢守卫、反文字墙门禁 |
| 3 | 深度互联网研究 | `deep-research` | 多源交叉比对、学术与行业信源深度检索、结构化调研报告生成 |
| 4 | 网页数据采集与表格抓取 | `web-scraping` | 双哨兵防死循环、Cloudflare/SPA 自动切轨无头浏览器、内嵌避坑经验库 |
| 5 | 数据科学与统计看板 | `data-analysis-pipeline` | 沙箱内完整 Python 数据分析管线、自动清洗、多维度聚合与专业图表渲染 |
| 6 | 代码审查与架构重构 | `code-review-pipeline` | 静态语法分析、安全漏洞扫描、架构分层防违约检查、重构建议矩阵 |
| 7 | 架构图表与系统设计 | `architecture-diagram` | Mermaid/PlantUML 动态生成、高内聚低耦合分层架构验证、SVG 矢量图导出 |
| 8 | 个人生活与效率工作台 | `personal-life-workbench` | 8 模块自包含微应用、主题 CSS 变量自适应、零外部 CDN、localStorage 状态持久化 |
| 9 | 个人语气与声音拟真 | `persona-voice` | 五维语料蒸馏矩阵、去 AI 塑料感、支持一键打包封装为独立数字人技能 |
| 10 | PDF 文档智能提取 | `document-extraction` / `pdf-generator` | 结构化版面分析、双栏/表格精准还原、ReportLab/Playwright 高保真 PDF 导出 |
| 11 | 主机与服务器健康诊断 | `host-server-ops` | 纯只读系统指标采集、CPU/内存/磁盘/网络异常诊断、无害化排查建议 |
| 12 | 数据库性能诊断 | `db-diagnostics` | 慢查询慢 SQL 分析、索引缺失建议、连接池耗尽预警、只读事务保护 |
| 13 | 前端组件与交互开发 | `frontend-development` | React/Next.js/Tailwind 最佳实践、无障碍标准、响应式流式布局 |
| 14 | 社交媒体舆情监测 | `social-media-monitoring` | 多平台热点追踪、情感极性判定、突发公关风险识别与摘要预警 |
| 15 | 每日工作简报生成 | `daily-briefing` | 日常任务/动态自动汇聚、优先级红绿灯标记、轻量 Markdown/HTML 简报 |
| 16 | 客户关系与敏感草稿审查 | `customer-relationship-draft-review` | 四维红线合规雷达：法务违约/商业泄密/礼仪语调/确定性闭环防护 |
| 17 | 品牌 VI 规范提炼 | `brand-vi-guidelines` | 提取 5 大视觉基石、导出机器可读 `brand-vi.yaml`、下游产物统一消费 |
| 18 | GitHub 工作流协同 | `github-workflow` | Issue/PR 自动化流转、CI 失败分析、语义化 Commit 规范与 Release 整理 |
| 19 | 企业品牌 Office 模板交接 | `enterprise-branded-office` | 16:9 母版底纹、统一三级标题公文与对账表头、同事免配置交接 |
| 20 | 技能经验库自免疫闭环 | `evidence-discipline` | 读在前写在后、踩坑原子沉淀、防复发门禁、让技能随调用持续变强 |
