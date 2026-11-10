/**
 * [INPUT]
 * - @/services/backgroundTasksRefresh (POS: 后台任务列表刷新通知)
 * - ./memoryOperationToasts / locatorHealedToast / kanbanTaskToast / reauthToasts / subsumptionUndoToast (POS: 各事件的 toast)
 *
 * [OUTPUT]
 * - systemEventHandlers: 空闲状态 / 运行摘要 / 系统通知 / 记忆 / 定位器自愈 / 重新授权 / 看板事件的处理器表
 *
 * [POS]
 * 全局事件中与后台运行状态相关的部分：把事件转给订阅它的页面，并在需要时提示用户。
 */
import { showKanbanTaskToast } from '@/hooks/globalEvents/kanbanTaskToast';
import { showLocatorHealedToast } from '@/hooks/globalEvents/locatorHealedToast';
import { showMemoryOperationToasts } from '@/hooks/globalEvents/memoryOperationToasts';
import { showMcpAuthRequiredToast, showOAuthReauthRequiredToast } from '@/hooks/globalEvents/reauthToasts';
import { showSubsumptionUndoToast } from '@/hooks/globalEvents/subsumptionUndoToast';
import {
  notifyBackgroundTasksChangedForShellJobFinish,
  notifyBackgroundTasksChangedForVoiceJobFinish,
} from '@/services/backgroundTasksRefresh';
import { asRecord } from '@/lib/utils/typeUtils';

import type { GlobalEventHandler } from './eventTypes';

const handleIdleStatus: GlobalEventHandler = (payload, { t, tIdle, pushToast }) => {
  window.dispatchEvent(
    new CustomEvent('idle-status', {
      detail: payload.data,
    }),
  );
  showSubsumptionUndoToast(payload.data, { t, tIdle, pushToast });
};

const handleRunDigestUpdated: GlobalEventHandler = (payload) => {
  const data = asRecord(payload.data);
  const chatId = typeof data.chat_id === 'string' ? data.chat_id : '';
  const digest = asRecord(data.digest);
  window.dispatchEvent(
    new CustomEvent('run-digest-updated', {
      detail: { chat_id: chatId, digest: Object.keys(digest).length ? digest : undefined },
    }),
  );
};

const handleSystemNotification: GlobalEventHandler = (payload, { t, pushToast }) => {
  const title = String(payload.data.title ?? t('systemNotificationTitle'));
  const message = String(payload.data.message ?? '');
  const meta = asRecord(payload.data.meta_data);

  // Dispatch a custom event so specific components (like ChatWindow) can handle it
  window.dispatchEvent(new CustomEvent('system-notification', { detail: payload }));

  if (meta.kind === 'background_job_finish' && typeof meta.chat_id === 'string' && meta.chat_id.trim()) {
    void import('@/store/chat/goals/useGoalStore').then(({ useGoalStore }) => {
      void useGoalStore.getState().refreshActiveGoal(meta.chat_id as string);
    });
    notifyBackgroundTasksChangedForShellJobFinish(meta);
  }
  if (meta.kind === 'voice_background_task_done') {
    notifyBackgroundTasksChangedForVoiceJobFinish(meta);
    const announceChatId = typeof meta.chat_id === 'string' ? meta.chat_id : '';
    if (announceChatId) {
      window.dispatchEvent(
        new CustomEvent('voice-bg-done', {
          detail: { title, message, chat_id: announceChatId },
        }),
      );
    }
  }

  // Only show global toast if it's not a snapshot_created event
  // (snapshot_created is handled specifically by ChatWindow with a custom icon)
  if (meta.type !== 'snapshot_created') {
    pushToast.success(title, {
      description: message,
      duration: 10_000,
      dismissible: true,
    });
  }
};

const handleMemoryOperation: GlobalEventHandler = (payload, { t, router }) => {
  showMemoryOperationToasts(payload.data, { t, router });
  window.dispatchEvent(new CustomEvent(payload.type, { detail: payload.data }));
};

const handleLocatorHealed: GlobalEventHandler = (payload, { t }) => {
  showLocatorHealedToast(payload.data, { t });
  window.dispatchEvent(new CustomEvent(payload.type, { detail: payload.data }));
};

const handleMcpAuthRequired: GlobalEventHandler = (payload, { t, router, pushToast, notifyIfLeader }) => {
  showMcpAuthRequiredToast(payload.data, { t, router, toast: pushToast, notifyIfLeader });
};

const handleOAuthReauthRequired: GlobalEventHandler = (payload, { t, router, pushToast, notifyIfLeader }) => {
  showOAuthReauthRequiredToast(payload.data, { t, router, toast: pushToast, notifyIfLeader });
};

const handleKanbanTaskUpdated: GlobalEventHandler = (payload, { t, tKanban, router, pushToast, notifyIfLeader }) => {
  showKanbanTaskToast(payload.data, { t, tKanban, router, pushToast, notifyIfLeader });
  window.dispatchEvent(new CustomEvent('kanban-task-updated', { detail: payload.data }));
};

export const systemEventHandlers: Record<string, GlobalEventHandler> = {
  idle_status: handleIdleStatus,
  run_digest_updated: handleRunDigestUpdated,
  system_notification: handleSystemNotification,
  memory_operation: handleMemoryOperation,
  locator_healed: handleLocatorHealed,
  mcp_auth_required: handleMcpAuthRequired,
  oauth_reauth_required: handleOAuthReauthRequired,
  kanban_task_updated: handleKanbanTaskUpdated,
};
