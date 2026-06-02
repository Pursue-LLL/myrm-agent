'use client';

/**
 * [INPUT]
 * @/services/memoryCommandCenter::getMemoryCommandCenter (POS: Frontend Personal Brain Command Center client)
 * @/services/memoryArchive::dryRunRollbackMemoryImport, exportMemoryArchive (POS: Frontend Memory Archive and import API client)
 *
 * [OUTPUT]
 * MemoryCommandCenter: Personal Brain Command Center container with health dashboard, governance, diagnostics, archive export, rollback preview orchestration, and SSE-backed live memory stream.
 *
 * [POS]
 * 个人大脑指挥中心容器。按观察、理解、治理、验证分区展示记忆快照，编排治理动作、Memory Doctor 动作和导入回滚预演强确认。
 */

import { lazy, memo, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/hooks/useToast';
import SessionAnalyticsDialog from '@/components/ui/settings/sections/SessionAnalyticsDialog';
import { ConnectWizardDialog } from './ConnectWizardDialog';
import {
  isMemoryTimelineEvent,
  LIVE_STREAM_LIMIT,
  mergeLiveStreamEvents,
  resolveReplaySessionId,
} from '@/components/ui/memory/memoryLiveStream';
import {
  dryRunRollbackMemoryImport,
  exportMemoryArchive,
  rollbackMemoryImport,
  type MemoryArchiveSection,
  type MemoryImportRollbackPreviewResponse,
  type MemoryImportRollbackResponse,
} from '@/services/memoryArchive';
import { ActSection, ObserveSection, UnderstandSection, VerifySection } from './MemoryCommandCenterPanels';
import {
  getMemoryCommandCenter,
  getConsolidationLastSummary,
  rollbackConsolidation,
  runMemoryCommandAction,
  runMemoryDiagnosticRepair,
  type ConsolidationLastSummary,
  type MemoryCommandCenterResponse,
  type MemoryCommandDiagnosticRun,
  type MemoryCommandGovernanceItem,
  type MemoryCommandTimelineEvent,
} from '@/services/memoryCommandCenter';
import { MemoryArchiveRestoreDialog } from './MemoryArchiveRestoreDialog';
import { CommandCenterSkeleton, MetricTile, RollbackPreviewDialog, StatusPill } from './MemoryCommandCenterChrome';
import { useMemoryArchiveRestoreActions } from './useMemoryArchiveRestoreActions';
import { useMemoryDemoSeed } from './useMemoryDemoSeed';
import { IconGlow } from '@/components/ui/icons/PremiumIcons';
import MemoryHealthDashboard from './MemoryHealthDashboard';

const MemoryKnowledgeGraph = lazy(() => import('./MemoryKnowledgeGraph'));

const SECTIONS = ['observe', 'understand', 'act', 'verify', 'graph'] as const;
const HEALTH_STATUSES = ['healthy', 'degraded', 'critical', 'unknown'] as const;

type Section = (typeof SECTIONS)[number];
type HealthStatus = (typeof HEALTH_STATUSES)[number];
type DoctorAction = 'run_diagnostics' | 'run_health_refresh';

const formatTime = (value: string): string =>
  new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));

const isHealthStatus = (value: string): value is HealthStatus => HEALTH_STATUSES.includes(value as HealthStatus);

