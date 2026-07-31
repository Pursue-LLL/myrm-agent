/**
 * [INPUT]
 * - @/services/mediaTasks::{fetchMediaTask,getMediaTaskChatId,getMediaTaskPrompt,isMediaTaskType} (POS: media task REST helpers)
 * - @/services/taskEventStream::subscribeTaskUpdateEvents (POS: multiplexed task SSE fan-out)
 * - @/services/notification::notificationService (POS: Web Notification + toast fallback)
 * - @/services/tauriNativeNotification::sendTauriNativeNotification (POS: Tauri desktop native notification helper)
 * - @tauri-apps/api/window::getCurrentWindow (POS: Tauri dock bounce when native notify denied)
 * - @/store/useConfigStore::enableWebNotifications (POS: personal notification preference gate)
 *
 * [OUTPUT]
 * - useGlobalMediaTaskNotifications: terminal media task browser notifications with chat deep links
 *
 * [POS]
 * Global media completion notifier mounted from BackgroundTasksPanel when users leave the originating chat.
 * Tauri hidden window: native notify first; on permission denial, requestUserAttention (dock bounce).
 */

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { isTauriRuntime } from '@/lib/deploy-mode';
import {
  fetchMediaTask,
  getMediaTaskChatId,
  getMediaTaskPrompt,
  isMediaTaskType,
} from '@/services/mediaTasks';
import { subscribeTaskUpdateEvents } from '@/services/taskEventStream';
import { notificationService } from '@/services/notification';
import { sendTauriNativeNotification } from '@/services/tauriNativeNotification';
import useConfigStore from '@/store/useConfigStore';
import type { Task } from '@/store/tasks/types';

function shouldSkipNotification(task: Task): boolean {
  const chatId = getMediaTaskChatId(task.payload);
  if (!chatId || typeof window === 'undefined') {
    return false;
  }
  const onChatPage = window.location.pathname === `/chat/${chatId}`;
  return onChatPage && document.visibilityState === 'visible';
}

function mediaTypeLabel(
  taskType: string,
  translate: (key: 'imageGenerate' | 'videoGenerate') => string,
): string {
  if (taskType === 'video_generate') {
    return translate('videoGenerate');
  }
  return translate('imageGenerate');
}

function isTerminalMediaStatus(status: string | undefined): status is 'succeeded' | 'failed' {
  return status === 'succeeded' || status === 'failed';
}

export function useGlobalMediaTaskNotifications() {
  const router = useRouter();
  const t = useTranslations('backgroundTasks.media');

  useEffect(() => {
    const notifiedTerminalKeys = new Set<string>();
    let disposed = false;

    const notifyIfTerminal = (task: Task) => {
      if (!isMediaTaskType(task.task_type)) {
        return;
      }
      if (task.status !== 'succeeded' && task.status !== 'failed') {
        return;
      }
      if (!useConfigStore.getState().enableWebNotifications) {
        return;
      }
      if (shouldSkipNotification(task)) {
        return;
      }

      const dedupeKey = `${task.task_id}:${task.status}`;
      if (notifiedTerminalKeys.has(dedupeKey)) {
        return;
      }
      notifiedTerminalKeys.add(dedupeKey);

      const typeLabel = mediaTypeLabel(task.task_type, (key) => t(key));
      const title =
        task.status === 'succeeded'
          ? t('completedTitle', { type: typeLabel })
          : t('failedTitle', { type: typeLabel });
      const prompt = getMediaTaskPrompt(task.payload);
      const body =
        task.status === 'failed'
          ? task.error?.message || prompt || t('unknownError')
          : prompt || undefined;
      const chatId = getMediaTaskChatId(task.payload);

      void (async () => {
        if (
          isTauriRuntime() &&
          typeof document !== 'undefined' &&
          document.visibilityState === 'hidden'
        ) {
          const sent = await sendTauriNativeNotification({ title, body });
          if (sent) {
            return;
          }
          try {
            const { getCurrentWindow } = await import('@tauri-apps/api/window');
            await getCurrentWindow().requestUserAttention(2);
          } catch {
            // Non-critical — attention API unavailable
          }
          return;
        }

        notificationService.notify(title, {
          body,
          onClick: chatId ? () => router.push(`/chat/${chatId}`) : undefined,
        });
      })();
    };

    return subscribeTaskUpdateEvents((eventData) => {
      if (eventData.sync_required) {
        return;
      }
      if (!eventData.task_id) {
        return;
      }
      if (eventData.task_type && !isMediaTaskType(eventData.task_type)) {
        return;
      }
      if (eventData.status && !isTerminalMediaStatus(eventData.status)) {
        return;
      }

      void fetchMediaTask(eventData.task_id).then((task) => {
        if (!task || disposed) {
          return;
        }
        notifyIfTerminal(task);
      });
    });
  }, [router, t]);
}
