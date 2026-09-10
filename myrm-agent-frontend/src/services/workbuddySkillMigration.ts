/**
 * [INPUT]
 * - Prebuilt skill definitions across Myrm ecosystem
 * - WorkBuddy legacy skill identifiers & common user terminology
 *
 * [OUTPUT]
 * - WorkbuddySkillMappingItem: 迁移映射项契约
 * - WORKBUDDY_TOP_20_MIGRATION_MAP: Top 20 官方技能对齐地图 SSOT
 * - resolveMyrmSkillFromWorkbuddy: 根据 WorkBuddy ID/关键词反查 Myrm 技能
 * - searchWorkbuddyMigrationSkills: 跨生态技能模糊匹配检索
 *
 * [POS]
 * 技能生态平滑迁移层。帮助原 WorkBuddy 用户、企业和团队零认知成本对齐 Myrm 技能库。
 */

export interface WorkbuddySkillMappingItem {
  id: string;
  wbNameZh: string;
  wbNameEn: string;
  category: 'office' | 'engineering' | 'growth' | 'operations';
  myrmSkillId: string;
  myrmSkillNameZh: string;
  myrmSkillNameEn: string;
  descriptionZh: string;
  descriptionEn: string;
  recommendedPromptZh: string;
  recommendedPromptEn: string;
}

