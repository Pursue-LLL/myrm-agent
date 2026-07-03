/**
 * [INPUT]
 * @/store/useChatStore::useChatStore (POS: Chat conversation state store)
 * @/lib/deploy-mode::isTauriRuntime (POS: Deployment mode detector)
 * @/services/background-tasks::listBackgroundTasks (POS: merged shell + agent tasks)
 * @/services/backgroundTasksRefresh::subscribeBackgroundTasksChanged
 *
 * [OUTPUT]
 * useTrayStatus: Synchronizes Tauri tray tooltip, taskbar progress bar,
 * and completion bounce notification with chat streaming and background jobs.
 *
 * [POS]
 * Desktop tray bridge hook. Mirrors chat generation state and in-process shell /
 * Kanban background running counts to the system tray and taskbar progress bar.
 * Fires user-attention when chat generation or a background job finishes while
 * the window is not focused. Inert in non-Tauri environments.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { isTauriRuntime } from '@/lib/deploy-mode';
import useChatStore from '@/store/useChatStore';
import { listBackgroundTasks } from '@/services/background-tasks';
import { subscribeBackgroundTasksChanged } from '@/services/backgroundTasksRefresh';

type SystemNotificationDetail = {
  data?: {
    meta_data?: {
      kind?: string;
    };
  };
};

export function useTrayStatus() {
  const t = useTranslations('backgroundTasks');
  const isGenerating = useChatStore((state) => state.loading);
  const prevGenerating = useRef(false);
  const [bgRunningCount, setBgRunningCount] = useState(0);

  const refreshBgRunningCount = useCallback(async () => {
    try {
      const tasks = await listBackgroundTasks();
      setBgRunningCount(tasks.filter((task) => task.status === 'running').length);
    } catch {
      // Non-critical — tray falls back to idle when fetch fails
    }
  }, []);

  useEffect(() => {
    if (!isTauriRuntime()) {
      return;
    }
    void refreshBgRunningCount();
    return subscribeBackgroundTasksChanged(() => {
      void refreshBgRunningCount();
    });
  }, [refreshBgRunningCount]);

  useEffect(() => {
    if (!isTauriRuntime()) {
      return;
    }

    const onSystemNotification = (event: Event) => {
      const detail = (event as CustomEvent<SystemNotificationDetail>).detail;
      const kind = detail?.data?.meta_data?.kind;
      if (kind !== 'background_job_finish') {
        return;
      }
      if (document.visibilityState !== 'hidden') {
        return;
      }
      void import('@tauri-apps/api/window').then(({ getCurrentWindow }) =>
        getCurrentWindow().requestUserAttention(2),
      );
    };

    window.addEventListener('system-notification', onSystemNotification);
    return () => window.removeEventListener('system-notification', onSystemNotification);
  }, []);

  useEffect(() => {
    if (!isTauriRuntime()) {
      return;
    }

    const sync = async () => {
      try {
        const [{ invoke }, { getCurrentWindow, ProgressBarStatus }] = await Promise.all([
          import('@tauri-apps/api/core'),
          import('@tauri-apps/api/window'),
        ]);

        const status = isGenerating ? 'busy' : 'idle';
        const tooltip = isGenerating
          ? t('trayTooltipBusy')
          : bgRunningCount > 0
            ? t('trayTooltipBackground', { count: bgRunningCount })
            : t('trayTooltipIdle');

        await invoke('set_tray_status', { status, tooltip });

        const win = getCurrentWindow();
        const showProgress = isGenerating || bgRunningCount > 0;

        if (showProgress) {
          await win.setProgressBar({ status: ProgressBarStatus.Indeterminate });
        } else {
          await win.setProgressBar({ status: ProgressBarStatus.None });

          if (prevGenerating.current && document.visibilityState === 'hidden') {
            await win.requestUserAttention(2);
          }
        }
      } catch {
        // Tauri API unavailable or permission denied — silently ignore
      }

      prevGenerating.current = isGenerating;
    };

    void sync();
  }, [isGenerating, bgRunningCount, t]);
}
