// @orphan-ok Standalone rollback card for 10-minute snapshot undo window after destructive command execution
'use client';

import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Clock, RotateCcw, ShieldCheck, Undo2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';

interface DestructiveUndoCardProps {
  approvalId: string;
  snapshotId: string;
  executedAt?: string;
  onRollbackSuccess?: () => void;
}

const DEFAULT_ROLLBACK_WINDOW_MS = 10 * 60 * 1000; // 10 minutes

export function DestructiveUndoCard({
  approvalId,
  snapshotId,
  executedAt,
  onRollbackSuccess,
}: DestructiveUndoCardProps) {
  const t = useTranslations('toolApproval.destructiveUndo');
  const [isRollingBack, setIsRollingBack] = useState(false);
  const [hasRolledBack, setHasRolledBack] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const startTimeMs = executedAt ? new Date(executedAt).getTime() : now;
  const deadlineMs = startTimeMs + DEFAULT_ROLLBACK_WINDOW_MS;

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const remainingMs = Math.max(0, deadlineMs - now);
  const isExpired = remainingMs <= 0;

  const minutes = Math.floor(remainingMs / 60000);
  const seconds = Math.floor((remainingMs % 60000) / 1000);
  const timeFormatted = `${minutes}:${seconds.toString().padStart(2, '0')}`;

  const handleRollback = async () => {
    if (isRollingBack || isExpired || hasRolledBack) {
      return;
    }

    setIsRollingBack(true);
    try {
      const res = await fetch(`/api/v1/approvals/${encodeURIComponent(approvalId)}/rollback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!res.ok) {
        const errJson = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errJson.detail || t('rollbackFailed'));
      }

      setHasRolledBack(true);
      toast.success(t('rollbackSuccess'));
      onRollbackSuccess?.();
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('rollbackFailed');
      toast.error(msg);
    } finally {
      setIsRollingBack(false);
    }
  };

  if (hasRolledBack) {
    return (
      <div
        className="flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-xs text-emerald-800 dark:text-emerald-300"
        role="status"
      >
        <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
        <span>{t('rollbackSuccess')}</span>
      </div>
    );
  }

  if (isExpired) {
    return null;
  }

  return (
    <div
      className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-lg border border-amber-500/50 bg-amber-500/10 p-3.5 dark:border-amber-500/40 dark:bg-amber-950/20 text-xs"
      data-testid="destructive-undo-card"
    >
      <div className="space-y-1">
        <div className="flex items-center gap-2 font-semibold text-amber-800 dark:text-amber-200">
          <Undo2 className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
          <span>{t('title')}</span>
          <span className="inline-flex items-center gap-1 font-mono text-[11px] text-amber-700 dark:text-amber-300 font-normal">
            <Clock className="h-3 w-3" aria-hidden="true" />
            {timeFormatted}
          </span>
        </div>
        <p className="text-muted-foreground leading-relaxed">{t('description')}</p>
        <div className="text-[11px] font-mono text-muted-foreground">
          快照指针: {snapshotId.slice(0, 16)}
        </div>
      </div>

      <div className="shrink-0 pt-1 sm:pt-0">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={handleRollback}
          disabled={isRollingBack}
          className="border-amber-500/50 text-amber-800 dark:text-amber-200 hover:bg-amber-500/20 text-xs h-8 gap-1.5"
        >
          <RotateCcw className={`h-3.5 w-3.5 ${isRollingBack ? 'animate-spin' : ''}`} aria-hidden="true" />
          {t('rollbackButton')}
        </Button>
      </div>
    </div>
  );
}
