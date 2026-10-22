/**
 * 跨端统一「需要你」中断队列与可锚定后台告警套件 - 纯函数计算引擎
 *
 * 负责中断源归并、优先级时间权重排序、离线告警窗口聚合以及向四泳道模型无缝转换。
 */

import type {
  AnchoredAlert,
  NeedsYouItem,
  NeedsYouQueueSummary,
  NeedsYouTaskItem,
} from './needsYouTypes';

export const DEFAULT_OFFLINE_MERGE_WINDOW_MS = 600_000; // 10 分钟合并窗口

/**
 * 针对活跃待办按紧急程度与等待时长双重排序
 */
export function sortNeedsYouQueue(items: NeedsYouItem[], now: number = Date.now()): NeedsYouItem[] {
  const activeItems = items.filter((item) => !item.isHandled && !item.isDismissed);

  const urgencyWeight: Record<string, number> = {
    urgent: 3,
    normal: 2,
    low: 1,
  };

  return [...activeItems].sort((a, b) => {
    const weightA = urgencyWeight[a.urgency] ?? 1;
    const weightB = urgencyWeight[b.urgency] ?? 1;

    if (weightA !== weightB) {
      return weightB - weightA;
    }

    const waitA = now - a.createdAt;
    const waitB = now - b.createdAt;
    return waitB - waitA;
  });
}

/**
 * 将「需要你」待办项映射转换为既有四泳道任务项模型
 */
export function mapNeedsYouToWorkspaceTaskItems(
  items: NeedsYouItem[],
  now: number = Date.now(),
): NeedsYouTaskItem[] {
  return items.map((item) => {
    const waitingMs = Math.max(0, now - item.createdAt);

    return {
      id: item.id,
      title: item.title,
      swimlane: 'needs-you',
      status: item.isHandled ? 'success' : 'waiting_approval',
      chatId: item.chatId,
      agentId: item.agentId,
      agentName: item.agentName,
      updatedAt: item.createdAt,
      waitingDurationMs: waitingMs,
      latestOutputTail: item.whatWaitingFor,
      errorReason: item.whyStopped,
    };
  });
}

/**
 * 锁屏或离线期间的后台告警窗口聚合去重，避免用户恢复视窗时被多条重复弹窗刷屏
 */
export function deduplicateAndMergeAlerts(
  alerts: AnchoredAlert[],
  mergeWindowMs: number = DEFAULT_OFFLINE_MERGE_WINDOW_MS,
): AnchoredAlert[] {
  if (alerts.length <= 1) {
    return alerts;
  }

  const sorted = [...alerts].sort((a, b) => a.timestamp - b.timestamp);
  const result: AnchoredAlert[] = [];

  for (const alert of sorted) {
    const last = result[result.length - 1];

    if (
      last &&
      last.source === alert.source &&
      Math.abs(alert.timestamp - last.timestamp) <= mergeWindowMs
    ) {
      // 在同一时间窗口内存在相同来源告警，进行摘要合并并更新最新时间戳
      last.summary = `${last.summary}; ${alert.summary}`;
      last.timestamp = Math.max(last.timestamp, alert.timestamp);
      last.isRead = last.isRead && alert.isRead;
      last.deepLinkUrl = alert.deepLinkUrl;
    } else {
      result.push({ ...alert });
    }
  }

  return result;
}

/**
 * 构建可锚定深链 URL，支持跳转至指定会话、消息及当前待办条目锚点
 */
export function buildNeedsYouDeepLink(
  chatId: string,
  messageId?: string,
  turnId?: number,
  itemId?: string,
): string {
  const params = new URLSearchParams();
  if (messageId) {
    params.set('msg', messageId);
  }
  if (turnId !== undefined) {
    params.set('turn', String(turnId));
  }
  const queryString = params.toString();
  const base = `/chat/${chatId}${queryString ? `?${queryString}` : ''}`;
  return itemId ? `${base}#needs-you?item=${itemId}` : base;
}

/**
 * 汇总当前中断队列统计数据
 */
export function calculateQueueSummary(
  items: NeedsYouItem[],
  alerts: AnchoredAlert[],
  now: number = Date.now(),
): NeedsYouQueueSummary {
  const activeItems = items.filter((item) => !item.isHandled && !item.isDismissed);

  let urgentCount = 0;
  let normalCount = 0;
  let longestWaitingMs = 0;

  for (const item of activeItems) {
    if (item.urgency === 'urgent') {
      urgentCount++;
    } else {
      normalCount++;
    }

    const wait = Math.max(0, now - item.createdAt);
    if (wait > longestWaitingMs) {
      longestWaitingMs = wait;
    }
  }

  const unreadAlertCount = alerts.filter((a) => !a.isRead).length;

  return {
    totalPendingCount: activeItems.length,
    urgentCount,
    normalCount,
    longestWaitingMs,
    unreadAlertCount,
  };
}
