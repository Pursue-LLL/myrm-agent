/**
 * [INPUT]
 * @/hooks/useLivenessState::useLivenessState (POS: Global agent liveness SSOT)
 * @/store/useChatStore::useChatStore (POS: Chat conversation state store)
 * @/lib/deploy-mode::isTauriRuntime (POS: Deployment mode detector)
 * @/services/background-tasks::listBackgroundTasks (POS: merged shell + agent tasks)
 * @/services/backgroundTasksRefresh::subscribeBackgroundTasksChanged
 * @/services/statistics::getUsageStatistics (POS: Global usage analytics API)
 * @/services/budget::getBudgetStatus (POS: Budget status API)
 *
 * [OUTPUT]
 * useTrayStatus: Synchronizes Tauri tray icon, tooltip (with today's usage summary),
 * taskbar progress bar, budget-alert native notification, and completion bounce
 * notification with global agent liveness state.
 *
 * [POS]
 * Desktop tray bridge hook. Consumes the global liveness SSOT (busy/idle/degraded)
 * from `/health/liveness` to drive tray icon switching and tooltip. Enriches tooltip
 * with today's token/cost snapshot. Fires native OS notification on budget_alert SSE.
 * Inert in non-Tauri environments.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { isTauriRuntime } from '@/lib/deploy-mode';
import useChatStore from '@/store/useChatStore';
import { listBackgroundTasks } from '@/services/background-tasks';
import { subscribeBackgroundTasksChanged } from '@/services/backgroundTasksRefresh';
import { useLivenessState } from '@/hooks/useLivenessState';
import { getUsageStatistics } from '@/services/statistics';
import { getBudgetStatus } from '@/services/budget';

import type { LivenessState } from '@/hooks/useLivenessState';

type SystemNotificationDetail = {
  data?: {
    meta_data?: {
      kind?: string;
    };
  };
};

type UsageSummary = { tokens: number; costUsd: number };

function formatUsageLine(summary: UsageSummary): string {
  const cost = summary.costUsd < 0.01
    ? '<$0.01'
    : `$${summary.costUsd.toFixed(2)}`;
  const tokens = summary.tokens >= 1_000_000
    ? `${(summary.tokens / 1_000_000).toFixed(1)}M`
    : summary.tokens >= 1_000
      ? `${(summary.tokens / 1_000).toFixed(1)}K`
      : `${summary.tokens}`;
  return `${tokens} tokens · ${cost}`;
}

export function useTrayStatus() {
  const t = useTranslations('backgroundTasks');
  const liveness = useLivenessState();
  const isGenerating = useChatStore((state) => state.loading);
  const prevGenerating = useRef(false);
  const prevLivenessState = useRef<LivenessState>('idle');
  const [bgRunningCount, setBgRunningCount] = useState(0);
  const [todayUsage, setTodayUsage] = useState<UsageSummary | null>(null);

  const refreshBgRunningCount = useCallback(async () => {
    try {
      const result = await listBackgroundTasks();
      setBgRunningCount(result.tasks.filter((task) => task.status === 'running').length);
    } catch {
      // Non-critical — tray falls back to idle when fetch fails
    }
  }, []);

  // Fetch today's usage snapshot for tooltip enrichment (low-frequency, event-driven)
  const refreshTodayUsage = useCallback(async () => {
    try {
      const today = new Date().toISOString().slice(0, 10);
      const stats = await getUsageStatistics(today, today);
      setTodayUsage({ tokens: stats.totalTokens, costUsd: stats.costUsd });
    } catch {
      // Non-critical — tooltip omits usage line when fetch fails
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

  // Refresh usage when liveness transitions from busy→idle (task just completed)
  useEffect(() => {
    if (!isTauriRuntime()) return;
    void refreshTodayUsage();
  }, [liveness.state, refreshTodayUsage]);

  // Budget-alert → native OS notification (Tauri only)
  useEffect(() => {
    if (!isTauriRuntime()) return;

    const onBudgetAlert = async () => {
      try {
        const status = await getBudgetStatus();
        if (!status.enabled) return;
        const { sendNotification, isPermissionGranted, requestPermission } = await import(
          '@tauri-apps/plugin-notification'
        );
        let granted = await isPermissionGranted();
        if (!granted) {
          const perm = await requestPermission();
          granted = perm === 'granted';
        }
        if (!granted) return;
        const pct = Math.round(status.usage_pct * 100);
        sendNotification({
          title: t('budgetAlertTitle'),
          body: t('budgetAlertBody', { pct, remaining: status.remaining_usd.toFixed(2) }),
        });
      } catch {
        // Notification permission denied or API unavailable
      }
    };

    window.addEventListener('budget_alert', onBudgetAlert);
    return () => window.removeEventListener('budget_alert', onBudgetAlert);
  }, [t]);

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

        let tooltip = liveness.state === 'busy'
          ? t('trayTooltipBusy')
          : liveness.state === 'degraded'
            ? t('trayTooltipDegraded')
            : bgRunningCount > 0
              ? t('trayTooltipBackground', { count: bgRunningCount })
              : t('trayTooltipIdle');

        if (todayUsage && todayUsage.tokens > 0) {
          tooltip += `\n${t('trayTooltipUsage', { usage: formatUsageLine(todayUsage) })}`;
        }

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
  }, [liveness.state, isGenerating, bgRunningCount, todayUsage, t]);
}
