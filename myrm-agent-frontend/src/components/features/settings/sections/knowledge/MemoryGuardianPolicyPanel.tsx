'use client';

import { memo, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { type MemoryGuardianPolicy } from '@/services/memory';

interface MemoryGuardianPolicyPanelProps {
  policy: MemoryGuardianPolicy;
  dirty: boolean;
  saving: boolean;
  onPolicyChange: (policy: MemoryGuardianPolicy) => void;
  onSave: () => void;
}

const MemoryGuardianPolicyPanel = memo(
  ({ policy, dirty, saving, onPolicyChange, onSave }: MemoryGuardianPolicyPanelProps) => {
    const t = useTranslations('settings.memoryGuardian');

    const hourOptions = useMemo(
      () =>
        Array.from({ length: 24 }).map((_, hour) => ({
          value: hour,
          label: `${hour.toString().padStart(2, '0')}:00`,
        })),
      [],
    );

    const updateField = <K extends keyof MemoryGuardianPolicy>(key: K, value: MemoryGuardianPolicy[K]) => {
      onPolicyChange({ ...policy, [key]: value });
    };

    return (
      <div className="rounded-xl border border-border/40 bg-background/40 p-3 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="text-xs font-semibold">{t('policyTitle')}</div>
            <div className="text-[11px] text-muted-foreground">{t('policyDesc')}</div>
          </div>
          {dirty && (
            <button
              onClick={onSave}
              disabled={saving}
              className={cn(
                'shrink-0 px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors',
                'bg-primary/10 text-primary hover:bg-primary/20 disabled:opacity-50',
              )}
            >
              {saving ? t('saving') : t('savePolicy')}
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="space-y-1">
            <div className="text-[11px] text-muted-foreground">{t('frequencyTierLabel')}</div>
            <select
              value={policy.frequency_tier}
              onChange={(e) =>
                updateField('frequency_tier', e.target.value as MemoryGuardianPolicy['frequency_tier'])
              }
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs"
            >
              <option value="conservative">{t('frequencyTierConservative')}</option>
              <option value="balanced">{t('frequencyTierBalanced')}</option>
              <option value="aggressive">{t('frequencyTierAggressive')}</option>
            </select>
          </label>

          <label className="flex items-center justify-between rounded-md border border-border bg-background px-2.5 py-2">
            <span className="text-xs text-muted-foreground">{t('quietWindowLabel')}</span>
            <button
              type="button"
              role="switch"
              aria-checked={policy.quiet_window_enabled}
              onClick={() => updateField('quiet_window_enabled', !policy.quiet_window_enabled)}
              className={cn(
                'relative w-9 h-5 rounded-full transition-colors',
                policy.quiet_window_enabled ? 'bg-accent-warm' : 'bg-input dark:bg-muted',
              )}
            >
              <span
                className={cn(
                  'absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform',
                  policy.quiet_window_enabled && 'translate-x-4',
                )}
              />
            </button>
          </label>
        </div>

        {policy.quiet_window_enabled && (
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1">
              <div className="text-[11px] text-muted-foreground">{t('quietWindowStart')}</div>
              <select
                value={policy.quiet_window_start_hour}
                onChange={(e) => updateField('quiet_window_start_hour', Number(e.target.value))}
                className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs"
              >
                {hourOptions.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <div className="text-[11px] text-muted-foreground">{t('quietWindowEnd')}</div>
              <select
                value={policy.quiet_window_end_hour}
                onChange={(e) => updateField('quiet_window_end_hour', Number(e.target.value))}
                className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs"
              >
                {hourOptions.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
      </div>
    );
  },
);

MemoryGuardianPolicyPanel.displayName = 'MemoryGuardianPolicyPanel';

export default MemoryGuardianPolicyPanel;
