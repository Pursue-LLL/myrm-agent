import { describe, expect, it } from 'vitest';
import { BACKUP_ALERT_COMPONENT, CLOUD_SYNC_ALERT_COMPONENT } from '@/hooks/globalEvents/backupAlertToast';
import {
  emit,
  installGlobalEventsLifecycle,
  mocks,
  mountGlobalEvents,
  recordWindowEvents,
  toastMessage,
  toastOptions,
} from './globalEventsTestKit';

describe('useGlobalEvents: alerts', () => {
  installGlobalEventsLifecycle();

  describe('health_alert', () => {
    it('routes the backup and cloud sync failures to their dedicated toasts', () => {
      mountGlobalEvents();
      const deps = {
        t: expect.any(Function),
        router: mocks.router,
        toast: expect.any(Object),
        notifyIfLeader: expect.any(Function),
      };

      emit('health_alert', { component: BACKUP_ALERT_COMPONENT, status: 'fail' });
      emit('health_alert', { component: CLOUD_SYNC_ALERT_COMPONENT, status: 'fail' });

      expect(mocks.showBackupFailureToast).toHaveBeenCalledWith(deps);
      expect(mocks.showCloudSyncFailureToast).toHaveBeenCalledWith(deps);
      expect(mocks.toast.error).not.toHaveBeenCalled();
    });

    it('raises an error toast and a leader notification for any other failure', () => {
      mountGlobalEvents();

      emit('health_alert', {
        component: 'db',
        layer: 'storage',
        status: 'fail',
        message: 'down',
        fix_suggestion: 'restart',
      });

      expect(toastMessage(mocks.toast.error)).toBe('healthAlertFail');
      expect(toastOptions(mocks.toast.error)).toMatchObject({
        description: 'down\nhealthAlertTip',
        duration: 15_000,
        dismissible: true,
      });
      toastOptions(mocks.toast.error).action?.onClick();
      expect(mocks.router.push).toHaveBeenCalledWith('/settings/system');
      expect(mocks.notify).toHaveBeenCalledWith('healthAlertFail', {
        body: 'down',
        fallbackToToast: false,
        onClick: expect.any(Function),
      });
    });

    it('omits the tip without a fix suggestion and ignores non-failures', () => {
      mountGlobalEvents();

      emit('health_alert', { component: 'db', status: 'fail', message: 'down' });
      emit('health_alert', { component: 'db', status: 'ok', message: 'fine' });
      emit('health_alert', { component: BACKUP_ALERT_COMPONENT, status: 'ok' });

      expect(mocks.toast.error).toHaveBeenCalledTimes(1);
      expect(toastOptions(mocks.toast.error).description).toBe('down');
      expect(mocks.showBackupFailureToast).not.toHaveBeenCalled();
    });
  });

  describe('budget_alert', () => {
    it('opens the work-unit exhaustion dialog and refreshes the entitlements', () => {
      mountGlobalEvents();
      const events = recordWindowEvents();

      emit('budget_alert', { status: 'exceeded', dimension: 'work_units', today_cost: 12.4, daily_limit: 10.6 });

      expect(mocks.showBudgetExceeded).toHaveBeenCalledWith(12, 11);
      const isEntitlementKey = mocks.mutateSwr.mock.calls[0][0] as (key: unknown) => boolean;
      expect(isEntitlementKey(['cp-entitlements', 'user'])).toBe(true);
      expect(isEntitlementKey(['other'])).toBe(false);
      expect(isEntitlementKey('cp-entitlements')).toBe(false);
      expect(mocks.toast.error).not.toHaveBeenCalled();
      expect(events().map((event) => event.type)).toEqual(['budget_alert']);
    });

    it('falls back to the remaining amount when the daily limit is missing', () => {
      mountGlobalEvents();

      emit('budget_alert', { status: 'exceeded', dimension: 'work_units', today_cost: 5, remaining: 3 });

      expect(mocks.showBudgetExceeded).toHaveBeenCalledWith(5, 3);
    });

    it('raises an error toast and a leader notification when another dimension is exceeded', () => {
      mountGlobalEvents();

      emit('budget_alert', { status: 'exceeded', dimension: 'tokens', remaining: 0.5 });

      expect(toastMessage(mocks.toast.error)).toBe('budgetExceeded');
      expect(toastOptions(mocks.toast.error)).toEqual({
        description: 'budgetRemaining',
        duration: 15_000,
        dismissible: true,
      });
      expect(mocks.notify).toHaveBeenCalledWith('budgetExceeded', {
        body: 'budgetRemaining',
        fallbackToToast: false,
        onClick: undefined,
      });
      expect(mocks.showBudgetExceeded).not.toHaveBeenCalled();
    });

    it('warns during finalization and on a plain warning, mentioning eco mode when active', () => {
      mountGlobalEvents();

      emit('budget_alert', { status: 'finalization', dimension: 'tokens', remaining: 1 });
      emit('budget_alert', { status: 'warning', dimension: 'tokens', remaining: 1 });
      emit('budget_alert', { status: 'warning', dimension: 'tokens', remaining: 1, eco_mode: true });

      expect(mocks.toast.warning.mock.calls.map(([message]) => message)).toEqual([
        'budgetFinalization',
        'budgetWarning',
        'budgetWarning',
      ]);
      expect(toastOptions(mocks.toast.warning, 0)).toEqual({
        description: 'budgetRemaining',
        duration: 12_000,
        dismissible: true,
      });
      expect(toastOptions(mocks.toast.warning, 1)).toEqual({
        description: 'budgetRemaining',
        duration: 10_000,
        dismissible: true,
      });
      expect(toastOptions(mocks.toast.warning, 2).description).toBe('budgetRemaining\necoModeActive');
    });
  });

  describe('web notification preference', () => {
    it('suppresses toasts and system notifications but keeps relaying window events', () => {
      mocks.config.enableWebNotifications = false;
      mountGlobalEvents();
      const events = recordWindowEvents();

      emit('approval_required', { action_type: 'shell' });
      emit('budget_alert', { status: 'exceeded', dimension: 'tokens', remaining: 1 });

      expect(mocks.toast.info).not.toHaveBeenCalled();
      expect(mocks.toast.error).not.toHaveBeenCalled();
      expect(mocks.notify).not.toHaveBeenCalled();
      expect(events().map((event) => event.type)).toEqual(['approval-required', 'budget_alert']);
    });
  });
});
