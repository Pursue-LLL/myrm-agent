'use client';

import { useTranslations } from 'next-intl';
import { AlertTriangle, CheckCircle2, Clock3, ShieldAlert, XCircle } from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import type { SkillEvolutionEvent } from '@/services/statistics';

interface SkillEventListProps {
  events: SkillEvolutionEvent[];
}

const STATUS_CONFIG = {
  PENDING_REVIEW: {
    icon: Clock3,
    color: 'text-amber-500',
    bg: 'bg-amber-500/10',
    labelKey: 'pendingReview' as const,
  },
  AUTO_APPLIED: {
    icon: IconGlow,
    color: 'text-emerald-500',
    bg: 'bg-emerald-500/10',
    labelKey: 'autoApplied' as const,
  },
  FAILED_SCAN: {
    icon: AlertTriangle,
    color: 'text-rose-500',
    bg: 'bg-rose-500/10',
    labelKey: 'failedScan' as const,
  },
  BLOCKED_LOCKED: {
    icon: ShieldAlert,
    color: 'text-orange-500',
    bg: 'bg-orange-500/10',
    labelKey: 'blockedLocked' as const,
  },
  APPROVED: {
    icon: CheckCircle2,
    color: 'text-sky-500',
    bg: 'bg-sky-500/10',
    labelKey: 'approved' as const,
  },
  REJECTED: {
    icon: XCircle,
    color: 'text-red-500',
    bg: 'bg-red-500/10',
    labelKey: 'rejected' as const,
  },
  APPLY_FAILED: {
    icon: AlertTriangle,
    color: 'text-orange-500',
    bg: 'bg-orange-500/10',
    labelKey: 'applyFailed' as const,
  },
};

export default function SkillEventList({ events }: SkillEventListProps) {
  const t = useTranslations('growthDashboard.skillEvents');

  const formatRelativeDate = (isoStr: string): string => {
    const date = new Date(isoStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return t('today');
    if (diffDays === 1) return t('yesterday');
    if (diffDays < 7) return t('daysAgo', { count: diffDays });
    if (diffDays < 30) return t('weeksAgo', { count: Math.floor(diffDays / 7) });
    return date.toLocaleDateString();
  };

  if (events.length === 0) {
    return <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">{t('empty')}</div>;
  }

  return (
    <div className="max-h-64 space-y-2 overflow-y-auto">
      {events.map((event, idx) => {
        const cfg = STATUS_CONFIG[event.status] ?? STATUS_CONFIG.PENDING_REVIEW;
        const Icon = cfg.icon;

        return (
          <div
            key={`${event.source}-${event.skill_id ?? event.skill_name}-${idx}`}
            className="flex items-start gap-3 rounded-lg p-2.5 transition-colors hover:bg-muted/50"
          >
            <div className={cn('mt-0.5 rounded-md p-1.5', cfg.bg)}>
              <Icon className={cn('h-3.5 w-3.5', cfg.color)} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium text-foreground">{event.skill_name}</span>
                <span className={cn('rounded px-1.5 py-0.5 text-xs font-medium', cfg.bg, cfg.color)}>
                  {t(cfg.labelKey)}
                </span>
                <span className="rounded border border-border/60 bg-muted/50 px-1.5 py-0.5 text-[11px] text-muted-foreground">
                  {event.source === 'draft' ? t('sourceDraft') : t('sourceEvolution')}
                </span>
              </div>
              <p className="mt-0.5 truncate text-xs text-muted-foreground">
                {t('growthType', { type: event.growth_type })}
              </p>
              {event.change_summary && (
                <p className="mt-1 truncate text-xs text-muted-foreground">{event.change_summary}</p>
              )}
            </div>
            <span className="mt-0.5 flex-shrink-0 text-xs text-muted-foreground">
              {formatRelativeDate(event.created_at)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
