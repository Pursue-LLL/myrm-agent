/**
 * [INPUT]
 * - @/store/useBudgetExceededStore (POS: 工作单元用尽对话框)
 * - ./backupAlertToast (POS: 备份失败 toast 与组件标识)
 *
 * [OUTPUT]
 * - alertEventHandlers: 健康告警与预算告警事件的处理器表
 *
 * [POS]
 * 全局事件中需要用户注意的告警：按严重程度弹出提示，并把预算告警转给订阅它的页面。
 */
import {
  BACKUP_ALERT_COMPONENT,
  CLOUD_SYNC_ALERT_COMPONENT,
  showBackupFailureToast,
  showCloudSyncFailureToast,
} from '@/hooks/globalEvents/backupAlertToast';
import { useBudgetExceededStore } from '@/store/useBudgetExceededStore';
import { mutate as mutateSwr } from 'swr';

import type { GlobalEventHandler } from './eventTypes';

const handleHealthAlert: GlobalEventHandler = (payload, { t, router, pushToast, notifyIfLeader }) => {
  const component = String(payload.data.component ?? 'Unknown');
  const status = String(payload.data.status ?? 'fail');
  const message = String(payload.data.message ?? 'Health check failed');
  const fixSuggestion = payload.data.fix_suggestion ? String(payload.data.fix_suggestion) : undefined;
  const layer = String(payload.data.layer ?? 'system');

  if (component === BACKUP_ALERT_COMPONENT && status === 'fail') {
    showBackupFailureToast({ t, router, toast: pushToast, notifyIfLeader });
  } else if (component === CLOUD_SYNC_ALERT_COMPONENT && status === 'fail') {
    showCloudSyncFailureToast({ t, router, toast: pushToast, notifyIfLeader });
  } else if (status === 'fail') {
    pushToast.error(t('healthAlertFail', { component, layer }), {
      description: `${message}${fixSuggestion ? `\n${t('healthAlertTip', { tip: fixSuggestion })}` : ''}`,
      duration: 15_000,
      dismissible: true,
      action: {
        label: t('viewHealthDashboard'),
        onClick: () => router.push('/settings/system'),
      },
    });
    notifyIfLeader(t('healthAlertFail', { component, layer }), message, () => router.push('/settings/system'));
  }
};

const handleBudgetAlert: GlobalEventHandler = (payload, { t, pushToast, notifyIfLeader }) => {
  const budgetStatus = String(payload.data.status ?? 'warning');
  const remaining = typeof payload.data.remaining === 'number' ? payload.data.remaining : 0;
  const dimension = String(payload.data.dimension ?? '');
  const remainingText = t('budgetRemaining', { dimension, remaining: remaining.toFixed(4) });

  if (budgetStatus === 'exceeded') {
    if (dimension === 'work_units') {
      const required = typeof payload.data.today_cost === 'number' ? payload.data.today_cost : 0;
      const limit = typeof payload.data.daily_limit === 'number' ? payload.data.daily_limit : remaining;
      useBudgetExceededStore.getState().show(Math.round(required), Math.round(limit));
      void mutateSwr((key) => Array.isArray(key) && key[0] === 'cp-entitlements');
    } else {
      pushToast.error(t('budgetExceeded'), {
        description: remainingText,
        duration: 15_000,
        dismissible: true,
      });
      notifyIfLeader(t('budgetExceeded'), remainingText);
    }
  } else if (budgetStatus === 'finalization') {
    pushToast.warning(t('budgetFinalization'), {
      description: remainingText,
      duration: 12_000,
      dismissible: true,
    });
  } else {
    const ecoActive = payload.data.eco_mode === true;
    pushToast.warning(t('budgetWarning'), {
      description: ecoActive ? `${remainingText}\n${t('ecoModeActive')}` : remainingText,
      duration: 10_000,
      dismissible: true,
    });
  }

  window.dispatchEvent(new CustomEvent('budget_alert', { detail: payload.data }));
};

export const alertEventHandlers: Record<string, GlobalEventHandler> = {
  health_alert: handleHealthAlert,
  budget_alert: handleBudgetAlert,
};
