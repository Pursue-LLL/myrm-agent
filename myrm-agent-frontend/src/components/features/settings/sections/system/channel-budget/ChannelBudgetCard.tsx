'use client';

/**
 * [INPUT]
 * - react::useState (POS: React state hook)
 * - next-intl::useTranslations (POS: i18n support)
 * - @/components/features/icons/PremiumIcons (POS: Standard premium UI icons)
 * - @/lib/utils/classnameUtils (POS: Class name merge helper)
 * - @/lib/utils/toast (POS: Toast wrapper)
 * - @/services/budget (POS: Channel budget API types)
 * - ./ChannelLimitInput (POS: Inline daily-limit box of a channel budget)
 * - ./channelLimit (POS: Range of a channel's daily limit)
 * - ./useChannelAudit::AUDIT_DAYS, ChannelAuditView (POS: Audit window and audit state of the panel)
 *
 * [OUTPUT]
 * - ChannelBudgetCard: One channel of the panel: today's spend against its limit, the limit box and the Enabled
 *   switch, the delete button, and the audit by sender that unfolds below.
 *
 * [POS]
 * Card of the channel budget panel. It counts the saves of its own channel that are still in flight, so the delete
 * button is off exactly while one of them is unsettled, whatever other channels do. A limit outside the stored range
 * is explained here and never sent. Deleting is only requested: the confirmation belongs to the panel. A channel no
 * chat has reached yet says so in a neutral note, since a key typed by hand may name a group that never talks to the
 * agent. What tells channels and senders apart is never cut off: a channel without a label is told apart by its key
 * alone, so its spend and delete button drop to their own line before the title gives way, a sender's figures do the
 * same below the sender id, and an identifier wider than the card breaks across lines.
 */

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconShield,
  IconLoader,
  IconTrash,
  IconChevronDown,
  IconChevronRight,
  IconUsers,
} from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import type { ChannelBudgetPolicy, ChannelBudgetPolicyFields, ChannelBudgetStatus } from '@/services/budget';
import ChannelLimitInput from './ChannelLimitInput';
import { CHANNEL_LIMIT_MAX_USD, CHANNEL_LIMIT_MIN_USD, isChannelLimitInRange } from './channelLimit';
import { AUDIT_DAYS, type ChannelAuditView } from './useChannelAudit';

