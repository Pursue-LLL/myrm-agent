'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from 'sonner';
import { Skeleton } from '@/components/primitives/skeleton';
import { IconHeart } from '@/components/features/icons/PremiumIcons';
import SettingsSection from '../SettingsSection';
import { fetchCommitments, dismissCommitment, snoozeCommitment, type Commitment } from '@/services/commitments';

const KIND_ICON: Record<string, React.ReactNode> = {
  event_check_in: '◆',
  deadline_check: '▲',
  care_check_in: <IconHeart className="inline w-3.5 h-3.5 text-rose-500" />,
  open_loop: '◎',
};

const SENSITIVITY_STYLES: Record<string, string> = {
  routine: 'bg-muted text-muted-foreground',
  personal: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
  care: 'bg-rose-500/15 text-rose-600 dark:text-rose-400',
};

const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  sent: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  dismissed: 'bg-muted text-muted-foreground',
  snoozed: 'bg-violet-500/15 text-violet-600 dark:text-violet-400',
  expired: 'bg-muted text-muted-foreground line-through',
};

function formatDueWindow(earliestMs: number, _latestMs: number): string {
  const now = Date.now();
  const diffMs = earliestMs - now;
  const diffHours = Math.round(diffMs / (1000 * 60 * 60));

  if (diffMs < 0) {
    const overdue = Math.abs(diffHours);
    return overdue < 24 ? `${overdue}h overdue` : `${Math.round(overdue / 24)}d overdue`;
  }
  if (diffHours < 1) return '<1h';
  if (diffHours < 24) return `${diffHours}h`;
  return `${Math.round(diffHours / 24)}d`;
}

function formatDueWindowZh(earliestMs: number, _latestMs: number): string {
  const now = Date.now();
  const diffMs = earliestMs - now;
  const diffHours = Math.round(diffMs / (1000 * 60 * 60));

  if (diffMs < 0) {
    const overdue = Math.abs(diffHours);
    return overdue < 24 ? `逾期${overdue}小时` : `逾期${Math.round(overdue / 24)}天`;
  }
  if (diffHours < 1) return '不到1小时';
  if (diffHours < 24) return `${diffHours}小时后`;
  return `${Math.round(diffHours / 24)}天后`;
}

type StatusFilter = 'all' | 'pending' | 'sent' | 'dismissed' | 'expired';

const CommitmentPanel = memo(function CommitmentPanel() {
  const t = useTranslations('commitments');
  const [items, setItems] = useState<Commitment[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<StatusFilter>('all');
  const isZh = t('title') !== 'Follow-up Tracking';

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const params: Record<string, string> = {};
      if (filter !== 'all') params.status = filter;
      const res = await fetchCommitments(filter !== 'all' ? { status: filter } : undefined);
      setItems(res.items);
    } catch {
      toast.error(t('loadError'));
    } finally {
      setLoading(false);
    }
  }, [filter, t]);

  useEffect(() => {
    load();
  }, [load]);

  const handleDismiss = useCallback(
    async (id: string) => {
      try {
        await dismissCommitment(id);
        setItems((prev) => prev.filter((i) => i.id !== id));
        toast.success(t('dismissed'));
      } catch {
        toast.error(t('actionError'));
      }
    },
    [t],
  );

  const handleSnooze = useCallback(
    async (id: string) => {
      const untilMs = Date.now() + 4 * 60 * 60 * 1000;
      try {
        await snoozeCommitment(id, untilMs);
        setItems((prev) =>
          prev.map((i) => (i.id === id ? { ...i, status: 'snoozed' as const, snoozed_until_ms: untilMs } : i)),
        );
        toast.success(t('snoozed'));
      } catch {
        toast.error(t('actionError'));
      }
    },
    [t],
  );

  const pendingCount = items.filter((i) => i.status === 'pending' || i.status === 'snoozed').length;

  return (
    <SettingsSection title={t('title')} description={t('description')}>
      <div className="space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          {(['all', 'pending', 'sent', 'dismissed', 'expired'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                'rounded-full px-3 py-1 text-xs font-medium transition-colors',
                filter === f
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/80',
              )}
            >
              {t(`filter.${f}`)}
              {f === 'pending' && pendingCount > 0 && (
                <span className="ml-1 rounded-full bg-amber-500/20 px-1.5 text-amber-600 dark:text-amber-400">
                  {pendingCount}
                </span>
              )}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full rounded-lg" />
            <Skeleton className="h-20 w-full rounded-lg" />
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-lg border border-dashed border-muted-foreground/25 p-8 text-center">
            <p className="text-sm text-muted-foreground">{t('empty')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <CommitmentCard
                key={item.id}
                item={item}
                isZh={isZh}
                t={t}
                onDismiss={handleDismiss}
                onSnooze={handleSnooze}
              />
            ))}
          </div>
        )}
      </div>
    </SettingsSection>
  );
});

interface CommitmentCardProps {
  item: Commitment;
  isZh: boolean;
  t: ReturnType<typeof useTranslations>;
  onDismiss: (id: string) => void;
  onSnooze: (id: string) => void;
}

const CommitmentCard = memo<CommitmentCardProps>(function CommitmentCard({ item, isZh, t, onDismiss, onSnooze }) {
  const isActive = item.status === 'pending' || item.status === 'snoozed';
  const dueText = isZh
    ? formatDueWindowZh(item.due_earliest_ms, item.due_latest_ms)
    : formatDueWindow(item.due_earliest_ms, item.due_latest_ms);

  return (
    <div
      className={cn(
        'rounded-lg border p-3 transition-colors',
        isActive ? 'border-border bg-card' : 'border-border/50 bg-muted/30',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium">{KIND_ICON[item.kind] ?? '·'}</span>
            <span
              className={cn('rounded-full px-1.5 py-0.5 text-[10px] font-medium', SENSITIVITY_STYLES[item.sensitivity])}
            >
              {t(`sensitivity.${item.sensitivity}`)}
            </span>
            <span className={cn('rounded-full px-1.5 py-0.5 text-[10px] font-medium', STATUS_STYLES[item.status])}>
              {t(`status.${item.status}`)}
            </span>
            <span className="text-[10px] text-muted-foreground">{dueText}</span>
          </div>
          <p className="text-sm leading-relaxed">{item.suggested_text}</p>
          <p className="text-xs text-muted-foreground">{item.reason}</p>
        </div>

        {isActive && (
          <div className="flex shrink-0 gap-1.5">
            <button
              onClick={() => onSnooze(item.id)}
              className="rounded-full px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted transition-colors"
              title={t('snoozeAction')}
            >
              {t('snoozeAction')}
            </button>
            <button
              onClick={() => onDismiss(item.id)}
              className="rounded-full px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
              title={t('dismissAction')}
            >
              {t('dismissAction')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
});

export default CommitmentPanel;
