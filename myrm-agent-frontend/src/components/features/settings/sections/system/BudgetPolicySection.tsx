'use client';

/**
 * [INPUT]
 * @/services/budget (POS: Budget API service)
 *
 * [OUTPUT]
 * BudgetPolicySection: Settings panel for multi-dimensional budget configuration.
 *
 * [POS]
 * Budget policy configuration UI. Displays current spend progress and allows
 * users to configure session/daily/per-call limits, finalization reserve, and exceeded actions.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconChart,
  IconShield,
  IconAlertTriangle,
  IconLoader,
  IconSave,
  IconClock,
  IconZap,
} from '@/components/features/icons/PremiumIcons';
import SettingsSection from '../SettingsSection';
import { cn } from '@/lib/utils/classnameUtils';
import {
  getBudgetPolicy,
  getBudgetStatus,
  updateBudgetPolicy,
  type BudgetPolicy,
  type BudgetStatus,
} from '@/services/budget';

const STATUS_COLORS = {
  ok: {
    bar: 'bg-emerald-500',
    text: 'text-emerald-600 dark:text-emerald-400',
    bg: 'bg-emerald-100 dark:bg-emerald-900/30',
  },
  warning: {
    bar: 'bg-amber-500',
    text: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-100 dark:bg-amber-900/30',
  },
  finalization: {
    bar: 'bg-orange-500',
    text: 'text-orange-600 dark:text-orange-400',
    bg: 'bg-orange-100 dark:bg-orange-900/30',
  },
  exceeded: {
    bar: 'bg-red-500',
    text: 'text-red-600 dark:text-red-400',
    bg: 'bg-red-100 dark:bg-red-900/30',
  },
  disabled: {
    bar: 'bg-muted',
    text: 'text-muted-foreground',
    bg: 'bg-muted',
  },
} as const;

function formatCost(cost: number): string {
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

const BudgetPolicySection = memo(() => {
  const t = useTranslations('settings.budget');
  const [policy, setPolicy] = useState<BudgetPolicy>({
    enabled: false,
    daily_limit_usd: 10.0,
    session_limit_usd: 5.0,
    per_call_limit_usd: null,
    warning_threshold: 0.8,
    finalization_reserve_pct: 0.15,
    action_on_exceeded: 'finalize',
  });
  const [status, setStatus] = useState<BudgetStatus | null>(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [p, s] = await Promise.all([getBudgetPolicy(), getBudgetStatus()]);
      setPolicy(p);
      setStatus(s);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    fetchData();
    const handleSseEvent = () => fetchData();
    window.addEventListener('budget_updated', handleSseEvent);
    window.addEventListener('budget_alert', handleSseEvent);
    return () => {
      window.removeEventListener('budget_updated', handleSseEvent);
      window.removeEventListener('budget_alert', handleSseEvent);
    };
  }, [fetchData]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const updated = await updateBudgetPolicy(policy);
      setPolicy(updated);
      setDirty(false);
      const s = await getBudgetStatus();
      setStatus(s);
    } catch {
      // handled by apiRequest
    } finally {
      setSaving(false);
    }
  }, [policy]);

  const updateField = useCallback(<K extends keyof BudgetPolicy>(key: K, value: BudgetPolicy[K]) => {
    setPolicy((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
  }, []);

  const statusKey = status?.status ?? 'disabled';
  const colors = STATUS_COLORS[statusKey in STATUS_COLORS ? (statusKey as keyof typeof STATUS_COLORS) : 'disabled'];

  return (
    <SettingsSection
      title={t('title')}
      description={t('description')}
      action={
        dirty ? (
          <button
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {saving ? <IconLoader className="w-3.5 h-3.5 animate-spin" /> : <IconSave className="w-3.5 h-3.5" />}
            {t('save')}
          </button>
        ) : null
      }
    >
      {/* Status bar */}
      {status && status.enabled && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {status.session_limit_usd > 0 ? t('sessionSpend') : t('todaySpend')}
            </span>
            <div className="flex items-center gap-2">
              <span className="text-sm font-mono font-medium tabular-nums">
                {status.session_limit_usd > 0
                  ? `${formatCost(status.session_cost_usd)} / ${formatCost(status.session_limit_usd)}`
                  : `${formatCost(status.today_cost_usd)} / ${formatCost(status.daily_limit_usd)}`}
              </span>
              <span className={cn('text-[10px] px-1.5 py-0.5 rounded font-medium', colors.bg, colors.text)}>
                {status.usage_pct.toFixed(0)}%
              </span>
            </div>
          </div>
          <div className="h-2 rounded-full bg-black/5 dark:bg-white/5 overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all duration-700 ease-out', colors.bar)}
              style={{ width: `${Math.min(status.usage_pct, 100)}%` }}
            />
          </div>
          {statusKey !== 'ok' && statusKey !== 'disabled' && (
            <div className={cn('flex items-center gap-2 rounded-lg px-3 py-2 text-xs', colors.bg, colors.text)}>
              <IconAlertTriangle className="w-3.5 h-3.5" />
              <span>
                {statusKey === 'exceeded'
                  ? t('statusExceeded')
                  : statusKey === 'finalization'
                    ? t('statusFinalization')
                    : t('statusWarning')}
                <span className="ml-1.5 opacity-75">• {t('ecoModeHint')}</span>
              </span>
            </div>
          )}
        </div>
      )}

      {/* Enable toggle */}
      <label className="flex items-center justify-between cursor-pointer">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-emerald-100 dark:bg-emerald-900/30">
            <IconShield className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div>
            <div className="text-sm font-medium">{t('enableLabel')}</div>
            <div className="text-xs text-muted-foreground">{t('enableDesc')}</div>
          </div>
        </div>
        <button
          role="switch"
          aria-checked={policy.enabled}
          onClick={() => updateField('enabled', !policy.enabled)}
          className={cn(
            'relative w-10 h-6 rounded-full transition-colors',
            policy.enabled ? 'bg-accent-warm' : 'bg-input dark:bg-muted',
          )}
        >
          <span
            className={cn(
              'absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform',
              policy.enabled && 'translate-x-4',
            )}
          />
        </button>
      </label>

      {policy.enabled && (
        <div className="space-y-4 pt-2">
          {/* Session limit */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-violet-100 dark:bg-violet-900/30">
                <IconClock className="w-4 h-4 text-violet-600 dark:text-violet-400" />
              </div>
              <div>
                <div className="text-sm font-medium">{t('sessionLimit')}</div>
                <div className="text-xs text-muted-foreground">{t('sessionLimitDesc')}</div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-sm text-muted-foreground">$</span>
              <input
                type="number"
                min={0.01}
                max={10000}
                step={0.5}
                value={policy.session_limit_usd ?? ''}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  updateField('session_limit_usd', isNaN(v) ? null : v);
                }}
                placeholder="5.0"
                className="w-24 text-right text-sm font-mono px-2 py-1.5 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
            </div>
          </div>

          {/* Daily limit */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-blue-100 dark:bg-blue-900/30">
                <IconChart className="w-4 h-4 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <div className="text-sm font-medium">{t('dailyLimit')}</div>
                <div className="text-xs text-muted-foreground">{t('dailyLimitDesc')}</div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-sm text-muted-foreground">$</span>
              <input
                type="number"
                min={0.01}
                max={10000}
                step={0.5}
                value={policy.daily_limit_usd ?? ''}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  updateField('daily_limit_usd', isNaN(v) ? null : v);
                }}
                placeholder="10.0"
                className="w-24 text-right text-sm font-mono px-2 py-1.5 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
            </div>
          </div>

          {/* Per-call limit */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-cyan-100 dark:bg-cyan-900/30">
                <IconZap className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
              </div>
              <div>
                <div className="text-sm font-medium">{t('perCallLimit')}</div>
                <div className="text-xs text-muted-foreground">{t('perCallLimitDesc')}</div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-sm text-muted-foreground">$</span>
              <input
                type="number"
                min={0.01}
                max={1000}
                step={0.1}
                value={policy.per_call_limit_usd ?? ''}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  updateField('per_call_limit_usd', isNaN(v) ? null : v);
                }}
                placeholder={t('optional')}
                className="w-24 text-right text-sm font-mono px-2 py-1.5 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
            </div>
          </div>

          {/* Warning threshold */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-amber-100 dark:bg-amber-900/30">
                <IconAlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
              </div>
              <div>
                <div className="text-sm font-medium">{t('warningThreshold')}</div>
                <div className="text-xs text-muted-foreground">{t('warningThresholdDesc')}</div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <input
                type="number"
                min={10}
                max={100}
                step={5}
                value={Math.round(policy.warning_threshold * 100)}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10);
                  if (!isNaN(v) && v >= 10 && v <= 100) updateField('warning_threshold', v / 100);
                }}
                className="w-16 text-right text-sm font-mono px-2 py-1.5 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
              <span className="text-sm text-muted-foreground">%</span>
            </div>
          </div>

          {/* Action on exceeded */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-red-100 dark:bg-red-900/30">
                <IconShield className="w-4 h-4 text-red-600 dark:text-red-400" />
              </div>
              <div>
                <div className="text-sm font-medium">{t('actionOnExceeded')}</div>
                <div className="text-xs text-muted-foreground">{t('actionOnExceededDesc')}</div>
              </div>
            </div>
            <select
              value={policy.action_on_exceeded}
              onChange={(e) => updateField('action_on_exceeded', e.target.value as 'warn' | 'block' | 'finalize')}
              className="text-sm px-2 py-1.5 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
            >
              <option value="finalize">{t('actionFinalize')}</option>
              <option value="warn">{t('actionWarn')}</option>
              <option value="block">{t('actionBlock')}</option>
            </select>
          </div>
        </div>
      )}
    </SettingsSection>
  );
});

BudgetPolicySection.displayName = 'BudgetPolicySection';

export default BudgetPolicySection;
