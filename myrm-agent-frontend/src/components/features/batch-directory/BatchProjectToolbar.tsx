'use client';

/**
 * [INPUT] ./useBatchProjectActions::BatchProjectActions (POS: 动作与忙碌标志), ./batchProjectModel::BatchProjectFlags (POS: 项目状态派生标志), ./BatchConfirmAlert (POS: 二次确认弹窗)
 * [OUTPUT] BatchProjectToolbar: 详情页头部的动作栏（刷新、全部通过、重试失败、重跑、暂停、恢复、取消、删除）
 * [POS] 按项目状态显示可用动作：进行中可暂停 / 取消，已暂停可恢复 / 取消，终态可重跑 / 删除；破坏性或影响面大的动作先二次确认。
 */

import { useTranslations } from 'next-intl';
import { CheckCheck, Loader2, Pause, Play, RefreshCw, RotateCcw, XCircle } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import type { BatchProjectDetail } from '@/services/batch-directory';
import { BatchConfirmAlert } from './BatchConfirmAlert';
import type { BatchProjectFlags } from './batchProjectModel';
import type { BatchProjectActions } from './useBatchProjectActions';

interface BatchProjectToolbarProps {
  project: BatchProjectDetail;
  flags: BatchProjectFlags;
  actions: BatchProjectActions;
  onRefresh: () => Promise<void>;
}

export function BatchProjectToolbar({ project, flags, actions, onRefresh }: BatchProjectToolbarProps) {
  const t = useTranslations('batchDirectory');
  const { busy, run, remove } = actions;
  const { running, paused, terminal, active, inReviewCount, hasRetryable } = flags;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="outline" size="sm" onClick={() => void onRefresh()}>
        <RefreshCw className="size-4 mr-1" />
        {t('refresh')}
      </Button>
      {!terminal && inReviewCount > 0 && (
        <BatchConfirmAlert
          trigger={
            <Button variant="outline" size="sm" disabled={busy.approveAll || busy.pause || busy.resume}>
              {busy.approveAll ? (
                <Loader2 className="size-4 mr-1 animate-spin" />
              ) : (
                <CheckCheck className="size-4 mr-1" />
              )}
              {t('approveAllAction', { count: inReviewCount })}
            </Button>
          }
          title={t('confirmApproveAllTitle', { count: inReviewCount })}
          description={t('confirmApproveAllDescription')}
          confirmLabel={t('confirmApproveAllAction')}
          onConfirm={() => void run('approveAll')}
        />
      )}
      {hasRetryable && !paused && (
        <Button variant="outline" size="sm" onClick={() => void run('retry')} disabled={busy.retry || busy.rerun}>
          {busy.retry ? <Loader2 className="size-4 mr-1 animate-spin" /> : <RotateCcw className="size-4 mr-1" />}
          {t('retryAction')}
        </Button>
      )}
      {terminal && (
        <BatchConfirmAlert
          trigger={
            <Button variant="outline" size="sm" disabled={busy.rerun}>
              {busy.rerun ? <Loader2 className="size-4 mr-1 animate-spin" /> : <RefreshCw className="size-4 mr-1" />}
              {t('rerunAction')}
            </Button>
          }
          title={t('confirmRerunTitle', { name: project.name })}
          description={t('confirmRerunDescription')}
          confirmLabel={t('confirmRerunAction')}
          onConfirm={() => void run('rerun')}
        />
      )}
      {running && (
        <BatchConfirmAlert
          trigger={
            <Button variant="outline" size="sm" disabled={busy.pause || busy.cancel}>
              {busy.pause ? <Loader2 className="size-4 mr-1 animate-spin" /> : <Pause className="size-4 mr-1" />}
              {t('pauseAction')}
            </Button>
          }
          title={t('confirmPauseTitle', { name: project.name })}
          description={t('confirmPauseDescription')}
          confirmLabel={t('confirmPauseAction')}
          onConfirm={() => void run('pause')}
        />
      )}
      {paused && (
        <Button variant="outline" size="sm" onClick={() => void run('resume')} disabled={busy.resume || busy.cancel}>
          {busy.resume ? <Loader2 className="size-4 mr-1 animate-spin" /> : <Play className="size-4 mr-1" />}
          {t('resumeAction')}
        </Button>
      )}
      {active && (
        <BatchConfirmAlert
          trigger={
            <Button variant="outline" size="sm" disabled={busy.cancel}>
              {busy.cancel ? <Loader2 className="size-4 mr-1 animate-spin" /> : null}
              {t('cancelAction')}
            </Button>
          }
          title={t('confirmCancelTitle', { name: project.name })}
          description={t('confirmCancelDescription')}
          confirmLabel={t('confirmCancelAction')}
          onConfirm={() => void run('cancel')}
        />
      )}
      {terminal && (
        <BatchConfirmAlert
          trigger={
            <Button variant="ghost" size="sm" className="text-destructive-text">
              <XCircle className="size-4 mr-1" />
              {t('deleteAction')}
            </Button>
          }
          title={t('confirmDeleteTitle', { name: project.name })}
          description={t('confirmDeleteDescription')}
          confirmLabel={t('confirmDeleteAction')}
          onConfirm={() => void remove()}
          destructive
        />
      )}
    </div>
  );
}