const MemoryCommandCenter = memo<{ className?: string }>(({ className }) => {
  const t = useTranslations('memory');
  const [snapshot, setSnapshot] = useState<MemoryCommandCenterResponse | null>(null);
  const [activeSection, setActiveSection] = useState<Section>('observe');
  const [loading, setLoading] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [diagnosticRun, setDiagnosticRun] = useState<MemoryCommandDiagnosticRun | null>(null);
  const [rollbackPreview, setRollbackPreview] = useState<MemoryImportRollbackPreviewResponse | null>(null);
  const [rollbackResult, setRollbackResult] = useState<MemoryImportRollbackResponse | null>(null);
  const [rollbackDialogOpen, setRollbackDialogOpen] = useState(false);
  const [connectWizardOpen, setConnectWizardOpen] = useState(false);
  const [liveStream, setLiveStream] = useState<MemoryCommandTimelineEvent[]>([]);
  const [replaySessionId, setReplaySessionId] = useState<string | null>(null);
  const [healthExpanded, setHealthExpanded] = useState(false);
  const [consolidationSummary, setConsolidationSummary] = useState<ConsolidationLastSummary | null>(null);

  const loadSnapshot = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [snap, consolSummary] = await Promise.all([
        getMemoryCommandCenter(),
        getConsolidationLastSummary().catch(() => null),
      ]);
      setSnapshot(snap);
      setConsolidationSummary(consolSummary);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('unknownError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  const archiveRestore = useMemoryArchiveRestoreActions({ setActionId, loadSnapshot });
  const { seedDemoData, isSeeding, rollbackDemoData, isRollingBack, hasDemoData } = useMemoryDemoSeed({
    setActionId,
    loadSnapshot,
  });
  useEffect(() => {
    void loadSnapshot();
  }, [loadSnapshot]);

  useEffect(() => {
    const refresh = () => void loadSnapshot();
    window.addEventListener('health_status_updated', refresh);
    window.addEventListener('app_resync_required', refresh);
    return () => {
      window.removeEventListener('health_status_updated', refresh);
      window.removeEventListener('app_resync_required', refresh);
    };
  }, [loadSnapshot]);

  useEffect(() => {
    if (snapshot?.live_stream) {
      setLiveStream(snapshot.live_stream.slice(0, LIVE_STREAM_LIMIT));
    }
  }, [snapshot?.live_stream]);

  useEffect(() => {
    const onMemoryOperation = (event: Event) => {
      const incoming = (event as CustomEvent<unknown>).detail;
      if (!isMemoryTimelineEvent(incoming)) return;
      setLiveStream((previous) => mergeLiveStreamEvents(previous, incoming));
    };
    window.addEventListener('memory_operation', onMemoryOperation);
    return () => window.removeEventListener('memory_operation', onMemoryOperation);
  }, []);

  const openReplayForEvent = useCallback(
    (event: MemoryCommandTimelineEvent) => {
      const sessionId = resolveReplaySessionId(event);
      if (!sessionId) {
        toast({
          title: t('commandCenter.replayUnavailable'),
          description: t('commandCenter.replayUnavailableHint'),
        });
        return;
      }
      setReplaySessionId(sessionId);
    },
    [t],
  );

  const runAction = useCallback(
    async (item: MemoryCommandGovernanceItem, action: 'approve' | 'reject') => {
      setActionId(`${item.target_kind}:${item.id}:${action}`);
      try {
        await runMemoryCommandAction({
          target_kind: item.target_kind,
          target_id: item.id,
          action,
          memory_type: item.title,
        });
        toast({ title: t('commandCenter.actionSuccess') });
        await loadSnapshot();
      } catch (err) {
        toast({
          title: t('commandCenter.actionFailed'),
          description: err instanceof Error ? err.message : t('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setActionId(null);
      }
    },
    [loadSnapshot, t],
  );

  const runDoctorAction = useCallback(
    async (action: DoctorAction) => {
      setActiveSection('verify');
      setActionId(`diagnostics:${action}`);
      try {
        const result = await runMemoryDiagnosticRepair({ plan_id: action, mode: 'execute' });
        if (result.run) setDiagnosticRun(result.run);
        toast({
          title:
            result.result.status === 'completed'
              ? t('commandCenter.diagnosticCompleted')
              : t('commandCenter.diagnosticCompletedWithFindings'),
          description: result.result.message,
        });
        await loadSnapshot();
      } catch (err) {
        toast({
          title: t('commandCenter.actionFailed'),
          description: err instanceof Error ? err.message : t('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setActionId(null);
      }
    },
    [loadSnapshot, t],
  );

  const previewRollbackImport = useCallback(
    async (importBatchId: string) => {
      setActionId(`migration:rollback-preview:${importBatchId}`);
      try {
        setRollbackPreview(await dryRunRollbackMemoryImport(importBatchId));
        setRollbackResult(null);
        setRollbackDialogOpen(true);
      } catch (err) {
        toast({
          title: t('commandCenter.actionFailed'),
          description: err instanceof Error ? err.message : t('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setActionId(null);
      }
    },
    [t],
  );

  const confirmRollbackImport = useCallback(async () => {
    if (!rollbackPreview) return;
    const importBatchId = rollbackPreview.import_batch_id;
    setActionId(`migration:rollback:${importBatchId}`);
    try {
      const result = await rollbackMemoryImport(importBatchId);
      setRollbackResult(result);
      toast({
        title: t('commandCenter.rollbackSuccess'),
        description: t('commandCenter.rollbackSuccessDesc', {
          count: result.total_rolled_back,
          missing: result.missing_items,
          failed: result.failed_items,
        }),
      });
      await loadSnapshot();
    } catch (err) {
      toast({
        title: t('commandCenter.actionFailed'),
        description: err instanceof Error ? err.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setActionId(null);
    }
  }, [loadSnapshot, rollbackPreview, t]);

  const handleConsolidationRollback = useCallback(async () => {
    setActionId('consolidation:rollback');
    try {
      const result = await rollbackConsolidation();
      toast({
        title: t('commandCenter.consolidationRollbackSuccess'),
        description: t('commandCenter.consolidationRollbackSuccessDesc', {
          count: result.rolled_back,
          conflicts: result.skipped_conflict,
        }),
      });
      await loadSnapshot();
    } catch (err) {
      toast({
        title: t('commandCenter.actionFailed'),
        description: err instanceof Error ? err.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setActionId(null);
    }
  }, [loadSnapshot, t]);

  const exportArchive = useCallback(async () => {
    setActionId('archive:export');
    try {
      const { archive } = await exportMemoryArchive();
      const payload = JSON.stringify(archive, null, 2);
      const blob = new Blob([payload], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `myrm-memory-archive-${archive.manifest.created_at.replaceAll(':', '-')}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      toast({
        title: t('commandCenter.archiveExportSuccess'),
        description: t('commandCenter.archiveExportSuccessDesc', {
          count: totalArchiveItems(archive.manifest.sections),
          sections: archive.manifest.sections.length,
        }),
      });
    } catch (err) {
      toast({
        title: t('commandCenter.actionFailed'),
        description: err instanceof Error ? err.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setActionId(null);
    }
  }, [t]);

  const generatedAt = useMemo(() => (snapshot ? formatTime(snapshot.generated_at) : ''), [snapshot]);

  if (loading && !snapshot) return <CommandCenterSkeleton className={className} />;

  if (error && !snapshot) {
    return (
      <section className={cn('rounded-xl border border-destructive/20 bg-destructive/5 p-4', className)}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-foreground">{t('commandCenter.title')}</h3>
            <p className="mt-1 text-sm text-destructive">{t('commandCenter.loadFailed')}</p>
          </div>
          <button type="button" onClick={loadSnapshot} className="rounded-lg border border-border px-3 py-2 text-xs">
            {t('commandCenter.refresh')}
          </button>
        </div>
      </section>
    );
  }

  if (!snapshot) return null;

  const healthStatus = isHealthStatus(snapshot.health.status) ? snapshot.health.status : 'unknown';

  return (
    <section className={cn('space-y-4 rounded-xl border border-border/60 bg-background/60 p-4', className)}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-foreground">{t('commandCenter.title')}</h3>
            <button
              type="button"
              onClick={() => setHealthExpanded((prev) => !prev)}
              className="inline-flex items-center gap-1 transition-opacity hover:opacity-80"
              aria-expanded={healthExpanded}
              aria-controls="memory-health-dashboard"
            >
              <StatusPill
                label={
                  snapshot.health.total != null
                    ? `${t(`commandCenter.healthStatus.${healthStatus}`)} ${snapshot.health.total}`
                    : t(`commandCenter.healthStatus.${healthStatus}`)
                }
                status={healthStatus}
              />
              <svg
                viewBox="0 0 16 16"
                className={cn(
                  'h-3 w-3 text-muted-foreground/60 transition-transform duration-200',
                  healthExpanded && 'rotate-180',
                )}
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M4 6l4 4 4-4" />
              </svg>
            </button>
          </div>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">{t('commandCenter.description')}</p>
          <p className="mt-1 text-xs text-muted-foreground/80">
            {t('commandCenter.lastUpdated', { time: generatedAt })}
          </p>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
          {snapshot.health.total === 0 && !hasDemoData && (
            <button
              type="button"
              onClick={seedDemoData}
              disabled={actionId !== null}
              className="w-full rounded-lg border border-primary/30 bg-primary/10 px-3 py-2 text-xs font-medium text-primary transition-colors hover:bg-primary/20 disabled:opacity-60 sm:w-auto flex items-center justify-center gap-1.5"
            >
              <IconGlow className="h-3.5 w-3.5" />
              {isSeeding
                ? t('commandCenter.seedingDemo', { fallback: 'Seeding...' })
                : t('commandCenter.seedDemo', { fallback: '体验 30 秒记忆魔法' })}
            </button>
          )}
          {hasDemoData && (
            <button
              type="button"
              onClick={rollbackDemoData}
              disabled={actionId !== null}
              className="w-full rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs font-medium text-destructive transition-colors hover:bg-destructive/20 disabled:opacity-60 sm:w-auto flex items-center justify-center gap-1.5"
            >
              {isRollingBack
                ? t('commandCenter.rollingBackDemo', { fallback: 'Removing...' })
                : t('commandCenter.rollbackDemo', { fallback: '清理 Demo 数据' })}
            </button>
          )}
          <button
            type="button"
            onClick={exportArchive}
            disabled={actionId === 'archive:export'}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-60 sm:w-auto"
          >
            {actionId === 'archive:export' ? t('commandCenter.exportingArchive') : t('commandCenter.exportArchive')}
          </button>
          <button
            type="button"
            onClick={archiveRestore.selectFile}
            disabled={actionId === 'archive:restore-dry-run'}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-60 sm:w-auto"
          >
            {actionId === 'archive:restore-dry-run'
              ? t('commandCenter.reviewingArchiveRestore')
              : t('commandCenter.restoreArchive')}
          </button>
          <input
            ref={archiveRestore.inputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={archiveRestore.handleFile}
          />
          <button
            type="button"
            onClick={loadSnapshot}
            disabled={loading}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-60 sm:w-auto"
          >
            {loading ? t('commandCenter.refreshing') : t('commandCenter.refresh')}
          </button>
        </div>
      </div>

      {healthExpanded && (
        <div
          id="memory-health-dashboard"
          className="rounded-lg border border-border/50 bg-accent/10 p-4 animate-in fade-in slide-in-from-top-1 duration-200"
        >
          <MemoryHealthDashboard health={snapshot.health} t={t} />
        </div>
      )}

      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <MetricTile label={t('commandCenter.totalMemories')} value={snapshot.overview.total_memories} />
        <MetricTile label={t('commandCenter.pendingReview')} value={snapshot.overview.pending_memories} />
        <MetricTile label={t('commandCenter.influenceCount')} value={snapshot.cost.cited_memory_refs} />
        <MetricTile label={t('commandCenter.estimatedMemoryTokens')} value={snapshot.cost.estimated_memory_tokens} />
      </div>

      <div className="grid grid-cols-3 gap-1 rounded-lg border border-border/60 bg-accent/20 p-1 sm:grid-cols-5">
        {SECTIONS.map((section) => (
          <button
            key={section}
            type="button"
            onClick={() => setActiveSection(section)}
            className={cn(
              'rounded-full px-3 py-2 text-xs font-medium transition-colors',
              activeSection === section
                ? 'bg-background text-foreground'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t(`commandCenter.sections.${section}`)}
          </button>
        ))}
      </div>

      {activeSection === 'observe' && (
        <ObserveSection snapshot={snapshot} liveStream={liveStream} t={t} onEventClick={openReplayForEvent} />
      )}
      {activeSection === 'understand' && <UnderstandSection snapshot={snapshot} t={t} />}
      {activeSection === 'act' && (
        <ActSection
          snapshot={snapshot}
          t={t}
          actionId={actionId}
          onAction={runAction}
          onDoctorAction={runDoctorAction}
          onRollbackImport={previewRollbackImport}
          consolidationSummary={consolidationSummary}
          onConsolidationRollback={handleConsolidationRollback}
        />
      )}
      {activeSection === 'verify' && (
        <VerifySection
          snapshot={snapshot}
          t={t}
          actionId={actionId}
          diagnosticRun={diagnosticRun}
          onDoctorAction={runDoctorAction}
          onConnectClick={() => setConnectWizardOpen(true)}
        />
      )}
      {activeSection === 'graph' && (
        <Suspense
          fallback={
            <div className="flex items-center justify-center rounded-lg border border-dashed border-border/70 p-12">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          }
        >
          <MemoryKnowledgeGraph />
        </Suspense>
      )}
      <RollbackPreviewDialog
        open={rollbackDialogOpen}
        preview={rollbackPreview}
        result={rollbackResult}
        loading={actionId === `migration:rollback:${rollbackPreview?.import_batch_id ?? ''}`}
        t={t}
        onOpenChange={setRollbackDialogOpen}
        onConfirm={confirmRollbackImport}
      />
      <ConnectWizardDialog open={connectWizardOpen} onOpenChange={setConnectWizardOpen} />
      {replaySessionId ? (
        <SessionAnalyticsDialog sessionId={replaySessionId} onClose={() => setReplaySessionId(null)} />
      ) : null}
      <MemoryArchiveRestoreDialog
        open={archiveRestore.open}
        preview={archiveRestore.preview}
        result={archiveRestore.result}
        rollbackPreview={archiveRestore.rollbackPreview}
        rollbackResult={archiveRestore.rollbackResult}
        selectedSections={archiveRestore.selectedSections}
        reviewing={actionId === 'archive:restore-dry-run'}
        restoring={actionId === 'archive:restore-confirm'}
        rollingBack={Boolean(actionId?.startsWith('archive:restore-rollback:'))}
        onOpenChange={archiveRestore.setOpen}
        onToggleSection={archiveRestore.toggleSection}
        onConfirm={archiveRestore.confirm}
        onRollback={archiveRestore.rollback}
      />
    </section>
  );
});

MemoryCommandCenter.displayName = 'MemoryCommandCenter';

const totalArchiveItems = (sections: MemoryArchiveSection[]): number =>
  sections.reduce((total, section) => total + section.item_count, 0);

export default MemoryCommandCenter;
