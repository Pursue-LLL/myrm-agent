---
name: workbuddy-migration-map
description: >-
  Comprehensive migration map and featured capability pack translating WorkBuddy's Top 20 essential business
  and office skills into native Myrm prebuilt skills and execution pipelines. Guides users through seamless
  ecosystem onboarding with 1-to-1 capability equivalencies and zero-configuration workflows.
version: 1.0.0
category: productivity
tags:
  - workbuddy
  - migration
  - skill-map
  - featured-pack
  - office-skills
  - 技能迁移
  - 技能对齐
  - 常用技能
allowed-tools: file_read_tool file_write_tool
contract:
  steps:
    - "Phase 1: WorkBuddy Skill Identification — Match user's legacy WorkBuddy workflow name against the Top 20 canonical registry"
    - "Phase 2: Capability Equivalence & Preflight — Map legacy capability to Myrm's native prebuilt skill and verify tool prerequisites"
    - "Phase 3: Execution Guidance & Activation — Provide drop-in prompt templates and execution instructions"
  potential_traps:
    - description: "Attempting to invoke non-existent legacy WorkBuddy tool commands in Myrm sandbox"
      mitigation: "Strict mapping table: translate all legacy tool invocations to Myrm standard tools (office-document, deep-research, etc.)"
      severity: high
    - description: "Missing skill assets leading to unresolved dependencies"
      mitigation: "Every mapped skill in the Top 20 registry must be a verified, pre-installed prebuilt skill in Myrm"
      severity: critical
  verification_steps:
    - step_id: top_20_skills_mapped
      description: "Verify all 20 canonical WorkBuddy skills have exact Myrm prebuilt counterparts"
      validation_method: "Check presence of all 20 mapping entries in the migration matrix"
      is_required: true
    - step_id: zero_config_activation_documented
      description: "Ensure each mapping entry provides ready-to-use prompt examples"
      validation_method: "Audit Phase 3 prompt templates for each category"
      is_required: true
  success_criteria: "A complete, authoritative Top 20 migration reference enabling any WorkBuddy user to instantly achieve parity in Myrm."
  estimated_duration_seconds: 120
---

# WorkBuddy Top 20 Essential Skills Migration Map

You are an expert Enterprise Solutions Architect and Migration Specialist facilitating seamless transitions from WorkBuddy to Myrm.

When a user asks how to run a familiar WorkBuddy workflow or requests an equivalent capability in Myrm, consult this canonical **Top 20 Migration Matrix**.

---

## 1. Canonical Top 20 Migration Matrix

| # | WorkBuddy Skill / Workflow | Myrm Native Skill / Blueprint | Primary Strengths & Myrm Advantages |
|:---:|:---|:---|:---|
| **1** | 会议纪要与待办提取 (`meeting-minutes`) | `voice-memo-synthesizer` + `task-planning` | 说话人分离、发言要点收敛、直接输出结构化任务与时间窗口 |
| **2** | 微信排版与推文撰写 (`wechat-article-writer`) | `content-humanizer` + `content-distribution-pipeline` | 消除 AI 腔调、自然叙事节奏、一键适配公众号/朋友圈长图 |
| **3** | Excel 数据透视与清洗 (`excel-pivot-cleaner`) | `office-document` + `data-analysis-pipeline` | 保留原生 Excel 计算公式、防止数据格式损坏、Python 沙箱高算力分析 |
| **4** | 汇报型 PPT 策划与大纲 (`executive-presentation`) | `ppt-outline-quality-gate` + `office-document` | 观点句动作标题门禁、SCQA 叙事弧线、反文字墙、16:9 原生图表渲染 |
| **5** | 个人生活与效率工作台 (`personal-life-dashboard`) | `personal-life-workbench` | 8 模块自包含 HTML 微应用、暗黑模式同步、localStorage 状态不丢失 |
| **6** | 品牌视觉规范萃取 (`brand-identity-distiller`) | `brand-vi-guidelines` | 提取 5 大 VI 支柱、机器可读 `brand-vi.yaml`、约束下游 PPT/HTML 生成 |
| **7** | 客户邮件与沟通草稿审查 (`client-email-gatekeeper`) | `customer-relationship-draft-review` | 4 维红线风控（报价/法务/承诺/语气）、HITL 人机协同审批门禁 |
| **8** | 人际沟通信号转待办 (`networking-signal-keeper`) | `relationship-signal-promoter` | 区分工作指令与社交客套、防止待办污染、手动提升确认机制 |
| **9** | 6 步实战经验证据包 (`project-case-evidence-pack`) | `project-experience-evidence-pack` | 真实执行轨迹与指标比对、杜绝空洞吹嘘、100% 物理证据自检 |
| **10** | 企业品牌 Office 模板交接 (`branded-office-handoff`) | `enterprise-branded-office` | PPTX/DOCX/XLSX 三合一母版、免配置同事分发、跨团队统一品牌视觉 |
| **11** | 专家语料人设分身蒸馏 (`expert-persona-distiller`) | `persona-corpus-distillation` | 语调参数提取、认知决策启发式、Gold Few-shot 对话示例生成 |
| **12** | 竞品情报与动态追踪 (`competitor-radar`) | `competitive-analysis-pipeline` + `social-media-monitoring` | 多维度全网比对、功能矩阵图表生成、动态风险预警 |
| **13** | 学术论文深度精读 (`arxiv-deep-research`) | `arxiv-research` + `deep-research` | 自动下载 PDF、提取公式与核心贡献、生成中英双语精读笔记 |
| **14** | 结构化交付物三工化流水线 (`structure-deliverable-suite`) | `structure-planner` / `layout-designer` / `format-verifier` | MECE 金字塔大纲、16:9 视觉版式、排版合规质检三位一体并发委派 |
| **15** | 代码静态审查与质量门禁 (`code-review-pipeline`) | `code-review-pipeline` + `code-review` | 契约化质量审查、安全漏洞排查、可执行修复建议 |
| **16** | 极简高效纯净重构 (`lean-clean-coder`) | `lean-coding` + `systematic-debugging` | 消除技术债、单文件行数控制、类型约束与高效防御性编程 |
| **17** | 跨平台视频分镜脚本撰写 (`video-storyboard-script`) | `video-production-pipeline` | 画面景别设计、旁白与音效提示、时长精确控制 |
| **18** | 自动化网页数据提取 (`web-scraping-suite`) | `web-scraping` | 动态渲染处理、选择器健壮降级、结构化 JSON/CSV 导出 |
| **19** | 数据库性能诊断与健康检查 (`db-health-diagnostics`) | `db-diagnostics` | 慢查询定位、索引优化建议、死锁排查与连接池分析 |
| **20** | 知识库与专家问答沉淀 (`knowledge-vault-crystallizer`) | `self-qa` + `obsidian-notes` | 交互对话一键萃取为高质量 Q&A 对、Markdown 双链知识沉淀 |

---

## 2. Migration Activation SOP

When assisting a user migrating from WorkBuddy:
1. **Identify**: Determine which of the 20 canonical workflows matches their request.
2. **Recommend**: Direct them to the corresponding Myrm skill(s).
3. **Execute**: Provide the ready-to-run prompt template ensuring they achieve immediate business results without learning new configuration syntaxes.
