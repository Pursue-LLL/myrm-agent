/**
 * [INPUT]
 * ./eventTypes::PushToast (POS: 全局事件的 toast 能力，error / warning 会对文案与说明做脱敏)
 *
 * [OUTPUT]
 * showSystemNotificationToast: 按服务端声明的级别展示 system_notification 的 toast;
 * SystemNotificationToastDeps: 所需的 toast 能力
 *
 * [POS]
 * 全局事件的系统通知提示。级别由服务端在 meta_data.level 声明（success / info / warning / error），缺省为 success，
 * 因此失败与警告不会被呈现成绿色的成功提示。
 */
import type { PushToast } from './eventTypes';

const LEVELS = ['success', 'info', 'warning', 'error'] as const;
type SystemNotificationLevel = (typeof LEVELS)[number];

const TOAST_DURATION_MS = 10_000;

export interface SystemNotificationToastDeps {
  pushToast: Pick<PushToast, SystemNotificationLevel>;
}

function resolveLevel(value: unknown): SystemNotificationLevel {
  return LEVELS.find((level) => level === value) ?? 'success';
}

/**
 * Toast for a `system_notification`, styled by the level the server declares in `meta.level` (success when absent or
 * unknown). A snapshot-created notice is skipped: the chat window shows it with its own icon.
 */
export function showSystemNotificationToast(
  title: string,
  message: string,
  meta: Record<string, unknown>,
  deps: SystemNotificationToastDeps,
): void {
  if (meta.type === 'snapshot_created') {
    return;
  }
  deps.pushToast[resolveLevel(meta.level)](title, {
    description: message,
    duration: TOAST_DURATION_MS,
    dismissible: true,
  });
}
