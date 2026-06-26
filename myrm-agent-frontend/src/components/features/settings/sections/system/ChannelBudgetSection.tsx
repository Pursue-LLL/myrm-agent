'use client';

/**
 * [INPUT]
 * @/services/budget (POS: Channel budget API service)
 *
 * [OUTPUT]
 * ChannelBudgetSection: Settings panel for per-channel budget quotas.
 *
 * [POS]
 * Per-channel budget configuration UI. Displays each channel's daily budget usage
 * and allows configuring per-channel limits to prevent cost explosion.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconShield, IconLoader, IconSave, IconTrash, IconPlus, IconChevronDown, IconChevronRight, IconUsers } from '@/components/features/icons/PremiumIcons';
import SettingsSection from '../SettingsSection';
import { cn } from '@/lib/utils/classnameUtils';
import {
  getChannelBudgets,
  updateChannelBudget,
  deleteChannelBudget,
  getChannelAudit,
  type ChannelBudgetPolicy,
  type ChannelBudgetStatus,
  type ChannelAuditEntry,
} from '@/services/budget';

const STATUS_COLORS: Record<string, { bar: string; text: string }> = {
  ok: { bar: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400' },
  warning: { bar: 'bg-amber-500', text: 'text-amber-600 dark:text-amber-400' },
  exceeded: { bar: 'bg-red-500', text: 'text-red-600 dark:text-red-400' },
  disabled: { bar: 'bg-muted', text: 'text-muted-foreground' },
};

interface EditingPolicy {
  channel_key: string;
  daily_limit_usd: number;
  warning_threshold: number;
  enabled: boolean;
  label: string;
}

const ChannelBudgetSection = memo(() => {
  const t = useTranslations('settings.channelBudget');
  const [statuses, setStatuses] = useState<ChannelBudgetStatus[]>([]);
  const [policies, setPolicies] = useState<ChannelBudgetPolicy[]>([]);
  const [adding, setAdding] = useState(false);
  const [newEntry, setNewEntry] = useState<EditingPolicy>({
    channel_key: '',
    daily_limit_usd: 2.0,
    warning_threshold: 0.8,
    enabled: true,
    label: '',
  });
  const [saving, setSaving] = useState<string | null>(null);
  const [expandedAudit, setExpandedAudit] = useState<string | null>(null);
  const [auditEntries, setAuditEntries] = useState<ChannelAuditEntry[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);

  const toggleAudit = useCallback(async (channelKey: string) => {
    if (expandedAudit === channelKey) {
      setExpandedAudit(null);
      return;
    }
    setAuditLoading(true);
    setExpandedAudit(channelKey);
    try {
      const data = await getChannelAudit(channelKey, 7);
      setAuditEntries(data.entries);
    } catch {
      setAuditEntries([]);
    } finally {
      setAuditLoading(false);
    }
  }, [expandedAudit]);

  const fetchData = useCallback(async () => {
    try {
      const data = await getChannelBudgets();
      setPolicies(data.policies);
      setStatuses(data.statuses);
    } catch {
      /* silent */
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSave = useCallback(
    async (channelKey: string, policy: Omit<ChannelBudgetPolicy, 'channel_key'>) => {
      setSaving(channelKey);
      try {
        await updateChannelBudget(channelKey, policy);
        await fetchData();
      } catch {
        /* silent */
      } finally {
        setSaving(null);
      }
    },
    [fetchData],
  );

  const handleDelete = useCallback(
    async (channelKey: string) => {
      setSaving(channelKey);
      try {
        await deleteChannelBudget(channelKey);
        await fetchData();
      } catch {
        /* silent */
      } finally {
        setSaving(null);
      }
    },
    [fetchData],
  );

  const handleAdd = useCallback(async () => {
    if (!newEntry.channel_key.trim()) return;
    setSaving('new');
    try {
      await updateChannelBudget(newEntry.channel_key, {
        daily_limit_usd: newEntry.daily_limit_usd,
        warning_threshold: newEntry.warning_threshold,
        enabled: newEntry.enabled,
        label: newEntry.label,
      });
      setAdding(false);
      setNewEntry({ channel_key: '', daily_limit_usd: 2.0, warning_threshold: 0.8, enabled: true, label: '' });
      await fetchData();
    } catch {
      /* silent */
    } finally {
      setSaving(null);
    }
  }, [newEntry, fetchData]);

  return (
    <SettingsSection
      title={t('title')}
      description={t('description')}
      action={
        !adding ? (
          <button
            onClick={() => setAdding(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <IconPlus className="w-3.5 h-3.5" />
            {t('add')}
          </button>
        ) : null
      }
    >
      {adding && (
        <div className="p-3 rounded-lg border border-dashed border-primary/30 bg-primary/5 space-y-3">
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              type="text"
              value={newEntry.channel_key}
              onChange={(e) => setNewEntry((prev) => ({ ...prev, channel_key: e.target.value }))}
              placeholder={t('channelKeyPlaceholder')}
              className="flex-1 min-w-0 text-sm px-2.5 py-1.5 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
            <input
              type="text"
              value={newEntry.label}
              onChange={(e) => setNewEntry((prev) => ({ ...prev, label: e.target.value }))}
              placeholder={t('labelPlaceholder')}
              className="sm:w-32 text-sm px-2.5 py-1.5 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1">
              <span className="text-xs text-muted-foreground">{t('dailyLimit')}:</span>
              <span className="text-xs text-muted-foreground">$</span>
              <input
                type="number"
                min={0.01}
                max={10000}
                step={0.5}
                value={newEntry.daily_limit_usd}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  if (!isNaN(v)) setNewEntry((prev) => ({ ...prev, daily_limit_usd: v }));
                }}
                className="w-20 text-right text-sm font-mono px-2 py-1 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
            </div>
            <div className="flex-1" />
            <button
              onClick={() => setAdding(false)}
              className="px-3 py-1.5 text-xs rounded-lg border border-border hover:bg-muted transition-colors"
            >
              {t('cancel')}
            </button>
            <button
              onClick={handleAdd}
              disabled={saving === 'new' || !newEntry.channel_key.trim()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {saving === 'new' ? <IconLoader className="w-3.5 h-3.5 animate-spin" /> : <IconSave className="w-3.5 h-3.5" />}
              {t('save')}
            </button>
          </div>
        </div>
      )}

      {statuses.length === 0 && !adding && (
        <div className="text-sm text-muted-foreground py-4 text-center">{t('empty')}</div>
      )}

      {statuses.map((st) => {
        const policy = policies.find((p) => p.channel_key === st.channel_key);
        const colors = STATUS_COLORS[st.status] ?? STATUS_COLORS.disabled;
        return (
          <div key={st.channel_key} className="p-3 rounded-lg border border-border/50 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <IconShield className={cn('w-4 h-4 shrink-0', colors.text)} />
                <span className="text-sm font-medium truncate">{st.label || st.channel_key}</span>
                {st.label && (
                  <span className="text-[10px] text-muted-foreground font-mono hidden sm:inline truncate">{st.channel_key}</span>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-xs font-mono tabular-nums">
                  ${st.today_cost_usd.toFixed(4)} / ${st.daily_limit_usd.toFixed(2)}
                </span>
                <button
                  onClick={() => handleDelete(st.channel_key)}
                  disabled={saving === st.channel_key}
                  className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                  title={t('delete')}
                >
                  {saving === st.channel_key ? (
                    <IconLoader className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <IconTrash className="w-3.5 h-3.5" />
                  )}
                </button>
              </div>
            </div>
            <div className="h-1.5 rounded-full bg-black/5 dark:bg-white/5 overflow-hidden">
              <div
                className={cn('h-full rounded-full transition-all duration-500', colors.bar)}
                style={{ width: `${Math.min(st.usage_pct, 100)}%` }}
              />
            </div>
            {policy && (
              <div className="flex flex-wrap items-center gap-3 pt-1">
                <div className="flex items-center gap-1">
                  <span className="text-xs text-muted-foreground">{t('dailyLimit')}:</span>
                  <span className="text-xs text-muted-foreground">$</span>
                  <input
                    type="number"
                    min={0.01}
                    max={10000}
                    step={0.5}
                    defaultValue={policy.daily_limit_usd}
                    key={`${st.channel_key}-${policy.daily_limit_usd}`}
                    onBlur={(e) => {
                      const v = parseFloat(e.target.value);
                      if (!isNaN(v) && v !== policy.daily_limit_usd) {
                        handleSave(st.channel_key, { ...policy, daily_limit_usd: v });
                      }
                    }}
                    className="w-20 text-right text-xs font-mono px-1.5 py-1 rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                </div>
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <span className="text-xs text-muted-foreground">{t('enabled')}</span>
                  <button
                    role="switch"
                    aria-checked={policy.enabled}
                    onClick={() => handleSave(st.channel_key, { ...policy, enabled: !policy.enabled })}
                    className={cn(
                      'relative w-8 h-5 rounded-full transition-colors',
                      policy.enabled ? 'bg-accent-warm' : 'bg-input dark:bg-muted',
                    )}
                  >
                    <span
                      className={cn(
                        'absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform',
                        policy.enabled && 'translate-x-3',
                      )}
                    />
                  </button>
                </label>
              </div>
            )}
            <button
              onClick={() => toggleAudit(st.channel_key)}
              className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors pt-1"
            >
              {expandedAudit === st.channel_key ? (
                <IconChevronDown className="w-3 h-3" />
              ) : (
                <IconChevronRight className="w-3 h-3" />
              )}
              <IconUsers className="w-3 h-3" />
              {t('auditDetails')}
            </button>
            {expandedAudit === st.channel_key && (
              <div className="pt-1.5 space-y-1.5">
                {auditLoading ? (
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground py-2">
                    <IconLoader className="w-3 h-3 animate-spin" />
                    {t('auditLoading')}
                  </div>
                ) : auditEntries.length === 0 ? (
                  <div className="text-xs text-muted-foreground py-1">{t('auditEmpty')}</div>
                ) : (
                  auditEntries.map((entry) => {
                    const pct = st.today_cost_usd > 0
                      ? (entry.total_cost_usd / st.today_cost_usd) * 100
                      : 0;
                    return (
                      <div key={entry.sender_id} className="flex items-center gap-2">
                        <span className="text-[11px] text-muted-foreground font-mono truncate min-w-0 flex-1">
                          {entry.sender_id}
                        </span>
                        <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
                          {entry.message_count} {t('auditMessages')}
                        </span>
                        <div className="w-16 h-1 rounded-full bg-black/5 dark:bg-white/5 overflow-hidden shrink-0">
                          <div
                            className="h-full rounded-full bg-primary/60 transition-all"
                            style={{ width: `${Math.min(pct, 100)}%` }}
                          />
                        </div>
                        <span className="text-[11px] font-mono tabular-nums shrink-0">
                          ${entry.total_cost_usd.toFixed(4)}
                        </span>
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>
        );
      })}
    </SettingsSection>
  );
});

ChannelBudgetSection.displayName = 'ChannelBudgetSection';

export default ChannelBudgetSection;
