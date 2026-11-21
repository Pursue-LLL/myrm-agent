'use client';

/**
 * [INPUT]
 * @/services/budget (POS: Channel budget API service)
 * ./ChannelLimitInput (POS: Inline daily-limit box of a channel budget)
 *
 * [OUTPUT]
 * ChannelBudgetSection: Settings panel for per-channel budget quotas.
 *
 * [POS]
 * Per-channel budget configuration UI. Displays each channel's daily budget usage
 * and allows configuring per-channel limits to prevent cost explosion; each edit is sent
 * as a patch of the one field it changes, so edits made close together, or from another
 * page, do not put each other's values back, and a limit box shows the limit in force
 * again once its blur has been handled, stored or not. The limit of a new channel is held
 * as the text of its box and read on Save, so the box can be emptied and retyped.
 * Unfolding a channel lists each sender's spend over the audit window, with bars sized by
 * their share of that window's total.
 */

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconShield,
  IconLoader,
  IconSave,
  IconTrash,
  IconPlus,
  IconChevronDown,
  IconChevronRight,
  IconUsers,
} from '@/components/features/icons/PremiumIcons';
import SettingsSection from '../SettingsSection';
import ChannelLimitInput from './ChannelLimitInput';
import { cn } from '@/lib/utils/classnameUtils';
import {
  getChannelBudgets,
  createChannelBudget,
  updateChannelBudget,
  deleteChannelBudget,
  getChannelAudit,
  type ChannelBudgetPolicy,
  type ChannelBudgetPolicyFields,
  type ChannelBudgetStatus,
  type ChannelAuditEntry,
} from '@/services/budget';

const STATUS_COLORS: Record<string, { bar: string; text: string }> = {
  ok: { bar: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400' },
  warning: { bar: 'bg-amber-500', text: 'text-amber-600 dark:text-amber-400' },
  exceeded: { bar: 'bg-red-500', text: 'text-red-600 dark:text-red-400' },
  disabled: { bar: 'bg-muted', text: 'text-muted-foreground' },
};

/** The limit a new channel starts with, as the text of its box. */
const DEFAULT_LIMIT_USD = '2';

interface EditingPolicy {
  channel_key: string;
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
    warning_threshold: 0.8,
    enabled: true,
    label: '',
  });
  // Text, not a number: a number box that ignores what is not a number cannot be emptied to type a new amount.
  const [limitText, setLimitText] = useState(DEFAULT_LIMIT_USD);
  const [saving, setSaving] = useState<string | null>(null);
  const [expandedAudit, setExpandedAudit] = useState<string | null>(null);
  const [auditEntries, setAuditEntries] = useState<ChannelAuditEntry[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  // NaN while the box is empty, which keeps Save off until an amount is typed.
  const newLimitUsd = parseFloat(limitText);
  // The audit spans several days, so a sender's bar is its share of what the window cost, not of today's spend.
  const auditTotalUsd = useMemo(
    () => auditEntries.reduce((sum, entry) => sum + entry.total_cost_usd, 0),
    [auditEntries],
  );

  const toggleAudit = useCallback(
    async (channelKey: string) => {
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
    },
    [expandedAudit],
  );

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

  // Only the field the user changed is sent: the rest of the policy shown here may be older than the stored one (another
  // page, or an edit still in flight), and sending it back would undo what changed meanwhile.
  const handleSave = useCallback(
    async (channelKey: string, patch: Partial<ChannelBudgetPolicyFields>) => {
      setSaving(channelKey);
      try {
        await updateChannelBudget(channelKey, patch);
        await fetchData();
      } catch {
        // apiRequest has already shown the failure.
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
        // apiRequest has already shown the failure.
      } finally {
        setSaving(null);
      }
    },
    [fetchData],
  );

  const handleAdd = useCallback(async () => {
    if (!newEntry.channel_key.trim()) {
      return;
    }
    setSaving('new');
    try {
      await createChannelBudget(newEntry.channel_key, {
        daily_limit_usd: newLimitUsd,
        warning_threshold: newEntry.warning_threshold,
        enabled: newEntry.enabled,
        label: newEntry.label,
      });
      setAdding(false);
      setNewEntry({ channel_key: '', warning_threshold: 0.8, enabled: true, label: '' });
      setLimitText(DEFAULT_LIMIT_USD);
      await fetchData();
    } catch {
      // apiRequest has already shown the failure.
    } finally {
      setSaving(null);
    }
  }, [newEntry, newLimitUsd, fetchData]);

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
                aria-label={t('dailyLimit')}
                min={0.01}
                max={10000}
                step="any"
                value={limitText}
                onChange={(e) => setLimitText(e.target.value)}
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
              disabled={saving === 'new' || !newEntry.channel_key.trim() || isNaN(newLimitUsd)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {saving === 'new' ? (
                <IconLoader className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <IconSave className="w-3.5 h-3.5" />
              )}
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
                  <span className="text-[10px] text-muted-foreground font-mono hidden sm:inline truncate">
                    {st.channel_key}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-xs font-mono tabular-nums">
                  ${st.today_cost_usd.toFixed(4)} / ${st.daily_limit_usd.toFixed(2)}
                </span>
                <button
                  onClick={() => handleDelete(st.channel_key)}
                  disabled={saving === st.channel_key}
                  className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive-text transition-colors"
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
                  <ChannelLimitInput
                    value={policy.daily_limit_usd}
                    label={t('dailyLimit')}
                    onSave={(limit) => handleSave(st.channel_key, { daily_limit_usd: limit })}
                  />
                </div>
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <span className="text-xs text-muted-foreground">{t('enabled')}</span>
                  <button
                    role="switch"
                    aria-checked={policy.enabled}
                    aria-label={t('enabled')}
                    onClick={() => handleSave(st.channel_key, { enabled: !policy.enabled })}
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
                    const pct = auditTotalUsd > 0 ? (entry.total_cost_usd / auditTotalUsd) * 100 : 0;
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
                            style={{ width: `${pct}%` }}
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
