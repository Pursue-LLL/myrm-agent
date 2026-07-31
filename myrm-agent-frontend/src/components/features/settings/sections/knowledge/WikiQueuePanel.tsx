'use client';

/**
 * [INPUT]
 * @/services/wikiService::wikiService, QueueStatus, CompileRunStatus (POS: Wiki REST client with agent scope)
 * ./wikiQueuePoll::{computeShouldPollQueue, queueStatsDiverge, QUEUE_POLL_INTERVAL_MS, SILENT_FAIL_STALE_THRESHOLD, shouldShowStaleRefreshBanner} (POS: queue poll eligibility pure logic)
 *
 * [OUTPUT]
 * WikiQueuePanel: Settings Wiki ingestion queue monitor with compile phase bar, circuit pause controls, and active polling.
 *
 * [POS]
 * Settings Knowledge Wiki Queue tab. Surfaces compile queue stats, failure details, retry/resume actions, and live refresh while active.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { IconCheckCircle, IconXCircle, IconRotateCcw } from '@/components/features/icons/PremiumIcons';
import { wikiService, type CompileRunStatus, type QueueStatus } from '@/services/wikiService';
import { WikiScopeChip } from './WikiScopeChip';
import {
  QUEUE_POLL_INTERVAL_MS,
  computeShouldPollQueue,
  queueStatsDiverge,
  shouldShowStaleRefreshBanner,
} from './wikiQueuePoll';
import { WikiCompilePhaseBar } from './WikiCompilePhaseBar';
import type { WikiIngestSnapshot } from './useWikiIngestSubscription';

interface WikiQueuePanelProps {
  agentScopeId?: string | null;
  scopeLabel: string;
  liveIngestConnected?: boolean;
  liveIngestSnapshot?: WikiIngestSnapshot | null;
}

function errorKindLabel(kind: string | undefined, t: ReturnType<typeof useTranslations<'settings.wiki.queue'>>): string {
  if (!kind) {
    return t('errorKindUnknown');
  }
  const labels: Record<string, string> = {
    auth: t('errorKind.auth'),
    billing: t('errorKind.billing'),
    rate_limit: t('errorKind.rate_limit'),
    overloaded: t('errorKind.overloaded'),
    timeout: t('errorKind.timeout'),
    io_missing: t('errorKind.io_missing'),
    cancelled: t('errorKind.cancelled'),
  };
  return labels[kind] ?? t('errorKindUnknown');
}

export function WikiQueuePanel({
  agentScopeId,
  scopeLabel,
  liveIngestConnected = false,
  liveIngestSnapshot = null,
}: WikiQueuePanelProps) {
  const t = useTranslations('settings.wiki.queue');
  const [queueData, setQueueData] = useState<QueueStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [isRetryingAll, setIsRetryingAll] = useState(false);
  const [isResuming, setIsResuming] = useState(false);
  const [refreshStale, setRefreshStale] = useState(false);
  const loadRequestRef = useRef(0);
  const silentFailCountRef = useRef(0);

  const loadQueue = useCallback(async (options?: { silent?: boolean }) => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;

    if (!options?.silent) {
      setIsLoading(true);
    }
    try {
      const data = await wikiService.getQueueStatus(agentScopeId);
      if (loadRequestRef.current !== requestId) {
        return;
      }
      setQueueData(data);
      silentFailCountRef.current = 0;
      setRefreshStale(false);
    } catch (error) {
      console.error('Failed to load queue:', error);
      if (loadRequestRef.current !== requestId) {
        return;
      }
      if (options?.silent) {
        silentFailCountRef.current += 1;
        setRefreshStale(shouldShowStaleRefreshBanner(silentFailCountRef.current));
      } else {
        toast.error(t('loadFailed'));
      }
    } finally {
      if (loadRequestRef.current === requestId && !options?.silent) {
        setIsLoading(false);
      }
    }
  }, [agentScopeId, t]);

  useEffect(() => {
    void loadQueue();
  }, [loadQueue]);

  const compileRun: CompileRunStatus | null | undefined =
    liveIngestSnapshot?.compile_run ?? queueData?.compile_run;
  const isPaused = compileRun?.state === 'paused';
  const mergedStats = liveIngestSnapshot?.stats ?? queueData?.stats;
  const shouldPollQueue = !liveIngestConnected && computeShouldPollQueue(queueData);

  useEffect(() => {
    if (!liveIngestSnapshot || !liveIngestConnected) {
      return;
    }
    if (liveIngestSnapshot.sync_required || !queueData) {
      void loadQueue({ silent: true });
      return;
    }
    if (queueStatsDiverge(liveIngestSnapshot.stats, queueData.stats)) {
      void loadQueue({ silent: true });
      return;
    }
    setQueueData((prev) => {
      if (!prev) {
        return prev;
      }
      const nextCompileRun = liveIngestSnapshot.compile_run ?? prev.compile_run;
      if (nextCompileRun === prev.compile_run) {
        return prev;
      }
      return {
        ...prev,
        compile_run: nextCompileRun,
      };
    });
  }, [liveIngestConnected, liveIngestSnapshot, loadQueue, queueData]);

  useEffect(() => {
    if (!shouldPollQueue) {
      return;
    }
    const intervalId = window.setInterval(() => {
      void loadQueue({ silent: true });
    }, QUEUE_POLL_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [shouldPollQueue, loadQueue]);

  const handleCancel = async () => {
    setIsCancelling(true);
    try {
      await wikiService.cancelQueue(agentScopeId);
      toast.success(t('cancelSuccess'));
      await loadQueue();
    } catch (error) {
      console.error('Failed to cancel queue:', error);
      toast.error(t('cancelFailed'));
    } finally {
      setIsCancelling(false);
    }
  };

  const handleRetryTransient = async () => {
    setIsRetrying(true);
    try {
      await wikiService.retryFailedQueue(agentScopeId);
      toast.success(t('retrySuccess'));
      await loadQueue();
    } catch (error) {
      console.error('Failed to retry queue:', error);
      toast.error(t('retryFailedError'));
    } finally {
      setIsRetrying(false);
    }
  };

  const handleRetryAllFailed = async () => {
    setIsRetryingAll(true);
    try {
      await wikiService.retryAllFailedQueue(agentScopeId);
      toast.success(t('retryAllSuccess'));
      await loadQueue();
    } catch (error) {
      console.error('Failed to retry all failed queue items:', error);
      toast.error(t('retryAllFailedError'));
    } finally {
      setIsRetryingAll(false);
    }
  };

  const handleResume = async () => {
    setIsResuming(true);
    try {
      await wikiService.resumeCompileCircuit(agentScopeId);
      toast.success(t('resumeSuccess'));
      await loadQueue();
    } catch (error) {
      console.error('Failed to resume compile:', error);
      toast.error(t('resumeFailed'));
    } finally {
      setIsResuming(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <IconCheckCircle className="w-5 h-5" />
            {t('title')}
          </div>
          <WikiScopeChip scopeLabel={scopeLabel} />
        </CardTitle>
        <CardDescription>{t('description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {refreshStale && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-900/80 dark:text-amber-100/80">
            {t('refreshStale')}
          </div>
        )}

        {isLoading && !queueData ? (
          <div className="text-center py-4 text-muted-foreground">{t('loading')}</div>
        ) : queueData ? (
          <>
            {isPaused && compileRun && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 space-y-3">
                <div className="text-sm font-medium text-amber-800 dark:text-amber-200">{t('pausedTitle')}</div>
                <p className="text-sm text-amber-900/80 dark:text-amber-100/80">
                  {compileRun.pause_reason || t('pausedDefaultReason')}
                </p>
                {compileRun.primary_error_kind && (
                  <p className="text-xs text-amber-800/70 dark:text-amber-200/70">
                    {t('pausedErrorKind', {
                      kind: errorKindLabel(compileRun.primary_error_kind, t),
                    })}
                  </p>
                )}
                <Button size="sm" variant="outline" disabled={isResuming} onClick={() => void handleResume()}>
                  {isResuming ? t('resuming') : t('resumeCompile')}
                </Button>
              </div>
            )}

            {compileRun && !isPaused && (
              <WikiCompilePhaseBar
                compileRun={compileRun}
                pendingCount={mergedStats?.pending ?? 0}
                processingCount={mergedStats?.processing ?? 0}
              />
            )}

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="text-center p-3 bg-yellow-500/10 rounded-lg">
                <div className="text-2xl font-bold text-yellow-600">{mergedStats?.pending ?? 0}</div>
                <div className="text-xs text-muted-foreground">{t('statsPending')}</div>
              </div>
              <div className="text-center p-3 bg-blue-500/10 rounded-lg">
                <div className="text-2xl font-bold text-blue-600">{mergedStats?.processing ?? 0}</div>
                <div className="text-xs text-muted-foreground">{t('statsProcessing')}</div>
              </div>
              <div className="text-center p-3 bg-green-500/10 rounded-lg">
                <div className="text-2xl font-bold text-green-600">{mergedStats?.completed ?? 0}</div>
                <div className="text-xs text-muted-foreground">{t('statsCompleted')}</div>
              </div>
              <div className="text-center p-3 bg-red-500/10 rounded-lg">
                <div className="text-2xl font-bold text-red-600">{mergedStats?.failed ?? 0}</div>
                <div className="text-xs text-muted-foreground">{t('statsFailed')}</div>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void handleCancel()}
                disabled={isCancelling || (mergedStats?.pending ?? 0) === 0}
              >
                <IconXCircle className="w-4 h-4 mr-1" />
                {isCancelling ? t('cancelling') : t('cancelAll')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void handleRetryTransient()}
                disabled={isRetrying || isPaused || (mergedStats?.failed ?? 0) === 0}
              >
                <IconRotateCcw className="w-4 h-4 mr-1" />
                {isRetrying ? t('retrying') : t('retryTransient')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void handleRetryAllFailed()}
                disabled={isRetryingAll || (mergedStats?.failed ?? 0) === 0}
              >
                <IconRotateCcw className="w-4 h-4 mr-1" />
                {isRetryingAll ? t('retrying') : t('retryAllFailed')}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => void loadQueue()}>
                {t('refresh')}
              </Button>
            </div>

            {queueData.pending_items.length > 0 && (
              <div className="mt-4 space-y-2">
                <div className="text-sm font-medium">{t('pendingItems')}</div>
                <div className="max-h-48 overflow-y-auto space-y-1">
                  {queueData.pending_items.map((item) => (
                    <div key={item.id} className="flex items-center justify-between px-3 py-2 bg-muted rounded text-xs">
                      <span className="truncate max-w-[70%]">{item.file_path.split('/').pop()}</span>
                      <span className="text-muted-foreground">
                        {(item.retry_count ?? 0) > 0 ? `×${item.retry_count}` : item.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {queueData.failed_items.length > 0 && (
              <div className="mt-4 space-y-2">
                <div className="text-sm font-medium">{t('failedItems')}</div>
                <div className="max-h-48 overflow-y-auto space-y-1">
                  {queueData.failed_items.map((item) => (
                    <div key={item.id} className="px-3 py-2 bg-red-500/5 border border-red-500/10 rounded text-xs space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-medium">{item.file_path.split('/').pop()}</span>
                        <span className="shrink-0 text-red-600 dark:text-red-400">
                          {errorKindLabel(item.error_kind, t)}
                        </span>
                      </div>
                      {item.error_message && (
                        <p className="text-muted-foreground line-clamp-2">{item.error_message}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
