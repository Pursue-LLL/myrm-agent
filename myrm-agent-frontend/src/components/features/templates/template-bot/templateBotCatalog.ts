/**
 * TemplateBot Built-In Catalog & Team Roster Presets
 * 预置岗位智能体库、团队模板预设与检索纯函数工具
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 纯函数设计，高可测性。
 */

import {
  TeamRosterTemplate,
  TemplateBotRole,
  TemplateRoleCategory,
} from './templateBotTypes';

export const BUILT_IN_TEMPLATE_BOTS: readonly TemplateBotRole[] = [
  {
    id: 'bot-chief-of-staff',
    name: '首席幕僚长 (Chief of Staff)',
    category: 'management',
    department: 'Executive Office',
    avatarBadge: 'CoS',
    summary: '复杂多项目全局拆解、智能体团队调度分工与关键里程碑纠偏总控。',
    defaultSystemPrompt:
      '你是一名拥有硅谷顶尖科技企业视野的首席幕僚长。你的职责是将模糊长程目标拆解为可度量的子任务，协调下属各岗位智能体并维持全局上下文对齐。',
    recommendedSkillIds: ['task-planner', 'team-orchestrator', 'milestone-tracker'],
    defaultTools: ['schedule_task', 'invoke_subagent', 'read_transcript'],
    maxContextTokens: 128000,
    author: 'Myrm Core Lab',
    starsCount: 3820,
  },
  {
    id: 'bot-senior-architect',
    name: '资深全栈架构师 (Lead Architect)',
    category: 'engineering',
    department: 'Engineering Core',
    avatarBadge: 'ARCH',
    summary: '主导分布式系统设计、技术选型把关、性能瓶颈排查与纯净无债重构。',
    defaultSystemPrompt:
      '你是一名世界顶尖的软件架构师与全栈工程专家。追求极致性能、单文件行数受控、零 any、全强类型与纯净重构。',
    recommendedSkillIds: ['code-analyzer', 'performance-profiler', 'dag-engine'],
    defaultTools: ['run_command', 'replace_file_content', 'view_file'],
    maxContextTokens: 200000,
    author: 'Myrm Core Lab',
    starsCount: 4210,
  },
  {
    id: 'bot-fullstack-engineer',
    name: '全栈交付专家 (Fullstack Engineer)',
    category: 'engineering',
    department: 'Engineering Core',
    avatarBadge: 'ENG',
    summary: '高质量代码编写、极不友好 Code Review 规范遵从与双门禁单测全绿交付。',
    defaultSystemPrompt:
      '你是一名资深全栈开发工程师。所有前端 if 显式加括号，无原生 emoji，遵循 a11y 标准与 Vitest 100% 覆盖。',
    recommendedSkillIds: ['git-guard', 'vitest-runner', 'oxlint-shield'],
    defaultTools: ['write_to_file', 'replace_file_content', 'run_command'],
    maxContextTokens: 128000,
    author: 'Open Source Community',
    starsCount: 2950,
  },
  {
    id: 'bot-market-researcher',
    name: '深度行业研究员 (Lead Researcher)',
    category: 'research',
    department: 'Market Intelligence',
    avatarBadge: 'RES',
    summary: '全网技术雷达、开源竞品源码穿透核查与证据驱动型深度分析报告。',
    defaultSystemPrompt:
      '你是一名资深技术与商业分析专家。杜绝未经证实的猜测，所有结论必须以证据为支撑，提供代码行级或文献级引用。',
    recommendedSkillIds: ['web-search', 'paper-fetcher', 'citation-verifier'],
    defaultTools: ['search_web', 'read_url_content', 'view_file'],
    maxContextTokens: 128000,
    author: 'Research Foundation',
    starsCount: 2180,
  },
  {
    id: 'bot-financial-analyst',
    name: '算力与财务分析师 (Cost & Quota Analyst)',
    category: 'finance',
    department: 'Finance & Ops',
    avatarBadge: 'CFO',
    summary: '模型提供商配额透视、Token 消耗 ROI 分析与日均燃尽速率预算测算。',
    defaultSystemPrompt:
      '你是一名专注于 AI 基础设施 Token 经济学与财务预算的专家。精确度量模型投入产出比，预防欠费突发事故。',
    recommendedSkillIds: ['quota-tracker', 'budget-guard', 'roi-calculator'],
    defaultTools: ['call_mcp_tool', 'view_file'],
    maxContextTokens: 64000,
    author: 'FinOps Alliance',
    starsCount: 1670,
  },
  {
    id: 'bot-qa-director',
    name: '质量与混沌总监 (QA & Reliability Lead)',
    category: 'operations',
    department: 'Reliability Engineering',
    avatarBadge: 'QA',
    summary: '高危边缘测试覆盖、自动化端到端验收与生产环境抗脆弱防线构建。',
    defaultSystemPrompt:
      '你是一名最挑剔的质量总监。以破坏者视角攻击系统潜在漏洞，确保边界情况无崩溃、高可用。',
    recommendedSkillIds: ['e2e-tester', 'chaos-monkey', 'a11y-auditor'],
    defaultTools: ['run_command', 'view_file'],
    maxContextTokens: 128000,
    author: 'Myrm Core Lab',
    starsCount: 1940,
  },
];

