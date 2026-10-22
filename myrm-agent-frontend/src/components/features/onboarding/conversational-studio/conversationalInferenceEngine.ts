import {
  AgentDomainPreset,
  AgentRecipeDraft,
  RecommendedSkill,
} from './conversationalOnboardingTypes';

const DOMAIN_RECIPES: Record<AgentDomainPreset, Omit<AgentRecipeDraft, 'presetKey'>> = {
  marketing: {
    suggestedName: '增长与营销洞察官',
    roleTitle: 'Growth & Market Analyst',
    description: '专注于全网竞品调研、社交舆情监控与转化漏斗分析',
    systemPrompt:
      '你是一名资深数字营销与市场分析专家。善于使用数据可视化、舆情追踪和内容策略帮助团队快速获取商业洞察。',
    recommendedSkills: [
      {
        id: 'skill_web_scraper',
        name: '全网舆情与网页抓取',
        category: 'Data',
        description: '自动提取公开网页与社媒动态',
        selected: true,
      },
      {
        id: 'skill_chart_generator',
        name: '多维交互图表生成',
        category: 'Visualization',
        description: '生成折线图、漏斗图与对比看板',
        selected: true,
      },
      {
        id: 'skill_report_synthesizer',
        name: '周报与竞品简报速成',
        category: 'Reporting',
        description: '按模板聚合提炼核心结论',
        selected: false,
      },
    ],
    recommendedModelTier: 'turbo',
    estimatedTokenSavingPct: 35,
  },
  software_eng: {
    suggestedName: '全栈架构工程师',
    roleTitle: 'Staff Fullstack Architect',
    description: '专注于系统架构设计、复杂代码重构与 Git 自动化协同',
    systemPrompt:
      '你是一名世界顶级软件架构师与全栈工程师。坚持 DRY 原则、高内聚低耦合，编写高性能、易维护的整洁代码。',
    recommendedSkills: [
      {
        id: 'skill_git_tools',
        name: 'Git 自动化协作流',
        category: 'DevOps',
        description: '分支管理、提交历史对比与冲突自检',
        selected: true,
      },
      {
        id: 'skill_code_review',
        name: '代码异味与质量巡检',
        category: 'Engineering',
        description: '单文件行数、复杂度与规范检测',
        selected: true,
      },
      {
        id: 'skill_test_generator',
        name: '契约与单测生成器',
        category: 'QA',
        description: '全自动编写 Vitest/Jest 测试用例',
        selected: true,
      },
    ],
    recommendedModelTier: 'pro',
    estimatedTokenSavingPct: 45,
  },
  admin_writing: {
    suggestedName: '行政文书高效助手',
    roleTitle: 'Executive Writing Partner',
    description: '专注于会议纪要整理、多语种公文撰写与日程待办归纳',
    systemPrompt:
      '你是一名细致严谨的高级行政与文书助理。语言得体、逻辑清晰，能迅速将口语记录转化为格式标准的正式公文。',
    recommendedSkills: [
      {
        id: 'skill_doc_formatter',
        name: '公文与 Markdown 格式排版',
        category: 'Writing',
        description: '统一段落间距、标点与层级编号',
        selected: true,
      },
      {
        id: 'skill_meeting_extractor',
        name: '录音纪要与待办提取',
        category: 'Efficiency',
        description: '从漫长会议中提炼行动项与负责人',
        selected: true,
      },
    ],
    recommendedModelTier: 'turbo',
    estimatedTokenSavingPct: 30,
  },
  finance_audit: {
    suggestedName: '财报与对账审计官',
    roleTitle: 'Financial Audit Specialist',
    description: '专注于发票台账核对、报销单验真与收支损益交叉审计',
    systemPrompt:
      '你是一名拥有注册会计师思维的财务审计专家。对数字与凭证极度敏感，核算过程严谨合规。',
    recommendedSkills: [
      {
        id: 'skill_spreadsheet_formula',
        name: '表格函数与对账核算',
        category: 'Finance',
        description: '自动对齐借贷平账与异常金额预警',
        selected: true,
      },
      {
        id: 'skill_invoice_ocr',
        name: '电子发票多维度识别',
        category: 'OCR',
        description: '解析发票代码、税额与防伪标记',
        selected: true,
      },
    ],
    recommendedModelTier: 'pro',
    estimatedTokenSavingPct: 50,
  },
  custom: {
    suggestedName: '全能办公协同搭子',
    roleTitle: 'All-Around Productive Partner',
    description: '通用型日常协同伙伴，随时根据您的任务即时调整技能',
    systemPrompt:
      '你是一名全能、亲和且务实的 AI 办公搭子，致力于帮助用户高效解决各种工作问题。',
    recommendedSkills: [
      {
        id: 'skill_general_search',
        name: '通用网络搜索',
        category: 'Search',
        description: '实时查询最新资讯与事实',
        selected: true,
      },
      {
        id: 'skill_summary_card',
        name: '长文卡片速读',
        category: 'Reading',
        description: '将万字长文浓缩为思维导图要点',
        selected: true,
      },
    ],
    recommendedModelTier: 'turbo',
    estimatedTokenSavingPct: 25,
  },
};

export function getRecipeByPreset(presetKey: AgentDomainPreset): AgentRecipeDraft {
  const base = DOMAIN_RECIPES[presetKey] || DOMAIN_RECIPES.custom;
  return {
    presetKey,
    ...base,
    recommendedSkills: base.recommendedSkills.map((s) => ({ ...s })),
  };
}

export function inferRecipeFromUserInput(input: string): AgentRecipeDraft {
  const lower = input.toLowerCase();

  if (
    lower.includes('代码') ||
    lower.includes('开发') ||
    lower.includes('前端') ||
    lower.includes('后端') ||
    lower.includes('架构') ||
    lower.includes('git') ||
    lower.includes('bug')
  ) {
    return getRecipeByPreset('software_eng');
  }

  if (
    lower.includes('营销') ||
    lower.includes('增长') ||
    lower.includes('竞品') ||
    lower.includes('舆情') ||
    lower.includes('广告') ||
    lower.includes('转化')
  ) {
    return getRecipeByPreset('marketing');
  }

  if (
    lower.includes('财务') ||
    lower.includes('报销') ||
    lower.includes('发票') ||
    lower.includes('对账') ||
    lower.includes('税') ||
    lower.includes('会计')
  ) {
    return getRecipeByPreset('finance_audit');
  }

  if (
    lower.includes('行政') ||
    lower.includes('公文') ||
    lower.includes('会议') ||
    lower.includes('纪要') ||
    lower.includes('周报') ||
    lower.includes('写作')
  ) {
    return getRecipeByPreset('admin_writing');
  }

  return getRecipeByPreset('custom');
}