export const WORKBUDDY_TOP_20_MIGRATION_MAP: readonly WorkbuddySkillMappingItem[] = [
  {
    id: 'wb-weekly-report',
    wbNameZh: '周报生成器',
    wbNameEn: 'Weekly Report Generator',
    category: 'office',
    myrmSkillId: 'daily-briefing',
    myrmSkillNameZh: '每日简报与周期复盘',
    myrmSkillNameEn: 'Daily Briefing & Weekly Review',
    descriptionZh: '汇聚本周任务动态与多源记录，自动化生成结构化工作周报。',
    descriptionEn: 'Aggregates weekly task updates and generates structured executive reports.',
    recommendedPromptZh: '请基于我本周的执行轨迹与任务清单，生成一份条理清晰的周报。',
    recommendedPromptEn: 'Please generate a structured weekly report based on my tasks and activity log.',
  },
  {
    id: 'wb-office-sheets',
    wbNameZh: '办公文档与报表专家',
    wbNameEn: 'Office Document & Spreadsheet Pro',
    category: 'office',
    myrmSkillId: 'office-document',
    myrmSkillNameZh: 'Office 格式化办公文档',
    myrmSkillNameEn: 'Office Document Formatter & Generator',
    descriptionZh: '支持专业 Word、Excel 报表与商业表格的创建与格式化。',
    descriptionEn: 'Create and format professional Word documents and Excel spreadsheets.',
    recommendedPromptZh: '请制作一份包含收支明细和可视化排版的财务报表 Excel。',
    recommendedPromptEn: 'Please create an Excel spreadsheet with income/expense breakdown and clear formatting.',
  },
  {
    id: 'wb-commercial-slides',
    wbNameZh: '商务汇报 PPT 生成器',
    wbNameEn: 'Business Slides Generator',
    category: 'office',
    myrmSkillId: 'office-document',
    myrmSkillNameZh: '商业演示与幻灯片',
    myrmSkillNameEn: 'Commercial Slides & Presentation',
    descriptionZh: '生成 16:9 商业演示文稿，严格遵循观点句导向与反文字墙原则。',
    descriptionEn: 'Generates 16:9 business slide decks adhering to headline-lead standards.',
    recommendedPromptZh: '请生成一份 16:9 格式的季度业务汇报 PPT 演示大纲与内容。',
    recommendedPromptEn: 'Please generate a 16:9 quarterly business presentation outline and deck.',
  },
  {
    id: 'wb-deep-research',
    wbNameZh: '全网深度研报调研',
    wbNameEn: 'Deep Web Research Pro',
    category: 'growth',
    myrmSkillId: 'deep-research',
    myrmSkillNameZh: '深度行业研究与文献分析',
    myrmSkillNameEn: 'Deep Industry & Academic Research',
    descriptionZh: '多跳网络事实核查、竞品技术剖析与深度调研报告沉淀。',
    descriptionEn: 'Multi-hop web fact-checking and in-depth research report synthesis.',
    recommendedPromptZh: '请对 2026 年最新大模型端侧推理生态展开深度调研并输出报告。',
    recommendedPromptEn: 'Please conduct deep research on the edge LLM inference ecosystem in 2026.',
  },
  {
    id: 'wb-web-crawler',
    wbNameZh: '智能网页数据采集器',
    wbNameEn: 'Smart Web Crawler',
    category: 'engineering',
    myrmSkillId: 'web-scraping',
    myrmSkillNameZh: '网页解析与数据抓取',
    myrmSkillNameEn: 'Web Scraping & DOM Extraction',
    descriptionZh: '精准提取网页正文、表格、结构化字段与链接网络。',
    descriptionEn: 'Extracts article content, data tables, and structured web data reliably.',
    recommendedPromptZh: '请抓取目标页面的主要资讯列表与价格参数，整理为结构化表格。',
    recommendedPromptEn: 'Please scrape the target page items and specs into a structured table.',
  },
  {
    id: 'wb-pdf-generator',
    wbNameZh: 'PDF 文档排版生成器',
    wbNameEn: 'PDF Layout & Generation',
    category: 'office',
    myrmSkillId: 'pdf-generator',
    myrmSkillNameZh: 'PDF 规范排版生成',
    myrmSkillNameEn: 'PDF Standard Typesetting & Export',
    descriptionZh: '支持高保真单页与多页 PDF 合同、备忘录与技术规格书导出。',
    descriptionEn: 'Exports high-fidelity multi-page PDF memos, specs, and invoices.',
    recommendedPromptZh: '请排版并生成一份正式的合作备忘录 PDF 文档。',
    recommendedPromptEn: 'Please layout and generate an official memorandum PDF document.',
  },
  {
    id: 'wb-data-analysis',
    wbNameZh: '数据探索与统计分析',
    wbNameEn: 'Data Exploration & Analysis',
    category: 'growth',
    myrmSkillId: 'data-analysis-pipeline',
    myrmSkillNameZh: '数据分析全流程流水线',
    myrmSkillNameEn: 'Data Analysis Pipeline',
    descriptionZh: '清洗缺失值、描述性统计、相关性挖掘与指标分布可视化。',
    descriptionEn: 'Data cleaning, descriptive statistics, and trend visualization.',
    recommendedPromptZh: '请加载此数据集，计算核心均值与方差并绘制分布图。',
    recommendedPromptEn: 'Please load this dataset, compute core statistics, and plot distributions.',
  },
  {
    id: 'wb-arch-diagram',
    wbNameZh: '系统架构与流程图表',
    wbNameEn: 'Architecture Diagram Pro',
    category: 'engineering',
    myrmSkillId: 'architecture-diagram',
    myrmSkillNameZh: '架构蓝图与时序图绘制',
    myrmSkillNameEn: 'Architecture Blueprint & Flowcharts',
    descriptionZh: '生成标准 Mermaid 与现代 SVG 架构图、流程时序图与模块关系图。',
    descriptionEn: 'Generates standard Mermaid and SVG architecture and sequence diagrams.',
    recommendedPromptZh: '请为当前微服务调用链绘制一张清晰的架构交互时序图。',
    recommendedPromptEn: 'Please draw an architecture interaction sequence diagram for microservices.',
  },
  {
    id: 'wb-wechat-article',
    wbNameZh: '微信公众号图文排版',
    wbNameEn: 'WeChat Article Formatter',
    category: 'growth',
    myrmSkillId: 'wechat-article-formatter',
    myrmSkillNameZh: '微信公众号排版引擎',
    myrmSkillNameEn: 'WeChat Article Layout Engine',
    descriptionZh: '生成自适应内联样式，杜绝外部 CSS 丢失，兼容富文本一键粘贴。',
    descriptionEn: 'Generates inline styles for WeChat editor with flawless formatting.',
    recommendedPromptZh: '请将这篇技术科普文章排版为适合微信公众号发布的富文本 HTML。',
    recommendedPromptEn: 'Please format this article for WeChat Official Accounts with inline styles.',
  },
  {
    id: 'wb-code-review',
    wbNameZh: '代码安全与质量审查',
    wbNameEn: 'Code Review & Security Audit',
    category: 'engineering',
    myrmSkillId: 'code-review-pipeline',
    myrmSkillNameZh: '代码审查与漏洞流水线',
    myrmSkillNameEn: 'Code Review Pipeline',
    descriptionZh: '自动化 Diff 审查、内存泄漏预警、空指针防护与规范合规性校验。',
    descriptionEn: 'Automated diff reviews, memory leak alerts, and style compliance checks.',
    recommendedPromptZh: '请审查当前 Git 修改，指出潜在的安全隐患与可优化坏味道。',
    recommendedPromptEn: 'Please review current git changes and flag potential bugs and code smells.',
  },
  {
    id: 'wb-competitive-intel',
    wbNameZh: '竞品情报与动向监测',
    wbNameEn: 'Competitive Intelligence',
    category: 'growth',
    myrmSkillId: 'competitive-analysis-pipeline',
    myrmSkillNameZh: '竞品动态追踪与矩阵对比',
    myrmSkillNameEn: 'Competitive Analysis Pipeline',
    descriptionZh: '跟踪对标产品发版日志、功能演进、定价策略与客群优劣势矩阵。',
    descriptionEn: 'Monitors competitor release notes, feature shifts, and pricing matrices.',
    recommendedPromptZh: '请梳理当前同类产品的最新功能更新并制作优劣势对照矩阵。',
    recommendedPromptEn: 'Please compile recent competitor updates and output a feature matrix.',
  },
  {
    id: 'wb-db-diagnostics',
    wbNameZh: '数据库慢查与索引诊断',
    wbNameEn: 'Database Slow Query Diagnoser',
    category: 'engineering',
    myrmSkillId: 'db-diagnostics',
    myrmSkillNameZh: '数据库异常诊断与优化',
    myrmSkillNameEn: 'Database Diagnostics & Tuning',
    descriptionZh: '分析慢查询日志、EXPLAIN 计划、锁争用与索引缺失建议。',
    descriptionEn: 'Analyzes slow queries, EXPLAIN execution plans, and lock contentions.',
    recommendedPromptZh: '请分析给定的 SQL 执行计划并提供索引添加与重写建议。',
    recommendedPromptEn: 'Please analyze this SQL EXPLAIN plan and recommend index optimizations.',
  },
  {
    id: 'wb-life-dashboard',
    wbNameZh: '个人效率与生活看板',
    wbNameEn: 'Personal Life Dashboard',
    category: 'operations',
    myrmSkillId: 'personal-life-workbench',
    myrmSkillNameZh: '8 模块个人生活与效率工作台',
    myrmSkillNameEn: '8-Module Personal Life Workbench',
    descriptionZh: '生成自包含、零外部依赖、数据本地持久化的交互式个人工作台。',
    descriptionEn: 'Self-contained, offline-first personal dashboard with 8 modular blocks.',
    recommendedPromptZh: '请为我生成一个包含今日焦点、习惯打卡和番茄钟的个人工作台网页。',
    recommendedPromptEn: 'Please generate a personal workbench with daily focus, habits, and pomodoro.',
  },
  {
    id: 'wb-crm-review',
    wbNameZh: '大客户沟通草稿合规审查',
    wbNameEn: 'VIP Client Message Review',
    category: 'office',
    myrmSkillId: 'customer-relationship-draft-review',
    myrmSkillNameZh: '客户沟通草稿与意向审核',
    myrmSkillNameEn: 'Customer Relationship Draft Review',
    descriptionZh: '严格审查面向核心客户的邮件与聊天草稿，防范过度承诺与泄密。',
    descriptionEn: 'Audits sensitive client emails and messages against over-promising risks.',
    recommendedPromptZh: '请审核这份发给战略客户的项目延期沟通草稿并提出修改意见。',
    recommendedPromptEn: 'Please review this email draft to a key client regarding schedule updates.',
  },
  {
    id: 'wb-brand-vi',
    wbNameZh: '企业品牌 VI 与视觉规范',
    wbNameEn: 'Brand VI & Visual Guidelines',
    category: 'growth',
    myrmSkillId: 'brand-vi-synthesizer',
    myrmSkillNameZh: '品牌 VI 规范合成器',
    myrmSkillNameEn: 'Brand VI Synthesizer & Guidelines',
    descriptionZh: '提炼品牌主色系、排版层级、间距系统并输出全栈 CSS 变量。',
    descriptionEn: 'Distills brand color palette, typography tokens, and CSS variables.',
    recommendedPromptZh: '请基于提供的品牌 Logo 与主色调，合成完整的品牌 VI 设计规范。',
    recommendedPromptEn: 'Please synthesize a complete brand VI guideline from our logo and palette.',
  },
  {
    id: 'wb-evidence-pack',
    wbNameZh: '项目经验与实施复盘包',
    wbNameEn: 'Project Experience Evidence Pack',
    category: 'operations',
    myrmSkillId: 'project-experience-evidence-pack',
    myrmSkillNameZh: '六步项目经验凭证包向导',
    myrmSkillNameEn: 'Project Experience Evidence Pack Wizard',
    descriptionZh: '将原始诉求、执行轨迹、决策依据沉淀为可复用的项目经验包。',
    descriptionEn: 'Crystallizes project history, trace logs, and decisions into evidence packs.',
    recommendedPromptZh: '请为本次功能迭代打包完整的项目经验复盘与证据清单。',
    recommendedPromptEn: 'Please package a complete project experience review and evidence pack.',
  },
  {
    id: 'wb-host-ops',
    wbNameZh: '主机服务器与资源巡检',
    wbNameEn: 'Host Server Ops & Health',
    category: 'engineering',
    myrmSkillId: 'host-server-ops',
    myrmSkillNameZh: '主机服务器健康巡检',
    myrmSkillNameEn: 'Host Server Ops Health Check',
    descriptionZh: '安全只读检查 CPU、内存、磁盘利用率、僵尸进程与网络连通性。',
    descriptionEn: 'Safe read-only checks for CPU, memory, disk, and zombie processes.',
    recommendedPromptZh: '请对当前宿主机运行一次健康巡检，排查高占用与异常指标。',
    recommendedPromptEn: 'Please run a safe health check on this host to inspect CPU and memory.',
  },
  {
    id: 'wb-lean-coding',
    wbNameZh: '精益编码与极简重构',
    wbNameEn: 'Lean Coding & Refactoring',
    category: 'engineering',
    myrmSkillId: 'lean-coding',
    myrmSkillNameZh: '精益编码与极简设计',
    myrmSkillNameEn: 'Lean Coding & Minimalist Architecture',
    descriptionZh: '严格遵循第一性原理，消除冗余依赖与过度封装，写最纯粹的代码。',
    descriptionEn: 'Eliminates bloat and over-engineering by adhering to first principles.',
    recommendedPromptZh: '请以精益原则重构这个模块，消除死代码并简化抽象层级。',
    recommendedPromptEn: 'Please refactor this module following lean principles to remove dead code.',
  },
  {
    id: 'wb-persona-voice',
    wbNameZh: '真实人物语气与声音提取',
    wbNameEn: 'Tone of Voice Extractor',
    category: 'growth',
    myrmSkillId: 'persona-voice',
    myrmSkillNameZh: '人设立场与语气风格提炼',
    myrmSkillNameEn: 'Persona Voice & Tone Adaptation',
    descriptionZh: '从长文语料提炼句式节奏、用词倾向与负向禁令，生成逼真人设。',
    descriptionEn: 'Extracts author tone, pacing, vocabulary preferences, and negative constraints.',
    recommendedPromptZh: '请从这段历史发言中提炼出作者独特的表达风格与 Tone of Voice。',
    recommendedPromptEn: 'Please distill the author unique voice and tone matrix from these writings.',
  },
  {
    id: 'wb-task-planner',
    wbNameZh: '结构化任务规划与分工',
    wbNameEn: 'Task Planning & Orchestration',
    category: 'operations',
    myrmSkillId: 'task-planning',
    myrmSkillNameZh: '系统化任务规划与目标分解',
    myrmSkillNameEn: 'Task Planning & Goal Decomposition',
    descriptionZh: '将复杂业务目标拆解为可验证的原子子任务与依赖拓扑图。',
    descriptionEn: 'Decomposes complex objectives into atomic verifiable sub-tasks.',
    recommendedPromptZh: '请针对该新业务需求进行深度规划，输出阶段里程碑与任务清单。',
    recommendedPromptEn: 'Please perform task planning for this feature and output a milestone breakdown.',
  },
];

