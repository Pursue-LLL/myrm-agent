/**
 * [INPUT]
 * @/hooks/useLivenessState::useLivenessState (POS: Global agent liveness SSOT)
 * @/store/useChatStore::useChatStore (POS: Chat conversation state store)
 * @/lib/deploy-mode::isTauriRuntime (POS: Deployment mode detector)
 * @/services/background-tasks::listBackgroundTasks (POS: merged shell + agent tasks)
 * @/services/backgroundTasksRefresh::subscribeBackgroundTasksChanged
 *
 * [OUTPUT]
 * useTrayStatus: Synchronizes Tauri tray icon, tooltip, taskbar progress bar,
 * and completion bounce notification with global agent liveness state.
 *
 * [POS]
 * Desktop tray bridge hook. Consumes the global liveness SSOT (busy/idle/degraded)
 * from `/health/liveness` to drive tray icon switching and tooltip. Retains
 * per-tab `isGenerating` for completion-bounce `requestUserAttention` only.
 * Inert in non-Tauri environments.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { isTauriRuntime } from '@/lib/deploy-mode';
import useChatStore from '@/store/useChatStore';
import { listBackgroundTasks } from '@/services/background-tasks';
import { subscribeBackgroundTasksChanged } from '@/services/backgroundTasksRefresh';
import { useLivenessState } from '@/hooks/useLivenessState';

import type { LivenessState } from '@/hooks/useLivenessState';

type SystemNotificationDetail = {
  data?: {
    meta_data?: {
      kind?: string;
    };
  };
};

export function useTrayStatus() {
  const t = useTranslations('backgroundTasks');
  const liveness = useLivenessState();
  const isGenerating = useChatStore((state) => state.loading);
  const prevGenerating = useRef(false);
  const prevLivenessState = useRef<LivenessState>('idle');
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

        const tooltip = liveness.state === 'busy'
          ? t('trayTooltipBusy')
          : liveness.state === 'degraded'
            ? t('trayTooltipDegraded')
            : bgRunningCount > 0
              ? t('trayTooltipBackground', { count: bgRunningCount })
              : t('trayTooltipIdle');

        await invoke('set_tray_status', { status: liveness.state, tooltip });

        const win = getCurrentWindow();
        const showProgress = liveness.state === 'busy' || bgRunningCount > 0;

        if (showProgress) {
          await win.setProgressBar({ status: ProgressBarStatus.Indeterminate });
        } else {
          await win.setProgressBar({ status: ProgressBarStatus.None });

          const wasBusy = prevLivenessState.current === 'busy' || prevGenerating.current;
          if (wasBusy && document.visibilityState === 'hidden') {
            await win.requestUserAttention(2);
          }
        }
      } catch {
        // Tauri API unavailable or permission denied — silently ignore
      }

      prevGenerating.current = isGenerating;
      prevLivenessState.current = liveness.state;
    };

    void sync();
  }, [liveness.state, isGenerating, bgRunningCount, t]);
}
