/**
 * [INPUT]
 * - WorkBuddy ERP 核心高频技能资产与工作流清单
 * - Myrm Prebuilt Skills 资产库 (assets/prebuilt_skills/*)
 *
 * [OUTPUT]
 * - WORKBUDDY_TOP20_MIGRATION_MAP: 官方 20 大高频办公/工程/运营技能一键迁移映射与增强说明 SSOT
 * - isWorkBuddyMigrationSkill: 辅助判断当前技能是否属于 WorkBuddy 20 大精选迁移体系
 * - getWorkBuddyMigrationInfo: 获取特定技能的迁移对标与增强细节
 *
 * [POS]
 * 技能市场与模板市场迁移中心服务层。帮助从 WorkBuddy 或通用 ERP 迁移的用户无缝找到对标技能与最佳实践。
 */

export interface WorkBuddySkillMigrationItem {
  /** 原 WorkBuddy 技能/工作流名称 */
  wbSkillName: string;
  /** 原分类体系 */
  category: 'office' | 'engineering' | 'growth' | 'operations' | 'analysis';
  /** Myrm 对应的生产级预置技能 ID */
  myrmSkillId: string;
  /** 技能简要描述 */
  summaryZh: string;
  summaryEn: string;
  /** Myrm 相较于原版的架构增强与核心优势 */
  enhancementsZh: string[];
  enhancementsEn: string[];
  /** 推荐的冒烟验证提示词 */
  recommendedPrompt: string;
}