export const BUILT_IN_TEAM_ROSTERS: readonly TeamRosterTemplate[] = [
  {
    teamId: 'team-tech-delivery',
    teamName: '全栈工程交付突击队 (Engineering Strike Squad)',
    description: '由首席幕僚长、资深架构师、全栈工程师与质量总监构成的企业级软件快速攻坚阵容。',
    category: 'engineering',
    roles: [
      BUILT_IN_TEMPLATE_BOTS[0], // CoS
      BUILT_IN_TEMPLATE_BOTS[1], // Architect
      BUILT_IN_TEMPLATE_BOTS[2], // Fullstack
      BUILT_IN_TEMPLATE_BOTS[5], // QA
    ],
    collaborationTopology: 'hierarchical',
    estimatedTokenBudgetMultiplier: 2.5,
  },
  {
    teamId: 'team-market-intel',
    teamName: '深度商业与技术情报团队 (Market Intelligence)',
    description: '由幕僚长统筹，研究员负责穿透核实，财务分析师提供投产比与算力经济学精算。',
    category: 'research',
    roles: [
      BUILT_IN_TEMPLATE_BOTS[0], // CoS
      BUILT_IN_TEMPLATE_BOTS[3], // Researcher
      BUILT_IN_TEMPLATE_BOTS[4], // Financial
    ],
    collaborationTopology: 'pipeline',
    estimatedTokenBudgetMultiplier: 1.8,
  },
  {
    teamId: 'team-ops-shield',
    teamName: '高可靠生产守护团队 (Production Reliability Shield)',
    description: '架构师与质量总监双向协同审查，结合财务分析师监控云端配额与突发熔断。',
    category: 'operations',
    roles: [
      BUILT_IN_TEMPLATE_BOTS[1], // Architect
      BUILT_IN_TEMPLATE_BOTS[4], // Financial
      BUILT_IN_TEMPLATE_BOTS[5], // QA
    ],
    collaborationTopology: 'peer_swarm',
    estimatedTokenBudgetMultiplier: 1.4,
  },
];

/**
 * 筛选模板岗位智能体
 */
export function filterTemplateBots(
  category?: TemplateRoleCategory,
  keyword?: string
): TemplateBotRole[] {
  return BUILT_IN_TEMPLATE_BOTS.filter((bot) => {
    if (category && bot.category !== category) {
      return false;
    }
    if (keyword && keyword.trim() !== '') {
      const kw = keyword.toLowerCase().trim();
      const matchName = bot.name.toLowerCase().includes(kw);
      const matchSummary = bot.summary.toLowerCase().includes(kw);
      const matchDept = bot.department.toLowerCase().includes(kw);
      return matchName || matchSummary || matchDept;
    }
    return true;
  });
}

/**
 * 根据 ID 查询单 Bot 模板
 */
export function getTemplateBotById(botId: string): TemplateBotRole | null {
  for (const bot of BUILT_IN_TEMPLATE_BOTS) {
    if (bot.id === botId) {
      return bot;
    }
  }
  return null;
}

/**
 * 根据 ID 查询团队模板预设
 */
export function getTeamRosterById(teamId: string): TeamRosterTemplate | null {
  for (const roster of BUILT_IN_TEAM_ROSTERS) {
    if (roster.teamId === teamId) {
      return roster;
    }
  }
  return null;
}