/**
 * 根据 WorkBuddy 技能 ID 或模糊关键词查询对应的 Myrm 迁移项
 */
export function resolveMyrmSkillFromWorkbuddy(key: string): WorkbuddySkillMappingItem | null {
  const normalized = key.trim().toLowerCase();
  if (!normalized) return null;

  return (
    WORKBUDDY_TOP_20_MIGRATION_MAP.find(
      (item) =>
        item.id.toLowerCase() === normalized ||
        item.wbNameZh.toLowerCase().includes(normalized) ||
        item.wbNameEn.toLowerCase().includes(normalized) ||
        item.myrmSkillId.toLowerCase() === normalized,
    ) ?? null
  );
}

/**
 * 跨生态技能搜索
 */
export function searchWorkbuddyMigrationSkills(query: string): WorkbuddySkillMappingItem[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return [...WORKBUDDY_TOP_20_MIGRATION_MAP];
  }

  return WORKBUDDY_TOP_20_MIGRATION_MAP.filter((item) => {
    return (
      item.wbNameZh.toLowerCase().includes(normalized) ||
      item.wbNameEn.toLowerCase().includes(normalized) ||
      item.myrmSkillNameZh.toLowerCase().includes(normalized) ||
      item.myrmSkillNameEn.toLowerCase().includes(normalized) ||
      item.descriptionZh.toLowerCase().includes(normalized) ||
      item.descriptionEn.toLowerCase().includes(normalized) ||
      item.myrmSkillId.toLowerCase().includes(normalized)
    );
  });
}