export const WORKBUDDY_TOP20_MIGRATION_MAP: readonly WorkBuddySkillMigrationItem[] = [
  {
    wbSkillName: 'Office Document Generator (PPT/Word/Excel)',
    category: 'office',
    myrmSkillId: 'office-document',
    summaryZh: '一键生成高品质 16:9 商务 PPT、公文级 Word 文档与千分位规范 Excel 表格',
    summaryEn: 'Generate high-polish 16:9 business presentations, formatted Word docs, and standard Excel sheets',
    enhancementsZh: ['原生集成 python-pptx/docx 沙箱渲染', '反文字墙与断言型大纲门禁', '在线 XLSX Univer 双向编辑器'],
    enhancementsEn: ['Native sandbox python-pptx/docx runtime', 'Thesis headline & anti-text-wall guard', 'Online Univer bidirectional editor'],
    recommendedPrompt: '使用 office-document 技能为我生成一份 2026 Q3 产品增长规划的 16:9 商业汇报 PPT 大纲与首页幻灯片',
  },
  {
    wbSkillName: 'Web Data Harvester & Scraper',
    category: 'engineering',
    myrmSkillId: 'web-scraping',
    summaryZh: '高韧性网页抓取与结构化数据提取',
    summaryEn: 'High-resilience web extraction and structured scraping',
    enhancementsZh: ['Patchright 浏览器拟人化反爬', 'DOM 清洗与 Markdown 直出', '网络重试与超时防护'],
    enhancementsEn: ['Patchright stealth browser runtime', 'DOM cleanup to clean markdown', 'Network retry & timeout resilient'],
    recommendedPrompt: '使用 web-scraping 技能抓取最新 AI Agent 行业新闻并提炼核心趋势表格',
  },
  {
    wbSkillName: 'Deep Web Researcher',
    category: 'analysis',
    myrmSkillId: 'deep-research',
    summaryZh: '多源交叉验证的深度全网调研与行业洞察',
    summaryEn: 'Multi-source cross-validated deep research and competitive landscape analysis',
    enhancementsZh: ['多源检索与证据交叉核对', '金字塔结构深度综述', '自动化引用链追溯'],
    enhancementsEn: ['Multi-source search & cross-validation', 'Pyramid structure synthesis', 'Automated citation traceability'],
    recommendedPrompt: '使用 deep-research 技能调研 2026 年企业端 Agent 沙箱技术的最新演进与商业化格局',
  },
  {
    wbSkillName: 'Data Analytics & Chart Pipeline',
    category: 'analysis',
    myrmSkillId: 'data-analysis-pipeline',
    summaryZh: '端到端数据清洗、探索性分析与可视化图表生成',
    summaryEn: 'End-to-end data cleaning, exploratory analysis, and chart visualization',
    enhancementsZh: ['DuckDB/Pandas 原生高性能执行', 'ECharts/Matplotlib 双格式导出', '统计显著性自动检验'],
    enhancementsEn: ['Native DuckDB/Pandas sandbox execution', 'Dual ECharts/Matplotlib export', 'Automated statistical significance checks'],
    recommendedPrompt: '使用 data-analysis-pipeline 技能为我分析一组模拟用户留存数据并绘制多维留存热力图',
  },
  {
    wbSkillName: 'Automated Code Reviewer',
    category: 'engineering',
    myrmSkillId: 'code-review',
    summaryZh: '代码坏味道检测、安全隐患审查与重构建议',
    summaryEn: 'Code smell detection, security vulnerability scan, and clean refactoring advice',
    enhancementsZh: ['AST 语法级精准审查', 'OWASP Top 10 安全门禁', '统一遵循工程代码红线'],
    enhancementsEn: ['AST syntax precision review', 'OWASP Top 10 security gating', 'Strict engineering redline compliance'],
    recommendedPrompt: '使用 code-review 技能对我最新的 API 路由鉴权逻辑进行安全防线与性能审计',
  },
  {
    wbSkillName: 'Host & Server Ops Health Diagnostics',
    category: 'operations',
    myrmSkillId: 'host-server-ops',
    summaryZh: 'Linux/Unix 主机健康体检、端口进程扫描与资源瓶颈诊断',
    summaryEn: 'Linux/Unix host health check, process & port scan, and resource bottleneck diagnosis',
    enhancementsZh: ['只读安全沙箱门禁', '一键生成 Markdown 体检表', '无缝挂载为定时 CronBlueprint'],
    enhancementsEn: ['Strict read-only safety gate', 'One-click Markdown health report', 'Native CronBlueprint schedule integration'],
    recommendedPrompt: '使用 host-server-ops 技能对当前主机系统的 CPU、内存、磁盘与开放端口进行只读健康巡检',
  },
  {
    wbSkillName: 'Personal Life & Productivity Workbench',
    category: 'office',
    myrmSkillId: 'personal-life-workbench',
    summaryZh: '8 模块自包含个人生活与效率工作台交互式微应用',
    summaryEn: '8-module self-contained personal life and daily productivity interactive widget',
    enhancementsZh: ['零外部 CDN 纯原生渲染', '宿主暗黑/明亮主题自动桥接', 'localStorage 响应式离线持久化'],
    enhancementsEn: ['Zero external CDN dependencies', 'Host theme CSS token bridge', 'LocalStorage reactive persistence'],
    recommendedPrompt: '使用 personal-life-workbench 技能为我构建一个包含今日焦点、待办看板与番茄钟的高颜值个人工作台微应用',
  },
  {
    wbSkillName: 'Customer Relationship Draft Review',
    category: 'office',
    myrmSkillId: 'customer-relationship-draft-review',
    summaryZh: '对外邮件、合同磋商与敏感客诉沟通 4 维合规雷达审查',
    summaryEn: '4-dimension compliance and tone review for sensitive customer emails, pitches, and dispute letters',
    enhancementsZh: ['无保留履约承诺严格拦截', '商业机密与隐私防御', '三段论得体话术智能润色'],
    enhancementsEn: ['Unchecked commitment blocking', 'Trade secret & PII defense', 'Diplomatic three-part tone polishing'],
    recommendedPrompt: '使用 customer-relationship-draft-review 技能审查我准备向客户发送的项目延期致歉信草稿',
  },
  {
    wbSkillName: 'Design Session Brand VI Synthesizer',
    category: 'growth',
    myrmSkillId: 'brand-vi-synthesizer',
    summaryZh: '从视觉讨论会话中自动萃取品牌设计规范与机读 Token',
    summaryEn: 'Synthesize brand design guidelines and machine-readable design tokens from design discussions',
    enhancementsZh: ['WCAG AA 无障碍对比度检查', '自动生成 tokens.css 与 Tailwind 配置', '下游 PPT/HTML 工件强制继承约束'],
    enhancementsEn: ['WCAG AA contrast ratio validation', 'Export tokens.css & Tailwind config', 'Downstream artifact visual inheritance'],
    recommendedPrompt: '使用 brand-vi-synthesizer 技能将我们讨论确定的极简科技蓝品牌视觉规范整理为标准化 Token 与约束',
  },
  {
    wbSkillName: 'Enterprise Branded Office Template Pack',
    category: 'office',
    myrmSkillId: 'enterprise-branded-office',
    summaryZh: '企业专属 16:9 PPTX/DOCX/XLSX 统一品牌母版与同事零配置交接',
    summaryEn: 'Unified enterprise branded 16:9 PPTX/DOCX/XLSX master templates with zero-config colleague handoff',
    enhancementsZh: ['三合一母版开箱即用', '版心网格与字体规范固化', '一键打包免配置分发'],
    enhancementsEn: ['All-in-one 3-suite master templates', 'Strict layout grid & typography presets', 'Zero-config team sharing pack'],
    recommendedPrompt: '使用 enterprise-branded-office 技能为我所在团队制定一套标准的商务汇报母版规范',
  },
  {
    wbSkillName: 'Voice Memo & Meeting Synthesizer',
    category: 'office',
    myrmSkillId: 'voice-memo-synthesizer',
    summaryZh: '语音备忘录与会议录音四维提炼（纪要、看板任务、长效记忆、表格）',
    summaryEn: '4-dimensional decomposition of voice memos & meeting audio into minutes, kanban, memory, and spreadsheet',
    enhancementsZh: ['原子化看板待办一键拆解', '长效上下文自动沉淀', '防重复幂等指纹校验'],
    enhancementsEn: ['Automated kanban task extraction', 'Long-term context memory indexing', 'Deterministic idempotency gating'],
    recommendedPrompt: '使用 voice-memo-synthesizer 技能帮我将今天的项目周会录音草稿提炼为会议纪要与看板任务',
  },
  {
    wbSkillName: 'Persona Voice & Corpus Distillation',
    category: 'growth',
    myrmSkillId: 'persona-voice',
    summaryZh: '个人真实语料蒸馏与高质量拟真对话型专家技能一键封装',
    summaryEn: 'Distill authentic personal corpus into lifelike conversational expert skill presets',
    enhancementsZh: ['句式节奏与态度五维画像', '专有词汇黑白名单门禁', '开箱即用的数字分身封装'],
    enhancementsEn: ['5D syntax rhythm & attitude matrix', 'Strict vocabulary whitelist/blacklist', 'Turnkey digital twin packaging'],
    recommendedPrompt: '使用 persona-voice 技能分析我的历史博文风格，提取我的专属语言人设规范',
  },
  {
    wbSkillName: 'WeChat Official Article Formatter',
    category: 'growth',
    myrmSkillId: 'wechat-article-formatter',
    summaryZh: '微信公众号排版引擎，将 Markdown 转换为优美内联样式富文本',
    summaryEn: 'WeChat Official Account formatter, converting markdown to beautiful inline-styled HTML',
    enhancementsZh: ['100% 兼容微信编辑器样式注入', '代码高亮与表格完美适配', '一键复制到剪贴板'],
    enhancementsEn: ['100% compatible WeChat inline styles', 'Perfect code block & table styling', 'One-click copy to clipboard'],
    recommendedPrompt: '使用 wechat-article-formatter 技能将这篇技术科普文章排版为适合微信公众号发布的富文本',
  },
  {
    wbSkillName: 'Project Experience Six-Step Evidence Pack',
    category: 'engineering',
    myrmSkillId: 'project-experience-evidence-pack',
    summaryZh: '严格基于实测证据链的项目实战经验沉淀与案例向导',
    summaryEn: 'Evidence-based 6-step project experience and post-mortem crystallization wizard',
    enhancementsZh: ['拒绝空洞理论，强制物理实测证据', '六步闭环可审计记录', '团队可复用防踩坑资产'],
    enhancementsEn: ['Mandatory empirical evidence over theory', '6-step auditable trace record', 'Reusable team immune asset'],
    recommendedPrompt: '使用 project-experience-evidence-pack 技能为刚刚完成的微服务迁移任务整理六步实测证据复盘包',
  },
  {
    wbSkillName: 'Daily Briefing & News Digest',
    category: 'analysis',
    myrmSkillId: 'daily-briefing',
    summaryZh: '多源聚合每日早报、行业动态速递与摘要提取',
    summaryEn: 'Multi-source morning briefing, industry updates, and concise digest synthesis',
    enhancementsZh: ['跨平台 RSS/网页多源抓取', '关键信息去重与提纯', '自适应定时自动推送'],
    enhancementsEn: ['Cross-platform RSS/web scraping', 'Deduplication and bullet distillation', 'Automated schedule delivery'],
    recommendedPrompt: '使用 daily-briefing 技能为我生成今日 AI 前沿与全球科技投资速览早报',
  },
  {
    wbSkillName: 'Systematic Debugging & Root Cause Analysis',
    category: 'engineering',
    myrmSkillId: 'systematic-debugging',
    summaryZh: '系统化软件缺陷排查、日志链路诊断与根因定位',
    summaryEn: 'Systematic software defect troubleshooting, log trace analysis, and root cause isolation',
    enhancementsZh: ['二分排查与最小复现测试', '调用栈与异常拓扑解析', '提供防复发守护单测'],
    enhancementsEn: ['Binary search & minimal reproduction', 'Call stack & error topology mapping', 'Regression-proof guard unit tests'],
    recommendedPrompt: '使用 systematic-debugging 技能帮我分析这段并发偶发的死锁日志并找出根本原因',
  },
  {
    wbSkillName: 'PDF Report & Document Generator',
    category: 'office',
    myrmSkillId: 'pdf-generator',
    summaryZh: '通过无头浏览器高保真渲染并导出商业级矢量 PDF',
    summaryEn: 'High-fidelity vector PDF generation and printing via headless browser engine',
    enhancementsZh: ['CSS 分页符与页眉页脚精确控制', '支持复杂图表与矢量图导出', '自动化像素级对齐'],
    enhancementsEn: ['Precise CSS print page-breaks & headers', 'Vector graphics & chart rendering', 'Automated pixel-level alignment'],
    recommendedPrompt: '使用 pdf-generator 技能为我将这份 Markdown 格式的季度财报渲染为高保真 PDF',
  },
  {
    wbSkillName: 'Infographic & Visual Poster Designer',
    category: 'growth',
    myrmSkillId: 'infographic',
    summaryZh: '信息图表、架构卡片与技术海报纯 SVG/HTML 矢量生成',
    summaryEn: 'Infographics, architecture cards, and visual posters crafted in pure SVG/HTML',
    enhancementsZh: ['纯矢量 SVG 导出无锯齿', '自适应主题与移动端视口', '信息层级高度精炼'],
    enhancementsEn: ['Pure vector SVG export', 'Responsive theme & mobile layout', 'High visual hierarchy clarity'],
    recommendedPrompt: '使用 infographic 技能为我设计一张展示现代 AI Agent 架构体系的信息图',
  },
  {
    wbSkillName: 'Evidence & Discipline Engineering Safety Protocol',
    category: 'engineering',
    myrmSkillId: 'evidence-discipline',
    summaryZh: '严苛的软件工程证据驱动执行准则与防御式工作协议',
    summaryEn: 'Strict evidence-driven engineering discipline and defensive coding protocol',
    enhancementsZh: ['先读后改严禁脑补假设', '经验库（learnings.md）自进化闭环', '全链路测试红绿验证'],
    enhancementsEn: ['Read-before-edit anti-hallucination', 'Self-evolving learnings.md feedback loop', 'Full-cycle red-green test gate'],
    recommendedPrompt: '在当前代码修改任务中严格激活 evidence-discipline 技能，确保每一步操作均有代码行号证据',
  },
  {
    wbSkillName: 'UI Design & Component Restoration',
    category: 'engineering',
    myrmSkillId: 'ui-design-restoration',
    summaryZh: '高保真 UI 还原、组件提取与 Tailwind/CSS 响应式重构',
    summaryEn: 'Pixel-perfect UI restoration, component extraction, and responsive Tailwind/CSS styling',
    enhancementsZh: ['54 种主流产品设计语言资产支持', '纯 CSS Token 规范驱动', '组件级模块化拆解'],
    enhancementsEn: ['54 real-world design systems support', 'Pure CSS token reference driven', 'Clean modular component separation'],
    recommendedPrompt: '使用 ui-design-restoration 技能帮我将一个粗糙的表格页面重构为现代高质感的 Dashboard',
  },
];

const WB_MIGRATION_SKILL_ID_SET = new Set(WORKBUDDY_TOP20_MIGRATION_MAP.map((m) => m.myrmSkillId));

/**
 * 判断指定 skillId 是否属于 WorkBuddy Top 20 精选迁移映射技能
 */
export function isWorkBuddyMigrationSkill(skillId: string): boolean {
  return WB_MIGRATION_SKILL_ID_SET.has(skillId);
}

/**
 * 获取指定技能在 WorkBuddy 中的迁移对标详情
 */
export function getWorkBuddyMigrationInfo(skillId: string): WorkBuddySkillMigrationItem | undefined {
  return WORKBUDDY_TOP20_MIGRATION_MAP.find((m) => m.myrmSkillId === skillId);
}
