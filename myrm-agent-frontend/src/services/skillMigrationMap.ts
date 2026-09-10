/**
 * [INPUT]
 * - WorkBuddy Top 20 常见高频技能与生态命名
 *
 * [OUTPUT]
 * - WB_TOP20_SKILL_MIGRATION_MAP: 官方 20 大核心技能迁移映射索引字典
 * - findMigratedSkill: 根据 WB 技能名或关键词快速检索对应 Myrm 原生技能
 * - WBSkillMigrationItem: 迁移契约类型定义
 *
 * [POS]
 * 技能生态无缝平移服务层。抹平竞品技能与 Myrm 生产级技能命名及架构差异，
 * 提供 1:1 映射索引、增强点说明与一键引导能力。
 */

export type MigrationMatchQuality = 'exact' | 'superset' | 'composite';

export interface WBSkillMigrationItem {
  /** WorkBuddy 原始技能标识或常见别名 */
  wbSkillId: string;
  /** WorkBuddy 原始技能中文名 */
  wbNameZh: string;
  /** WorkBuddy 原始技能英文名 */
  wbNameEn: string;
  /** WorkBuddy 核心使用场景 */
  wbScenario: string;
  /** Myrm 对应的标准原生技能 ID */
  myrmSkillId: string;
  /** 匹配质态: exact (完全对等), superset (Myrm 包含并大幅增强), composite (多技能联合) */
  matchQuality: MigrationMatchQuality;
  /** Myrm 相对优势或架构增强特性说明 */
  enhancementsZh: string;
  enhancementsEn: string;
}

/**
 * WorkBuddy 20 大核心高频技能官方平移映射表
 */
