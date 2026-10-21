import {
  OfficeWorkspaceMode,
  OfficeModeMetadata,
  ModeSecurityPolicy,
  WriteIntentDetectionResult,
} from './threeModeTypes';

export const OFFICE_MODES: Record<OfficeWorkspaceMode, OfficeModeMetadata> = {
  ask: {
    id: 'ask',
    title: 'Ask 问一问',
    subTitle: '只读问答',
    tagline: '不改文件，安全阅读',
    description: '严格只读模式。Agent 仅能阅读已授权的资料、解释代码与分析文档，绝对禁止任何文件修改和系统写入。',
    policy: {
      readOnly: true,
      requirePlanApproval: false,
      allowFileWrites: false,
      allowShellExecution: false,
      bypassConfirmations: false,
    },
    recommendedFor: '阅读合同、查询知识库、理清思路、新手体验',
    shortcut: '1',
    badgeBg: 'bg-emerald-950/60',
    badgeText: 'text-emerald-300',
    badgeBorder: 'border-emerald-800/60',
  },
  plan: {
    id: 'plan',
    title: 'Plan 想一想',
    subTitle: '出计划再执行',
    tagline: '先审计划，满意才动手',
    description: '审慎规划模式。Agent 先行通读上下文并输出结构化执行计划（Step-by-Step），待您审查确认后方可实施。',
    policy: {
      readOnly: false,
      requirePlanApproval: true,
      allowFileWrites: false,
      allowShellExecution: false,
      bypassConfirmations: false,
    },
    recommendedFor: '多步骤复杂重构、方案选型、大型文件迁移',
    shortcut: '2',
    badgeBg: 'bg-indigo-950/60',
    badgeText: 'text-indigo-300',
    badgeBorder: 'border-indigo-800/60',
  },
  craft: {
    id: 'craft',
    title: 'Craft 做一做',
    subTitle: '全自动执行',
    tagline: '高效落地，直接产出',
    description: '自动化操作模式。Agent 具备文件读写、指令执行与生成交付工件的全流程自主权，高效闭环。',
    policy: {
      readOnly: false,
      requirePlanApproval: false,
      allowFileWrites: true,
      allowShellExecution: true,
      bypassConfirmations: true,
    },
    recommendedFor: '确定性任务、日常脚本编写、批量图文产出',
    shortcut: '3',
    badgeBg: 'bg-amber-950/60',
    badgeText: 'text-amber-300',
    badgeBorder: 'border-amber-800/60',
  },
};

/**
 * 获取指定模式的安全权限策略
 */
export function resolveModeSecurityPolicy(mode: OfficeWorkspaceMode): ModeSecurityPolicy {
  return OFFICE_MODES[mode].policy;
}

const WRITE_INTENT_KEYWORDS = [
  '保存到',
  '创建文件',
  '新建文件',
  '写入',
  '修改文件',
  '帮我改下',
  '导出到',
  '重构并保存',
  '运行代码',
  '执行脚本',
  '部署上线',
  'commit',
  'overwrite',
];

/**
 * 职场新手防误触检测：在 Ask 模式下输入写意图时，温和检测并给出指引
 */
export function detectWriteIntentInAskMode(
  userInput: string,
  currentMode: OfficeWorkspaceMode
): WriteIntentDetectionResult {
  if (currentMode !== 'ask') {
    return {
      hasWriteIntent: false,
      matchedKeywords: [],
      suggestedMode: currentMode,
      guidanceMessage: '',
    };
  }

  const normalized = userInput.toLowerCase();
  const matched = WRITE_INTENT_KEYWORDS.filter((keyword) =>
    normalized.includes(keyword.toLowerCase())
  );

  if (matched.length > 0) {
    return {
      hasWriteIntent: true,
      matchedKeywords: matched,
      suggestedMode: 'craft',
      guidanceMessage: `检测到您的指令中包含写操作意图（如“${matched[0]}”）。当前处于严格只读的「Ask 问一问」模式，是否一键切换到「⚡ Craft 做一做」以允许智能体直接修改文件？`,
    };
  }

  return {
    hasWriteIntent: false,
    matchedKeywords: [],
    suggestedMode: 'ask',
    guidanceMessage: '',
  };
}