const STATUS_COLORS: Record<string, { bar: string; text: string }> = {
  ok: { bar: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400' },
  warning: { bar: 'bg-amber-500', text: 'text-amber-600 dark:text-amber-400' },
  exceeded: { bar: 'bg-red-500', text: 'text-red-600 dark:text-red-400' },
  disabled: { bar: 'bg-muted', text: 'text-muted-foreground' },
};

interface ChannelBudgetCardProps {
  status: ChannelBudgetStatus;
  /** The stored policy; the limit box and the switch are left out while the panel has none for this channel. */
  policy: ChannelBudgetPolicy | undefined;
  /** The audit of this channel while it is unfolded, `null` while it is folded. */
  audit: ChannelAuditView | null;
  /** Writes the given fields of the policy; settles once the write and the read-back are done, stored or not. */
  onSave: (patch: Partial<ChannelBudgetPolicyFields>) => Promise<void>;
  onToggleAudit: () => void;
  /** Asks to delete this channel; nothing is deleted until the panel's confirmation is accepted. */
  onRequestDelete: () => void;
}

/** What an unfolded channel shows: that its audit is loading, could not be loaded, is empty, or each sender's spend. */
function AuditPanel({ audit }: { audit: ChannelAuditView }) {
  const t = useTranslations('settings.channelBudget');

  if (audit.status === 'loading') {
    return (
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground py-2">
        <IconLoader className="w-3 h-3 animate-spin" />
        {t('auditLoading')}
      </div>
    );
  }
  if (audit.status === 'failed') {
    return <div className="text-xs text-muted-foreground py-1">{t('auditFailed')}</div>;
  }
  if (audit.entries.length === 0) {
    return <div className="text-xs text-muted-foreground py-1">{t('auditEmpty')}</div>;
  }
  return (
    <>
      {audit.entries.map((entry) => {
        const pct = audit.totalUsd > 0 ? (entry.total_cost_usd / audit.totalUsd) * 100 : 0;
        return (
          <div key={entry.sender_id} className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span className="min-w-0 flex-auto text-[11px] text-muted-foreground font-mono break-all">
              {entry.sender_id}
            </span>
            <div className="flex items-center gap-2 shrink-0 ml-auto">
              <span className="text-[11px] text-muted-foreground tabular-nums">
                {entry.message_count} {t('auditMessages')}
              </span>
              <div className="w-16 h-1 rounded-full bg-black/5 dark:bg-white/5 overflow-hidden shrink-0">
                <div className="h-full rounded-full bg-primary/60 transition-all" style={{ width: `${pct}%` }} />
              </div>
              <span className="text-[11px] font-mono tabular-nums">${entry.total_cost_usd.toFixed(4)}</span>
            </div>
          </div>
        );
      })}
    </>
  );
}

const ChannelBudgetCard = ({
  status,
  policy,
  audit,
  onSave,
  onToggleAudit,
  onRequestDelete,
}: ChannelBudgetCardProps) => {
  const t = useTranslations('settings.channelBudget');
  // Saves of this channel that have not settled yet. A count, because the limit and the switch can be saved at once.
  const [inFlight, setInFlight] = useState(0);
  const busy = inFlight > 0;
  const colors = STATUS_COLORS[status.status] ?? STATUS_COLORS.disabled;
  const name = status.label || status.channel_key;

  const save = async (patch: Partial<ChannelBudgetPolicyFields>) => {
    setInFlight((count) => count + 1);
    try {
      await onSave(patch);
    } finally {
      setInFlight((count) => count - 1);
    }
  };

  const saveLimit = async (limit: number) => {
    if (!isChannelLimitInRange(limit)) {
      toast.warning(t('limitOutOfRange', { min: CHANNEL_LIMIT_MIN_USD, max: CHANNEL_LIMIT_MAX_USD }));
      return;
    }
    await save({ daily_limit_usd: limit });
  };

  return (
    <div className="p-3 rounded-lg border border-border/50 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <div className="flex items-center gap-2 min-w-0">
          <IconShield className={cn('w-4 h-4 shrink-0', colors.text)} />
          <span className="min-w-0 text-sm font-medium break-words">{name}</span>
          {status.label && (
            <span className="text-[10px] text-muted-foreground font-mono hidden sm:inline truncate">
              {status.channel_key}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-auto">
          <span className="text-xs font-mono tabular-nums">
            ${status.today_cost_usd.toFixed(4)} / ${status.daily_limit_usd.toFixed(2)}
          </span>
          <button
            onClick={onRequestDelete}
            disabled={busy}
            className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive-text transition-colors"
            title={t('delete')}
            aria-label={t('deleteNamed', { name })}
          >
            {busy ? <IconLoader className="w-3.5 h-3.5 animate-spin" /> : <IconTrash className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>
      <div className="h-1.5 rounded-full bg-black/5 dark:bg-white/5 overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all duration-500', colors.bar)}
          style={{ width: `${Math.min(status.usage_pct, 100)}%` }}
        />
      </div>
      {!status.known && <p className="text-xs text-muted-foreground">{t('unseenGroupNote')}</p>}
      {policy && (
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <div className="flex items-center gap-1">
            <span className="text-xs text-muted-foreground">{t('dailyLimit')}:</span>
            <span className="text-xs text-muted-foreground">$</span>
            <ChannelLimitInput value={policy.daily_limit_usd} label={t('dailyLimit')} onSave={saveLimit} />
          </div>
          <label className="flex items-center gap-1.5 cursor-pointer">
            <span className="text-xs text-muted-foreground">{t('enabled')}</span>
            <button
              role="switch"
              aria-checked={policy.enabled}
              aria-label={t('enabled')}
              onClick={() => save({ enabled: !policy.enabled })}
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
        onClick={onToggleAudit}
        aria-expanded={audit !== null}
        className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors pt-1"
      >
        {audit ? <IconChevronDown className="w-3 h-3" /> : <IconChevronRight className="w-3 h-3" />}
        <IconUsers className="w-3 h-3" />
        {t('auditDetails', { days: AUDIT_DAYS })}
      </button>
      {audit && (
        <div className="pt-1.5 space-y-1.5">
          <AuditPanel audit={audit} />
        </div>
      )}
    </div>
  );
};

export default ChannelBudgetCard;
