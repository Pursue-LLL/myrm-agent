import {
  ChatTurnItem,
  LineageFilterMode,
  OriginVisualTheme,
  TurnOriginType,
} from './turnLineageTypes';

/**
 * 触发源视觉主题配置字典
 */
export const ORIGIN_VISUAL_CONFIG: Record<TurnOriginType, OriginVisualTheme> = {
  user_direct: {
    label: '人工直接指令',
    badgeBg: 'bg-slate-800/80',
    badgeText: 'text-slate-200',
    badgeBorder: 'border-slate-700',
    dotColor: 'bg-slate-400',
    description: '由人类用户在输入框中主动敲击回车或发送的消息轮次',
  },
  cron_job: {
    label: '定时调度任务',
    badgeBg: 'bg-purple-950/60',
    badgeText: 'text-purple-300',
    badgeBorder: 'border-purple-800/60',
    dotColor: 'bg-purple-400',
    description: '由后台 Cron 调度引擎（如每小时同步、健康心跳探测）周期性激活触发',
  },
  webhook_trigger: {
    label: '外部 Webhook',
    badgeBg: 'bg-amber-950/60',
    badgeText: 'text-amber-300',
    badgeBorder: 'border-amber-800/60',
    dotColor: 'bg-amber-400',
    description: '由外部 GitHub PR、CI/CD 告警或第三方系统推送的回调事件触发',
  },
  subagent_delegation: {
    label: '智能体移交',
    badgeBg: 'bg-indigo-950/60',
    badgeText: 'text-indigo-300',
    badgeBorder: 'border-indigo-800/60',
    dotColor: 'bg-indigo-400',
    description: '由上游主管智能体（Orchestrator）向子智能体（如 Coder/Reviewer）派发移交的步骤',
  },
  approval_resume: {
    label: '审批放行恢复',
    badgeBg: 'bg-emerald-950/60',
    badgeText: 'text-emerald-300',
    badgeBorder: 'border-emerald-800/60',
    dotColor: 'bg-emerald-400',
    description: '在关键高危操作挂起后，经人类管理员点击确认批准恢复执行的轮次',
  },
};

export function getOriginVisualTheme(originType: TurnOriginType): OriginVisualTheme {
  return ORIGIN_VISUAL_CONFIG[originType] || ORIGIN_VISUAL_CONFIG.user_direct;
}

/**
 * 按审计过滤模式筛选轮次
 */
export function filterTurns(
  turns: ChatTurnItem[],
  mode: LineageFilterMode
): ChatTurnItem[] {
  if (mode === 'all') {
    return turns;
  }
  if (mode === 'user_only') {
    return turns.filter((t) => t.provenance.originType === 'user_direct');
  }
  if (mode === 'automated_only') {
    return turns.filter(
      (t) =>
        t.provenance.originType === 'cron_job' ||
        t.provenance.originType === 'webhook_trigger'
    );
  }
  if (mode === 'handoff_only') {
    return turns.filter(
      (t) =>
        t.provenance.originType === 'subagent_delegation' ||
        t.provenance.originType === 'approval_resume'
    );
  }
  return turns;
}

/**
 * 沿 causalityParentId 追溯因果关系链
 */
export function traceCausalityLineage(
  turnId: string,
  turns: ChatTurnItem[]
): string[] {
  const turnMap = new Map<string, ChatTurnItem>();
  for (const t of turns) {
    turnMap.set(t.id, t);
  }

  const chain: string[] = [];
  let current: ChatTurnItem | undefined = turnMap.get(turnId);

  while (current) {
    chain.unshift(current.id);
    if (!current.provenance.causalityParentId) {
      break;
    }
    current = turnMap.get(current.provenance.causalityParentId);
  }

  return chain;
}

/**
 * 默认示范多源协同任务流数据
 */
export function getDefaultTurns(): ChatTurnItem[] {
  return [
    {
      id: 'turn-1',
      turnNumber: 1,
      role: 'user',
      author: '人类管理员',
      content: '请协助审计当前系统所有技能依赖并生成每日排障与优化建议。',
      provenance: {
        originType: 'user_direct',
        originRefId: 'manual-input-001',
        triggerSourceTitle: '用户控制台手动输入',
        executedByAgent: 'Human',
        timestamp: '10:00:02',
      },
      tokensUsed: 45,
      durationMs: 0,
    },
    {
      id: 'turn-2',
      turnNumber: 2,
      role: 'assistant',
      author: 'Arch-Master-4o',
      content: '收到指令，正在调度后台诊断与技能扫描管线进行深度健康巡检。',
      provenance: {
        originType: 'user_direct',
        originRefId: 'turn-1',
        triggerSourceTitle: '响应用户指令',
        executedByAgent: 'Arch-Master-4o',
        timestamp: '10:00:04',
        causalityParentId: 'turn-1',
      },
      tokensUsed: 420,
      durationMs: 1200,
    },
    {
      id: 'turn-3',
      turnNumber: 3,
      role: 'assistant',
      author: 'Cron-Scheduler',
      content: '[定时同步调度] hourly_skill_sync 触发：扫描到 2 个待升级依赖与 1 个僵死进程。',
      provenance: {
        originType: 'cron_job',
        originRefId: 'cron:hourly_skill_sync',
        triggerSourceTitle: '定时任务: hourly_skill_sync (每整点激活)',
        executedByAgent: 'Cron-Scheduler',
        timestamp: '10:00:15',
        details: { schedule: '0 * * * *', runner: 'BackgroundDaemon' },
      },
      tokensUsed: 680,
      durationMs: 2400,
    },
    {
      id: 'turn-4',
      turnNumber: 4,
      role: 'assistant',
      author: 'Arch-Master-4o',
      content: '检测到高风险系统补丁写入，已将修改方案委派给安全审计子智能体。',
      provenance: {
        originType: 'subagent_delegation',
        originRefId: 'delegation:sec-audit-99',
        triggerSourceTitle: '智能体委派: Arch-Master-4o -> Security-Guard',
        executedByAgent: 'Security-Guard',
        timestamp: '10:00:22',
        causalityParentId: 'turn-3',
      },
      tokensUsed: 1120,
      durationMs: 3100,
    },
    {
      id: 'turn-5',
      turnNumber: 5,
      role: 'assistant',
      author: 'Security-Guard',
      content: '高危文件更新拦截：需要人类高管决策批准后方可执行覆盖写入。',
      provenance: {
        originType: 'approval_resume',
        originRefId: 'approval-req-771',
        triggerSourceTitle: '审批流恢复: 生产环境配置写入放行',
        executedByAgent: 'Executive-Approver',
        timestamp: '10:01:05',
        causalityParentId: 'turn-4',
      },
      tokensUsed: 390,
      durationMs: 800,
    },
    {
      id: 'turn-6',
      turnNumber: 6,
      role: 'assistant',
      author: 'Webhook-Receiver',
      content: '[外部 Webhook] 收到 GitHub PR #142 合并事件，触发自动化回归测试。',
      provenance: {
        originType: 'webhook_trigger',
        originRefId: 'webhook:github:pr-142',
        triggerSourceTitle: '外部 Webhook: GitHub Push & Merge Event',
        executedByAgent: 'CI-Runner',
        timestamp: '10:01:40',
        details: { repo: 'open-perplexity/myrm-agent', prNumber: '142' },
      },
      tokensUsed: 520,
      durationMs: 1500,
    },
  ];
}
