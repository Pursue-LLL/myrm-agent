'use client';

/**
 * [INPUT] @/components/primitives/badge::Badge (POS: 状态徽标), next-intl (POS: batchDirectory 文案), @/services/batch-directory::BatchProjectStatus (POS: 项目状态)
 * [OUTPUT] BATCH_TONE: 状态色调类名；BatchListStatusBadge / BatchProjectStatusBadge / BatchTaskStatusBadge: 列表行、详情页头部与任务行的状态徽标
 * [POS] BatchDirectory 状态到文案、图标与色调的唯一映射；后端新增的未知状态回退到草稿 / 待处理样式，不会让整页渲染失败。
 */

import type { ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { CheckCircle2, Clock, Loader2, XCircle } from 'lucide-react';
import { Badge } from '@/components/primitives/badge';
import type { BatchProjectStatus } from '@/services/batch-directory';

export const BATCH_TONE = {
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600',
  danger: 'border-destructive/30 bg-destructive/10 text-destructive-text',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-600',
  muted: 'border-muted bg-muted/50 text-muted-foreground',
  active: 'border-muted bg-muted/50 text-foreground',
} as const;

interface StatusStyle {
  labelKey: string;
  tone: string;
}

const PROJECT_STATUS: Record<BatchProjectStatus, StatusStyle> = {
  draft: { labelKey: 'statusDraft', tone: BATCH_TONE.muted },
  running: { labelKey: 'statusRunning', tone: BATCH_TONE.active },
  paused: { labelKey: 'statusPaused', tone: BATCH_TONE.warning },
  completed: { labelKey: 'statusCompleted', tone: BATCH_TONE.success },
  failed: { labelKey: 'statusFailed', tone: BATCH_TONE.danger },
  cancelled: { labelKey: 'statusCancelled', tone: BATCH_TONE.muted },
};

const LIST_ICON: Record<BatchProjectStatus, ReactNode> = {
  draft: <Clock className="size-3 mr-1" />,
  running: <Loader2 className="size-3 mr-1 animate-spin" />,
  paused: <Clock className="size-3 mr-1" />,
  completed: <CheckCircle2 className="size-3 mr-1 text-emerald-500" />,
  failed: <XCircle className="size-3 mr-1" />,
  cancelled: <XCircle className="size-3 mr-1" />,
};

interface TaskStatusStyle extends StatusStyle {
  icon: ReactNode;
}

const TASK_STATUS: Record<string, TaskStatusStyle> = {
  completed: {
    labelKey: 'taskStatusCompleted',
    icon: <CheckCircle2 className="size-3.5 text-emerald-500" />,
    tone: BATCH_TONE.success,
  },
  failed: {
    labelKey: 'taskStatusFailed',
    icon: <XCircle className="size-3.5 text-destructive-text" />,
    tone: BATCH_TONE.danger,
  },
  running: {
    labelKey: 'taskStatusRunning',
    icon: <Loader2 className="size-3.5 animate-spin" />,
    tone: BATCH_TONE.active,
  },
  archived: { labelKey: 'taskStatusArchived', icon: <Clock className="size-3.5" />, tone: BATCH_TONE.muted },
  in_review: { labelKey: 'taskStatusInReview', icon: <Clock className="size-3.5" />, tone: BATCH_TONE.warning },
  blocked: { labelKey: 'taskStatusBlocked', icon: <Clock className="size-3.5" />, tone: BATCH_TONE.muted },
  pending: { labelKey: 'taskStatusPending', icon: <Clock className="size-3.5" />, tone: BATCH_TONE.muted },
};

/** 列表行徽标：带状态图标；运行中沿用 Badge 默认的强调底色。 */
export function BatchListStatusBadge({ status }: { status: BatchProjectStatus }) {
  const t = useTranslations('batchDirectory');
  const style = PROJECT_STATUS[status] ?? PROJECT_STATUS.draft;
  return (
    <Badge className={status === 'running' ? undefined : style.tone} data-testid="bd-project-row-status">
      {LIST_ICON[status] ?? LIST_ICON.draft}
      {t(style.labelKey)}
    </Badge>
  );
}

/** 详情页头部徽标：只有文字，运行中用中性底色。 */
export function BatchProjectStatusBadge({ status }: { status: BatchProjectStatus }) {
  const t = useTranslations('batchDirectory');
  const style = PROJECT_STATUS[status] ?? PROJECT_STATUS.draft;
  return <Badge className={style.tone}>{t(style.labelKey)}</Badge>;
}

export function BatchTaskStatusBadge({ status }: { status: string }) {
  const t = useTranslations('batchDirectory');
  const style = TASK_STATUS[status] ?? TASK_STATUS.pending;
  return (
    <Badge className={style.tone}>
      {style.icon}
      {t(style.labelKey)}
    </Badge>
  );
}
