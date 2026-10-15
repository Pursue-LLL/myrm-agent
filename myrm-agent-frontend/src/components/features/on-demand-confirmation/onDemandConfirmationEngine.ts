import {
  OptionLetterId,
  ConfirmationOptionItem,
  OnDemandDecisionInterrupt,
  ConfirmationDecisionResult,
  NineEntryNavItem,
} from './onDemandConfirmationTypes';

/**
 * 键盘按键映射为选项字母 (1-6 或 A-F)
 */
export function mapKeyToOptionLetter(
  key: string,
  availableOptions: ConfirmationOptionItem[]
): OptionLetterId | null {
  const normalized = key.toUpperCase();
  const digitMap: Record<string, OptionLetterId> = {
    '1': 'A',
    '2': 'B',
    '3': 'C',
    '4': 'D',
    '5': 'E',
    '6': 'F',
  };

  const targetLetter: OptionLetterId | null =
    digitMap[key] || (['A', 'B', 'C', 'D', 'E', 'F'].includes(normalized) ? (normalized as OptionLetterId) : null);

  if (!targetLetter) {
    return null;
  }

  const exists = availableOptions.some((opt) => opt.id === targetLetter);
  if (!exists) {
    return null;
  }

  return targetLetter;
}

/**
 * 组装决策确认结果负载
 */
export function buildDecisionResult(
  interrupt: OnDemandDecisionInterrupt,
  selectedId: OptionLetterId,
  customInput?: string
): ConfirmationDecisionResult {
  const matched = interrupt.options.find((opt) => opt.id === selectedId);
  const label = matched ? matched.label : `选项 ${selectedId}`;

  return {
    interruptId: interrupt.interruptId,
    taskId: interrupt.taskId,
    selectedOptionId: selectedId,
    selectedOptionLabel: label,
    customInput: customInput?.trim() ? customInput.trim() : undefined,
    decidedAt: new Date().toISOString(),
  };
}

/**
 * 预设的全功能九大入口导航列表定义
 */
export const NINE_ENTRY_NAV_ITEMS: NineEntryNavItem[] = [
  {
    id: 'new_task',
    label: '新工作任务',
    description: '启动高自主性长程任务编排',
    shortcut: 'Cmd+N',
    category: 'lifecycle',
    badge: 'NEW',
  },
  {
    id: 'cron_jobs',
    label: '定时任务',
    description: 'Crontab 与周期巡检工作流',
    shortcut: 'Cmd+T',
    category: 'lifecycle',
  },
  {
    id: 'main_chat',
    label: '主对话中枢',
    description: '人机实时交互与通用问答',
    shortcut: 'Cmd+1',
    category: 'lifecycle',
  },
  {
    id: 'skills_mcp',
    label: '技能与连接器',
    description: 'MCP 协议扩展与技能目录',
    shortcut: 'Cmd+K',
    category: 'collaboration',
  },
  {
    id: 'agents',
    label: '伙伴对话',
    description: '多智能体 Swarm 协同网络',
    shortcut: 'Cmd+A',
    category: 'collaboration',
  },
  {
    id: 'mobile_pair',
    label: '手机遥控电脑',
    description: '移动端配对与跨端协同',
    shortcut: 'Cmd+M',
    category: 'collaboration',
    badge: 'LIVE',
  },
  {
    id: 'drive_projects',
    label: '云盘与资料空间',
    description: '项目知识库与交付工件归档',
    shortcut: 'Cmd+D',
    category: 'assets',
  },
  {
    id: 'kanban_roadmap',
    label: '方案与项目看板',
    description: '任务里程碑与甘特图流转',
    shortcut: 'Cmd+B',
    category: 'assets',
  },
  {
    id: 'recent_history',
    label: '最近历史',
    description: '快照版本与会话审计流水',
    shortcut: 'Cmd+H',
    category: 'assets',
  },
];
