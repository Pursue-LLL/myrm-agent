import {
  IconBan,
  IconCheckCircle,
  IconClock,
  IconLoader,
  IconXCircle,
} from '@/components/features/icons/PremiumIcons';

export interface ActiveGoal {
  goal_id: string;
  session_id: string;
  objective: string;
  status: string;
  tokens_used: number;
  created_at: string;
}

export const POLL_FAST_MS = 3_000;
export const POLL_SLOW_MS = 30_000;
export const IDLE_STOP_THRESHOLD = 3;

export const STATUS_CONFIG = {
  running: {
    icon: IconLoader,
    className: 'text-primary animate-spin',
    dotColor: 'bg-primary',
  },
  completed: {
    icon: IconCheckCircle,
    className: 'text-emerald-500 dark:text-emerald-400',
    dotColor: 'bg-emerald-500 dark:bg-emerald-400',
  },
  failed: {
    icon: IconXCircle,
    className: 'text-destructive',
    dotColor: 'bg-destructive',
  },
  timed_out: {
    icon: IconClock,
    className: 'text-amber-500 dark:text-amber-400',
    dotColor: 'bg-amber-500 dark:bg-amber-400',
  },
  cancelled: {
    icon: IconBan,
    className: 'text-muted-foreground',
    dotColor: 'bg-muted-foreground',
  },
} as const;

export const GOAL_STATUS_STYLES: Record<string, { dotColor: string; i18nKey: string }> = {
  active: { dotColor: 'bg-primary', i18nKey: 'goalStatusActive' },
  paused: { dotColor: 'bg-amber-500', i18nKey: 'goalStatusPaused' },
  pending_approval: { dotColor: 'bg-violet-500', i18nKey: 'goalStatusPendingApproval' },
  budget_limited: { dotColor: 'bg-orange-500', i18nKey: 'goalStatusBudgetLimited' },
  needs_human_review: { dotColor: 'bg-rose-500', i18nKey: 'goalStatusNeedsReview' },
  queued: { dotColor: 'bg-muted-foreground', i18nKey: 'goalStatusQueued' },
};
