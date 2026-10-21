'use client';

/**
 * [INPUT]
 * @/services/cron::{getCronJob, pauseCronJob} (POS: Frontend Cron API client)
 * @/lib/cron/buildCronAuditFields (POS: Cron six-field audit snapshot builder)
 * @/lib/cron/cronCreateAuditGate::{resumeJobAfterAuditConfirm, needsSettingsAuditGate} (POS: Settings audit resume gate)
 *
 * [OUTPUT]
 * CronJobAuditPanel: Hermes-style six-field cron create audit with confirm gate.
 *
 * [POS]
 * Shared cron audit surface for chat cards, create dialog, and Settings job detail.
 */

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { AlertTriangle, CheckCircle2, ClipboardCheck, Loader2, PauseCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { getCronJob, pauseCronJob } from '@/services/cron';
import type { CronJob } from '@/services/cron.types';
import { buildCronAuditFields, isCronAuditConfirmed, markCronAuditConfirmed } from '@/lib/cron/buildCronAuditFields';
import { resumeJobAfterAuditConfirm } from '@/lib/cron/cronCreateAuditGate';
import { cn } from '@/lib/utils/classnameUtils';

interface CronJobAuditPanelProps {
  jobId: string;
  /** Optional prefetched job for first paint — always refetched when updated_at changes. */
  initialJob?: CronJob | null;
  className?: string;
  compact?: boolean;
  /** Settings create flow: confirm resumes a paused job. */
  enforceSettingsGate?: boolean;
  /** Chat/detail flow: offer manual pause while reviewing. */
  showManualPause?: boolean;
  /** Chat flow: confirm means acknowledgment only, not a schedule gate. */
  acknowledgmentOnly?: boolean;
  onJobChange?: (job: CronJob) => void;
}

export const CronJobAuditPanel = memo<CronJobAuditPanelProps>(
  ({
    jobId,
    initialJob = null,
    className,
    compact = false,
    enforceSettingsGate = false,
    showManualPause = false,
    acknowledgmentOnly = false,
    onJobChange,
  }) => {
    const t = useTranslations('cron.audit');
    const router = useRouter();
    const [job, setJob] = useState<CronJob | null>(initialJob);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [confirmed, setConfirmed] = useState(() => isCronAuditConfirmed(jobId));
    const [actionPending, setActionPending] = useState(false);

    const jobRevision = initialJob?.updated_at ?? null;

    useEffect(() => {
      setConfirmed(isCronAuditConfirmed(jobId));
    }, [jobId]);

    useEffect(() => {
      if (initialJob) {
        setJob(initialJob);
      }
    }, [initialJob]);

    useEffect(() => {
      let cancelled = false;
      setLoading(!initialJob);
      setError(null);
      void getCronJob(jobId)
        .then((fetched) => {
          if (!cancelled) {
            setJob(fetched);
            setLoading(false);
          }
        })
        .catch((err: unknown) => {
          if (!cancelled) {
            setError(err instanceof Error ? err.message : t('loadFailed'));
            setLoading(false);
          }
        });
      return () => {
        cancelled = true;
      };
    }, [jobId, jobRevision, t, initialJob]);

    const fields = useMemo(() => (job ? buildCronAuditFields(job) : []), [job]);

    const handleConfirm = useCallback(async () => {
      if (!job) {
        return;
      }
      setActionPending(true);
      try {
        if (enforceSettingsGate && job.status === 'paused') {
          const resumed = await resumeJobAfterAuditConfirm(jobId);
          setJob(resumed);
          onJobChange?.(resumed);
        }
        markCronAuditConfirmed(jobId);
        setConfirmed(true);
      } catch {
        toast.error(t('resumeFail'));
      } finally {
        setActionPending(false);
      }
    }, [enforceSettingsGate, job, jobId, t, onJobChange]);

    const handlePause = useCallback(async () => {
      if (!job || job.status !== 'active') {
        return;
      }
      setActionPending(true);
      try {
        await pauseCronJob(job.id);
        const paused = await getCronJob(job.id);
        setJob(paused);
        onJobChange?.(paused);
        toast.success(t('pauseSuccess'));
      } catch {
        toast.error(t('pauseFail'));
      } finally {
        setActionPending(false);
      }
    }, [job, t, onJobChange]);

    if (loading && !job) {
      return (
        <div className={cn('flex items-center gap-2 text-sm text-muted-foreground py-2', className)}>
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>{t('loading')}</span>
        </div>
      );
    }

    if (error || !job) {
      return <div className={cn('text-sm text-destructive py-2', className)}>{error ?? t('loadFailed')}</div>;
    }

    const showPausedHint = enforceSettingsGate && job.status === 'paused' && !confirmed;
    const canManualPause = showManualPause && job.status === 'active' && !confirmed;

    return (
      <div
        className={cn(
          'rounded-lg border border-border/60 bg-muted/20',
          compact ? 'px-3 py-2.5 space-y-2' : 'px-4 py-3 space-y-3',
          className,
        )}
      >
        <div className="flex items-start gap-2">
          <ClipboardCheck className="h-4 w-4 text-primary shrink-0 mt-0.5" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-foreground">{t('title')}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {acknowledgmentOnly ? t('subtitleAck') : t('subtitle')}
            </p>
            {showPausedHint ? (
              <p className="text-xs text-amber-700 dark:text-amber-400 mt-1">{t('pausedHint')}</p>
            ) : null}
          </div>
          {confirmed ? (
            <span className="inline-flex items-center gap-1 text-[11px] text-green-600 dark:text-green-400 bg-green-500/10 px-2 py-0.5 rounded-full shrink-0">
              <CheckCircle2 className="h-3 w-3" />
              {t('confirmed')}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full shrink-0">
              <AlertTriangle className="h-3 w-3" />
              {t('pendingConfirm')}
            </span>
          )}
        </div>

        <dl className="space-y-2">
          {fields.map((field, index) => (
            <div key={field.id} className="grid grid-cols-1 sm:grid-cols-[7rem_1fr] gap-0.5 sm:gap-3 text-sm">
              <dt className="text-muted-foreground text-xs sm:text-sm font-medium">
                {index + 1}. {t(`fields.${field.id}`)}
              </dt>
              <dd className="text-foreground break-words text-xs sm:text-sm">{field.value}</dd>
            </div>
          ))}
        </dl>

        <div className="flex flex-wrap items-center justify-end gap-2 pt-1 border-t border-border/40">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            onClick={() => router.push(`/settings/cron?job=${job.id}`)}
          >
            {t('openSettings')}
          </Button>
          {canManualPause ? (
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1"
              disabled={actionPending}
              onClick={() => void handlePause()}
            >
              {actionPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <PauseCircle className="h-3 w-3" />}
              {t('pauseTask')}
            </Button>
          ) : null}
          {!confirmed ? (
            <Button
              size="sm"
              className="h-7 text-xs gap-1"
              disabled={actionPending}
              onClick={() => void handleConfirm()}
            >
              {actionPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
              {enforceSettingsGate ? t('confirmAndResume') : t('confirm')}
            </Button>
          ) : null}
        </div>
      </div>
    );
  },
);

CronJobAuditPanel.displayName = 'CronJobAuditPanel';
