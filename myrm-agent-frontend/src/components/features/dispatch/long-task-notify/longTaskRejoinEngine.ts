import { LongTaskDispatchTicket } from './longTaskNotifyTypes';

export function formatTaskDuration(seconds: number): string {
  if (seconds <= 0) {
    return '0秒';
  }

  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);

  if (mins > 0 && secs > 0) {
    return `${mins}分${secs}秒`;
  }
  if (mins > 0) {
    return `${mins}分钟`;
  }
  return `${secs}秒`;
}

export interface EstimatedCompletionInfo {
  etaTimestamp: number;
  etaFormatted: string;
  remainingSec: number;
}

export function calculateEstimatedCompletionTime(
  startedAt: number,
  durationSec: number,
  now = Date.now()
): EstimatedCompletionInfo {
  const etaTimestamp = startedAt + durationSec * 1000;
  const remainingMs = etaTimestamp - now;
  const remainingSec = Math.max(0, Math.ceil(remainingMs / 1000));

  const etaDate = new Date(etaTimestamp);
  const hours = String(etaDate.getHours()).padStart(2, '0');
  const minutes = String(etaDate.getMinutes()).padStart(2, '0');
  const etaFormatted = `${hours}:${minutes}`;

  return {
    etaTimestamp,
    etaFormatted,
    remainingSec,
  };
}

export interface RejoinDeltaResult {
  missedCount: number;
  needsCatchup: boolean;
}

export function computeRejoinDelta(
  lastSyncTimestamp: number,
  currentEvents: Array<{ timestamp: number }>
): RejoinDeltaResult {
  if (currentEvents.length === 0) {
    return { missedCount: 0, needsCatchup: false };
  }

  const missed = currentEvents.filter((e) => e.timestamp > lastSyncTimestamp);
  return {
    missedCount: missed.length,
    needsCatchup: missed.length > 0,
  };
}

export interface SimulatedPushPayload {
  title: string;
  body: string;
  deepLink: string;
  tag: string;
}

export function simulatePushNotificationPayload(
  ticket: LongTaskDispatchTicket
): SimulatedPushPayload {
  const count = ticket.sourcedChecklist.length;
  const title = `长任务已完成: ${ticket.title}`;
  const body = `沙箱后台已生成带来源权威清单 (${count} 条核验产物)，点击立即直达复盘。`;
  const deepLink = `myrm://session/rejoin?task=${ticket.taskId}`;
  const tag = `task-notify-${ticket.taskId}`;

  return {
    title,
    body,
    deepLink,
    tag,
  };
}
