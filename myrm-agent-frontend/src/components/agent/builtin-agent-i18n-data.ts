/**
 * [OUTPUT]
 * BUILTIN_AGENT_I18N: 内置智能体多语言名称与描述映射表
 *
 * [POS]
 * builtin-agent-i18n 的数据 SSOT（纯数据，无运行时逻辑）。
 */

export interface LocaleStrings {
  name: string;
  description: string;
}

export interface AgentI18nEntry {
  en: LocaleStrings;
  zh: LocaleStrings;
}

export const BUILTIN_AGENT_I18N: Record<string, AgentI18nEntry> = {
  'builtin-general': {
    en: {
      name: 'General Assistant',
      description: 'Versatile AI assistant for everyday tasks — writing, analysis, Q&A, brainstorming, and more.',
    },
    zh: { name: '通用助手', description: '多功能 AI 助手，适用于日常写作、分析、问答、头脑风暴等各类任务。' },
  },
  'builtin-economy': {
    en: {
      name: 'Knowledge Work',
      description:
        'Deliverable-first assistant for everyday knowledge work — search, files, tasks, and memory. Ideal for Hermes migrants and Cowork-style workflows.',
    },
    zh: {
      name: '知识工作助手',
      description: '面向日常知识工作的交付优先助手——搜索、文件、任务与记忆。适合 Hermes 迁移与 Cowork 式工作流。',
    },
  },
  'builtin-writer': {
    en: {
      name: 'Content Creator',
      description: 'Expert in writing, editing, copywriting, and content strategy with a creative flair.',
    },
    zh: { name: '内容创作者', description: '擅长写作、编辑、文案创意与内容策略，兼具创意灵感。' },
  },
  'builtin-researcher': {
    en: {
      name: 'Research Analyst',
      description:
        'Deep research and analysis — structured reports, data-driven insights, and multi-angle investigation.',
    },
    zh: { name: '研究分析师', description: '深度研究与分析——结构化报告、数据驱动洞察、多角度调研。' },
  },
  'builtin-developer': {
    en: {
      name: 'Code Developer',
      description: 'Focused coding assistant — write, debug, review, and optimize code with precision.',
    },
    zh: { name: '代码开发者', description: '专注的编程助手——精准编写、调试、审查和优化代码。' },
  },
  'builtin-fast-search': {
    en: {
      name: 'Quick Search',
      description:
        'Fast web search — concise, real-time answers with source citations. Ideal for quick facts and news.',
    },
    zh: { name: '快速搜索', description: '快速网页搜索——简洁实时、带来源引用，适合查事实与新闻。' },
  },
  'builtin-deep-search': {
    en: {
      name: 'Deep Search',
      description: 'Thorough multi-source research — reads full pages, cross-references, and self-validates answers.',
    },
    zh: { name: '深度搜索', description: '多源深度调研——阅读全文、交叉验证并自检答案。' },
  },
  'builtin-translator': {
    en: {
      name: 'Translator',
      description: 'Professional multilingual translation and localization — faithful, natural, culturally adapted.',
    },
    zh: { name: '翻译专家', description: '专业多语种翻译与本地化——忠实原意、表达自然、文化适配。' },
  },
  'builtin-social-media': {
    en: {
      name: 'Social Media Strategist',
      description:
        'Content creation for Xiaohongshu, Douyin, Bilibili, Twitter, Instagram — platform-native copy and strategy.',
    },
    zh: { name: '社媒策略师', description: '为小红书、抖音、B站、Twitter、Instagram 创作平台原生内容与策略。' },
  },
  'builtin-data-analyst': {
    en: {
      name: 'Data Analyst',
      description: 'Data analysis, visualization recommendations, SQL, and insight extraction from structured data.',
    },
    zh: { name: '数据分析师', description: '数据分析、可视化建议、SQL 编写与结构化数据洞察提取。' },
  },
  'builtin-product-manager': {
    en: {
      name: 'Product Manager',
      description: 'PRD writing, competitive analysis, requirement breakdown, user story mapping, and prioritization.',
    },
    zh: { name: '产品经理', description: 'PRD 撰写、竞品分析、需求拆解、用户故事梳理与优先级排序。' },
  },
  'builtin-tutor': {
    en: {
      name: 'Tutor',
      description:
        'Patient teaching assistant — explain concepts, answer questions, create study plans, and guide learning.',
    },
    zh: { name: '学习导师', description: '耐心的教学助手——讲解概念、解答疑问、制定学习计划、引导学习。' },
  },
  'builtin-newsletter': {
    en: {
      name: 'Newsletter Editor',
      description: 'Research topics, write engaging newsletters, manage editorial calendars, and optimize open rates.',
    },
    zh: { name: 'Newsletter 编辑', description: '选题调研、撰写有吸引力的通讯内容、管理编辑日历、优化打开率。' },
  },
  'builtin-designer': {
    en: {
      name: 'Designer',
      description: 'Creative design assistant — generates images, critiques UI/UX, and provides visual inspiration.',
    },
    zh: { name: '设计师', description: '创意设计助手——生成图像、点评 UI/UX，并提供视觉灵感。' },
  },
  'builtin-video-studio': {
    en: {
      name: 'Video Studio',
      description:
        'AI video production assistant — scripts, storyboards, visuals, voiceovers, and complete video assembly.',
    },
    zh: {
      name: '视频工作室',
      description: 'AI 视频制作助手——脚本、分镜、画面生成、配音与成片组装。',
    },
  },
  'builtin-seo': {
    en: {
      name: 'SEO Strategist',
      description: 'Keyword research, content optimization, technical SEO audits, and competitive SERP analysis.',
    },
    zh: { name: 'SEO 策略师', description: '关键词研究、内容优化、技术 SEO 审计与竞争 SERP 分析。' },
  },
  'builtin-scheduler': {
    en: {
      name: 'Schedule Planner',
      description:
        'Task decomposition, time blocking, priority management, deadline tracking, and productivity systems.',
    },
    zh: { name: '日程规划师', description: '任务拆解、时间块规划、优先级管理、截止日期跟踪与效率系统。' },
  },
  'builtin-meeting': {
    en: {
      name: 'Meeting Scribe',
      description: 'Extract key points, decisions, action items, and follow-ups from meeting notes or transcripts.',
    },
    zh: { name: '会议纪要员', description: '从会议记录中提取要点、决策、行动项与后续跟进事项。' },
  },
  'builtin-career': {
    en: {
      name: 'Career Coach',
      description: 'Resume optimization, interview prep, career planning, networking strategy, and salary negotiation.',
    },
    zh: { name: '职业教练', description: '简历优化、面试准备、职业规划、人脉策略与薪资谈判。' },
  },
  'builtin-finance': {
    en: {
      name: 'Finance Advisor',
      description: 'Budget analysis, investment basics, expense tracking strategies, and personal financial planning.',
    },
    zh: { name: '理财顾问', description: '预算分析、投资基础、支出管理策略与个人财务规划。' },
  },
  'builtin-travel': {
    en: {
      name: 'Travel Planner',
      description: 'Itinerary design, destination research, budget optimization, and local experience recommendations.',
    },
    zh: { name: '旅行规划师', description: '行程设计、目的地研究、预算优化与本地体验推荐。' },
  },
  'builtin-email': {
    en: {
      name: 'Email Expert',
      description: 'Professional email drafting — cold outreach, follow-ups, negotiations, and business communication.',
    },
    zh: { name: '邮件专家', description: '专业邮件撰写——冷启动触达、跟进邮件、商务谈判与沟通。' },
  },
  'builtin-ko-office': {
    en: {
      name: 'Korean Office Assistant',
      description: 'Formal Korean business assistant for email, meeting notes, and office workflows.',
    },
    zh: { name: '韩语办公助手', description: '正式韩语商务助手——邮件、会议纪要、办公流程。' },
  },
  'builtin-automation': {
    en: {
      name: 'Automation Builder',
      description: 'Workflow design, task automation strategies, integration planning, and efficiency optimization.',
    },
    zh: { name: '自动化构建师', description: '工作流设计、任务自动化策略、集成规划与效率优化。' },
  },
  'builtin-cli_visual': {
    en: {
      name: 'CLI Visual Agent',
      description: 'Supports programming assistants like Claude Code, Codex, and Gemini CLI in local sandbox',
    },
    zh: { name: 'CLI 可视化助手', description: '在本地沙箱中支持 Claude Code、Codex、Gemini CLI 等编程助手。' },
  },
  'builtin-hr_screener': {
    en: {
      name: 'HR Resume Screener',
      description: 'Automatically parse and extract key information from resumes and CVs into structured formats.',
    },
    zh: { name: 'HR 简历筛选', description: '自动解析简历与 CV，提取关键信息并输出结构化结果。' },
  },
  'builtin-speaker': {
    en: {
      name: 'Audio Assistant',
      description: 'Text-to-speech assistant — converts text into natural-sounding audio.',
    },
    zh: { name: '语音助手', description: '文本转语音助手——将文字转换为自然流畅的音频。' },
  },
  'builtin-social_intelligence': {
    en: {
      name: 'Social Intelligence',
      description:
        'Track discussions, sentiment, and trends on X (Twitter) — monitor influencers, brands, and competitors.',
    },
    zh: {
      name: '社媒情报',
      description: '追踪 X (Twitter) 上的讨论、情绪与趋势——监控意见领袖、品牌与竞品动态。',
    },
  },
  'strategic-advisor': {
    en: {
      name: 'Strategic Advisor',
      description:
        'Independent architectural reviewer and strategic critic — evaluates design elegance, scalability, and trade-offs in read-only mode.',
    },
    zh: {
      name: '战略顾问',
      description: '独立的系统架构与战略质询顾问——以严格只读模式审查架构美感、可扩展性极限与权衡取舍。',
    },
  },
};

