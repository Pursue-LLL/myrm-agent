import {
  AmbientDeckSummary,
  BotActivityItem,
  ConversationWithVisibility,
} from './ambientActivityTypes';

/**
 * 根据可见性作用域过滤会话列表，实现机器互聊静默免打扰
 */
export function filterVisibleConversations<
  T extends ConversationWithVisibility,
>(conversations: T[], showHiddenBots: boolean = false): T[] {
  if (showHiddenBots) {
    return conversations;
  }
  return conversations.filter(
    (item) => item.visibilityScope !== 'hidden_bot_peer',
  );
}

/**
 * 汇总多智能体环境态后台协同指标
 */
export function aggregateAmbientActivities(
  activities: BotActivityItem[],
): AmbientDeckSummary {
  if (!activities || activities.length === 0) {
    return {
      activeAgentsCount: 0,
      totalExchangesCount: 0,
      totalTokenCost: 0,
      recentHighlights: [],
    };
  }

  const agentNames = new Set<string>();
  let totalTokenCost = 0;

  for (const item of activities) {
    if (item.sourceAgent) {
      agentNames.add(item.sourceAgent);
    }
    if (item.targetAgent) {
      agentNames.add(item.targetAgent);
    }
    totalTokenCost += Math.max(0, item.tokenCost || 0);
  }

  // 按时间倒序排序提取最新高亮进展（最多 3 条）
  const sorted = [...activities].sort((a, b) => b.timestamp - a.timestamp);
  const recentHighlights = sorted.slice(0, 3).map((item) => {
    return `${item.targetAgent ? `@${item.targetAgent}` : '协同通道'}: ${
      item.actionSummary
    }`;
  });

  return {
    activeAgentsCount: agentNames.size,
    totalExchangesCount: activities.length,
    totalTokenCost,
    recentHighlights,
  };
}

/**
 * 格式化紧凑单行微活动摘要
 */
export function formatMicroActivitySummary(activity: BotActivityItem): string {
  const source = activity.sourceAgent.trim() || 'Agent';
  const target = activity.targetAgent.trim() || 'Agent';
  const action = activity.actionSummary.trim() || '同步协作数据';
  const latency =
    activity.latencyMs > 0 ? ` (${activity.latencyMs}ms)` : '';

  return `[@${source} -> @${target}] ${action}${latency}`;
}