export const WB_TOP20_SKILL_MIGRATION_MAP: readonly WBSkillMigrationItem[] = [
  {
    wbSkillId: 'wb-meeting-minutes',
    wbNameZh: '会议纪要生成',
    wbNameEn: 'Meeting Minutes Summarizer',
    wbScenario: '会议录音录屏/速记文本整理、待办事项提炼与行动项拆解',
    myrmSkillId: 'voice-memo-synthesizer',
    matchQuality: 'superset',
    enhancementsZh: '具备四维结构化解构（纪要、看板任务、长期记忆、统计表格），幂等去重且支持自动写入看板',
    enhancementsEn: 'Provides 4D decomposition (minutes, kanban tasks, long-term memory, spreadsheets) with deduplication.',
  },
  {
    wbSkillId: 'wb-office-doc-helper',
    wbNameZh: 'Office 文档助手',
    wbNameEn: 'Office Document Generator',
    wbScenario: 'Word、Excel、PPT 商业交付物生成与格式排版',
    myrmSkillId: 'office-document',
    matchQuality: 'superset',
    enhancementsZh: '沙箱内高保真 python-docx / openpyxl / python-pptx 真实渲染，支持观点句门禁与反文字墙审查',
    enhancementsEn: 'In-sandbox high-fidelity docx/xlsx/pptx generation with thesis statement gate & anti-text-wall guards.',
  },
  {
    wbSkillId: 'wb-deep-web-research',
    wbNameZh: '深度联网研报',
    wbNameEn: 'Deep Web Research',
    wbScenario: '行业调研、竞品对比、多源交叉检验与万字长篇报告输出',
    myrmSkillId: 'deep-research',
    matchQuality: 'superset',
    enhancementsZh: '多轮递归搜索、信源权威度交叉验证、自动生成架构对比图与参考文献索引',
    enhancementsEn: 'Recursive multi-turn web search, authoritative source cross-validation, and structured report synthesis.',
  },
  {
    wbSkillId: 'wb-code-review-audit',
    wbNameZh: '代码审查与审计',
    wbNameEn: 'Code Review & Audit',
    wbScenario: '代码质量把控、潜在 Bug 挖掘、规范门禁与重构建议',
    myrmSkillId: 'code-review-pipeline',
    matchQuality: 'superset',
    enhancementsZh: '结合 AST 语法树与调用图拓扑分析，聚焦安全漏洞、内存泄漏与性能瓶颈',
    enhancementsEn: 'Integrates AST & repo call graph with automated security diff scan and performance bottleneck audits.',
  },
  {
    wbSkillId: 'wb-data-analysis-bi',
    wbNameZh: '数据分析与BI看板',
    wbNameEn: 'Data Analysis & Charts',
    wbScenario: 'CSV/Excel 数据统计、探索性数据分析(EDA)与可视化图表',
    myrmSkillId: 'data-analysis-pipeline',
    matchQuality: 'superset',
    enhancementsZh: '沙箱 Pandas/Matplotlib/Seaborn 物理执行，输出交互式图表与关键业务指标解读',
    enhancementsEn: 'Safe sandbox execution with Pandas/Matplotlib, producing interactive charts & quantified metrics.',
  },
  {
    wbSkillId: 'wb-pdf-report-builder',
    wbNameZh: 'PDF 报表排版生成',
    wbNameEn: 'PDF Report Builder',
    wbScenario: '合同、发票、项目报告与公文的规范分页 PDF 导出',
    myrmSkillId: 'pdf-generator',
    matchQuality: 'exact',
    enhancementsZh: '支持专业 CSS Paged Media 物理分页、页眉页脚页码动态插入与高分辨率矢量渲染',
    enhancementsEn: 'Supports CSS Paged Media pagination, dynamic running headers/footers, and vector rendering.',
  },
  {
    wbSkillId: 'wb-web-scraper',
    wbNameZh: '网页数据提取抓取',
    wbNameEn: 'Web Scraper & Crawler',
    wbScenario: '目标网站文本抓取、商品/资讯列表抽取与结构化存储',
    myrmSkillId: 'web-scraping',
    matchQuality: 'superset',
    enhancementsZh: '内置 Patchright 拟真浏览器沙箱与反爬对抗，支持复杂 SPA 页面动态渲染抓取',
    enhancementsEn: 'Uses browser automation with anti-detect stealth to scrape dynamic SPAs and structured tables.',
  },
  {
    wbSkillId: 'wb-daily-briefing',
    wbNameZh: '每日资讯早报',
    wbNameEn: 'Daily Briefing & News',
    wbScenario: '行业热点监控、早间新闻简报与多渠道聚合推送',
    myrmSkillId: 'daily-briefing',
    matchQuality: 'exact',
    enhancementsZh: '与 Cron 调度系统深度联动，支持自定义信源权重与微信/邮件排版直发',
    enhancementsEn: 'Integrates with CronJob scheduler, supporting custom source weighting and responsive digests.',
  },
  {
    wbSkillId: 'wb-debug-expert',
    wbNameZh: '程序故障系统级排查',
    wbNameEn: 'Systematic Debugging',
    wbScenario: '报错日志根因诊断、堆栈追踪与修复方案验证',
    myrmSkillId: 'systematic-debugging',
    matchQuality: 'superset',
    enhancementsZh: '严格遵循物理证据排查纪律，以最小可复现用例(MRE)驱动代码验证',
    enhancementsEn: 'Enforces evidence-based troubleshooting with minimal reproducible test case verification.',
  },
  {
    wbSkillId: 'wb-arch-diagram-flow',
    wbNameZh: '架构图与流程图设计',
    wbNameEn: 'Architecture Diagram Flow',
    wbScenario: '系统拓扑、微服务时序图与业务流程建模',
    myrmSkillId: 'architecture-diagram',
    matchQuality: 'exact',
    enhancementsZh: '支持 PlantUML / Mermaid / SVG 矢量实时渲染，配色契合现代深色与浅色双模设计规范',
    enhancementsEn: 'Generates crisp PlantUML/Mermaid/SVG diagrams honoring modern design systems & dual themes.',
  },
  {
    wbSkillId: 'wb-personal-life-board',
    wbNameZh: '生活看板与个人待办',
    wbNameEn: 'Personal Life Dashboard',
    wbScenario: '个人生活效率工作台、习惯打卡、番茄钟与日程规划',
    myrmSkillId: 'personal-life-workbench',
    matchQuality: 'superset',
    enhancementsZh: '提供 8 模块微应用自包含 HTML 工件，零外部依赖，数据持久化于 localStorage 且主题自适应',
    enhancementsEn: '8-module micro-app HTML artifact, zero CDN dependencies, local state persistence & dual-theme sync.',
  },
  {
    wbSkillId: 'wb-copywriting-humanizer',
    wbNameZh: '文案去AI感与润色',
    wbNameEn: 'Copywriting Humanizer',
    wbScenario: '消除机器生硬表达、语调本土化与专业行文润色',
    myrmSkillId: 'content-humanizer',
    matchQuality: 'exact',
    enhancementsZh: '多维词汇黑名单过滤、反说教句式重构与自然口语化韵律调校',
    enhancementsEn: 'Eliminates AI cliché terms, restructures preachy sentences, and tunes natural human rhythm.',
  },
  {
    wbSkillId: 'wb-persona-voice-clone',
    wbNameZh: '人物语气与人设塑造',
    wbNameEn: 'Persona Voice & Style',
    wbScenario: '特定名人或专家语言习惯拟合、对话风格一致性保持',
    myrmSkillId: 'persona-voice',
    matchQuality: 'superset',
    enhancementsZh: '支持语料蒸馏与 Conversational Skill Preset 资产自动打包，保留标点习惯与思维心智模型',
    enhancementsEn: 'Corpus distillation into conversational skill presets preserving mental models & lexical habits.',
  },
  {
    wbSkillId: 'wb-customer-email-audit',
    wbNameZh: '客户沟通草稿防翻车审核',
    wbNameEn: 'Customer Draft Review',
    wbScenario: '对外重要邮件、商务磋商与客户争议回复前的合规与礼仪审查',
    myrmSkillId: 'customer-relationship-draft-review',
    matchQuality: 'exact',
    enhancementsZh: '4 维红线合规雷达（过度承诺防御、商业机密保护、得体语调、明确闭环行动项）',
    enhancementsEn: '4-dimension compliance radar (promise containment, confidentiality, professional tone, actionable closure).',
  },
  {
    wbSkillId: 'wb-wechat-article-format',
    wbNameZh: '微信公众号排版排版器',
    wbNameEn: 'WeChat Article Formatter',
    wbScenario: 'Markdown 转换带内联样式的公众号精美 HTML',
    myrmSkillId: 'wechat-article-formatter',
    matchQuality: 'exact',
    enhancementsZh: '纯内联 CSS 计算，完美兼容微信编辑器粘贴，无样式丢失',
    enhancementsEn: 'Pure inline CSS calculation guaranteeing flawless copy-paste into WeChat official account editor.',
  },
  {
    wbSkillId: 'wb-server-ops-ssh',
    wbNameZh: '服务器运维与只读巡检',
    wbNameEn: 'Host Server Ops & Health',
    wbScenario: '主机 CPU/内存/磁盘排查、服务端口检测与系统健康度巡检',
    myrmSkillId: 'host-server-ops',
    matchQuality: 'superset',
    enhancementsZh: '严格防灾只读模式，支持与 Cron 定时巡检蓝图开箱即用无缝绑定',
    enhancementsEn: 'Safe read-only execution guardrails with 1-click binding to Cron health check blueprints.',
  },
  {
    wbSkillId: 'wb-brand-vi-designer',
    wbNameZh: '品牌VI与设计规范提取',
    wbNameEn: 'Brand VI Guidelines Extractor',
    wbScenario: '企业视觉标识提炼、调色板对比度检验与规范文件生成',
    myrmSkillId: 'brand-vi-synthesizer',
    matchQuality: 'superset',
    enhancementsZh: '支持导出机器可读的 tokens.css、tailwind.brand.js 与 tokens.json，直通驱动后续工件',
    enhancementsEn: 'Synthesizes machine-readable design tokens (tokens.css, tailwind tokens) to drive downstream artifacts.',
  },
  {
    wbSkillId: 'wb-tdd-test-craft',
    wbNameZh: '测试驱动开发与单测编写',
    wbNameEn: 'Test Driven Development',
    wbScenario: '编写自动化单元测试、提高代码覆盖率与回归防护',
    myrmSkillId: 'test-driven-development',
    matchQuality: 'exact',
    enhancementsZh: '遵循严格红-绿-重构循环，门禁断言物理执行证据，杜绝 Mock 偷工减料',
    enhancementsEn: 'Strict Red-Green-Refactor cycle with physical execution proof, rejecting superficial mock tricks.',
  },
  {
    wbSkillId: 'wb-evidence-case-pack',
    wbNameZh: '项目实战案例证据包',
    wbNameEn: 'Project Experience Evidence Pack',
    wbScenario: '沉淀高信度项目经验、故障复盘与可审计技术资产',
    myrmSkillId: 'project-experience-evidence-pack',
    matchQuality: 'exact',
    enhancementsZh: '标准 6 步证据链（原始诉求、v0 首稿、执行失败轨迹、修正依据、实测物理证据、不变量沉淀）',
    enhancementsEn: 'Standard 6-step evidence chain (demands, v0 draft, failed trace, fixes, physical proof, invariants).',
  },
  {
    wbSkillId: 'wb-ui-design-tailor',
    wbNameZh: '现代UI界面与交互设计',
    wbNameEn: 'Modern UI & Design Systems',
    wbScenario: '高质量前端组件、落地页设计与设计系统参考',
    myrmSkillId: 'popular-web-designs',
    matchQuality: 'superset',
    enhancementsZh: '内置 54 个一线大厂(Stripe, Linear, Notion, Vercel)完整像素级设计系统与 CSS Token 参考',
    enhancementsEn: 'Includes 54 real-world design systems (Linear, Stripe, Vercel) with pixel-accurate CSS tokens.',
  },
];

/**
 * 快速查找匹配的技能迁移条目
 * 支持通过 WB 技能 ID、中文名称、英文名或 Myrm 目标技能 ID 匹配
 */
export function findMigratedSkill(query: string): WBSkillMigrationItem | undefined {
  const q = query.trim().toLowerCase();
  if (!q) return undefined;

  return WB_TOP20_SKILL_MIGRATION_MAP.find(
    (item) =>
      item.wbSkillId.toLowerCase() === q ||
      item.myrmSkillId.toLowerCase() === q ||
      item.wbNameZh.toLowerCase().includes(q) ||
      item.wbNameEn.toLowerCase().includes(q) ||
      item.wbScenario.toLowerCase().includes(q),
  );
}
