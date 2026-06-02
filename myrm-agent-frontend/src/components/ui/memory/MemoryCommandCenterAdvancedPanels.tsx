'use client';

/**
 * [INPUT]
 * @/services/memoryCommandCenter::MemoryCommandCenterResponse (POS: Frontend Personal Brain Command Center client)
 *
 * [OUTPUT]
 * MemoryAdvancedVerifyPanels: validation-focused Personal Brain Command Center panels.
 *
 * [POS]
 * 个人大脑指挥中心验证面板。展示 replay event trail、记忆瀑布流、运行级检索轨迹、Memory Doctor、eval checks、连接器、隐私信号和部署边界摘要。
 */

import type { ReactNode } from 'react';
import type { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type {
  MemoryCommandCenterResponse,
  MemoryCommandConnectorStatus,
  MemoryCommandDiagnosticRun,
  MemoryCommandEvalMetric,
  MemoryCommandPrivacySignal,
  MemoryCommandReplayEvent,
  MemoryCommandTraceRun,
  MemoryCommandTraceStep,
  MemoryCommandWaterfallStep,
} from '@/services/memoryCommandCenter';
import { MemoryDoctorPanel, type DoctorExecutableAction } from './MemoryCommandCenterDoctorPanel';

type MemoryTranslation = ReturnType<typeof useTranslations<'memory'>>;

const WATERFALL_PHASES = [
  'observe',
  'scan',
  'propose',
  'approve',
  'write',
  'index',
  'recall',
  'inject',
  'cite',
  'verify',
] as const;
const REPLAY_PHASES = ['observe', 'govern', 'write', 'index', 'recall', 'inject', 'verify'] as const;
const READINESS_STATUSES = [
  'ready',
  'active',
  'partial',
  'success',
  'warning',
  'error',
  'skipped',
  'critical',
  'missing',
  'manual_config_required',
  'planned',
] as const;
const CONNECTOR_IDS = ['claude_code', 'cursor', 'windsurf', 'codex', 'gemini_cli'] as const;
const PRIVACY_SIGNAL_IDS = ['approval_gate', 'sensitive_event_visibility', 'secret_redaction'] as const;
const EVAL_METRIC_IDS = [
  'event_coverage',
  'influence_coverage',
  'conflict_governance',
  'migration_readiness',
  'cross_session_transfer',
] as const;
type WaterfallPhase = (typeof WATERFALL_PHASES)[number];
type ReplayPhase = (typeof REPLAY_PHASES)[number];
type ReadinessStatus = (typeof READINESS_STATUSES)[number];
type ConnectorId = (typeof CONNECTOR_IDS)[number];
type PrivacySignalId = (typeof PRIVACY_SIGNAL_IDS)[number];
type EvalMetricId = (typeof EVAL_METRIC_IDS)[number];

const isWaterfallPhase = (value: string): value is WaterfallPhase => WATERFALL_PHASES.includes(value as WaterfallPhase);
const isReplayPhase = (value: string): value is ReplayPhase => REPLAY_PHASES.includes(value as ReplayPhase);
const isReadinessStatus = (value: string): value is ReadinessStatus =>
  READINESS_STATUSES.includes(value as ReadinessStatus);
const isConnectorId = (value: string): value is ConnectorId => CONNECTOR_IDS.includes(value as ConnectorId);
const isPrivacySignalId = (value: string): value is PrivacySignalId =>
  PRIVACY_SIGNAL_IDS.includes(value as PrivacySignalId);
const isEvalMetricId = (value: string): value is EvalMetricId => EVAL_METRIC_IDS.includes(value as EvalMetricId);

const formatTime = (value?: string | null): string =>
  value
    ? new Intl.DateTimeFormat(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }).format(new Date(value))
    : '';

const formatDuration = (value?: number | null): string => (value ? `${Math.round(value)}ms` : '-');

export const MemoryAdvancedVerifyPanels = ({
  snapshot,
  t,
  actionId,
  diagnosticRun,
  onDoctorAction,
  onConnectClick,
}: {
  snapshot: MemoryCommandCenterResponse;
  t: MemoryTranslation;
  actionId: string | null;
  diagnosticRun: MemoryCommandDiagnosticRun | null;
  onDoctorAction: (action: DoctorExecutableAction) => void;
  onConnectClick?: () => void;
}) => {
  const traceRuns = snapshot.trace_runs.slice(0, 6);
  return (
    <>
      <Panel title={t('commandCenter.waterfallTitle')} className="xl:col-span-2">
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
          {snapshot.waterfall.map((step) => (
            <WaterfallStep key={step.phase} step={step} t={t} />
          ))}
        </div>
      </Panel>
      <Panel title={t('commandCenter.replayEventsTitle')} className="xl:col-span-2">
        <div className="space-y-2">
          {snapshot.replay_events.slice(0, 8).map((event) => (
            <ReplayEventRow key={event.id} event={event} t={t} />
          ))}
          {!snapshot.replay_events.length && <EmptyState label={t('commandCenter.replayEmpty')} />}
        </div>
      </Panel>
      <Panel title={t('commandCenter.doctorTitle')} className="xl:col-span-2">
        <MemoryDoctorPanel
          snapshot={snapshot}
          t={t}
          actionId={actionId}
          diagnosticRun={diagnosticRun}
          onDoctorAction={onDoctorAction}
        />
      </Panel>
      <Panel title={t('commandCenter.retrievalTraceTitle')} className="xl:col-span-2">
        <div className="space-y-2">
          {traceRuns.map((run) => (
            <RetrievalTraceRunRow key={run.id} run={run} t={t} />
          ))}
          {!traceRuns.length && <EmptyState label={t('commandCenter.retrievalTraceEmpty')} />}
        </div>
      </Panel>
      <Panel title={t('commandCenter.evalTitle')}>
        <div className="space-y-2">
          {snapshot.eval_metrics.map((metric) => (
            <EvalMetricRow key={metric.id} metric={metric} t={t} />
          ))}
        </div>
      </Panel>
      <Panel
        title={t('commandCenter.connectorTitle')}
        action={
          onConnectClick ? (
            <button
              type="button"
              onClick={onConnectClick}
              className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary hover:bg-primary/20 transition-colors"
            >
              Connect
            </button>
          ) : undefined
        }
      >
        <div className="space-y-2">
          {snapshot.connectors.map((connector) => (
            <ConnectorRow key={connector.id} connector={connector} t={t} />
          ))}
        </div>
      </Panel>
      <Panel title={t('commandCenter.privacyTitle')}>
        <div className="space-y-2">
          {snapshot.privacy.map((signal) => (
            <PrivacyRow key={signal.id} signal={signal} t={t} />
          ))}
        </div>
      </Panel>
      <Panel title={t('commandCenter.planeSummaryTitle')}>
        <div className="grid gap-2">
          <FactRow
            label={t('commandCenter.planeContentVisibility')}
            value={t('commandCenter.contentVisibility.not_shared')}
          />
          <FactRow label={t('commandCenter.planeEventCount')} value={String(snapshot.plane_summary.event_count)} />
          <FactRow
            label={t('commandCenter.planeFailedEvents')}
            value={String(snapshot.plane_summary.failed_event_count)}
          />
          <FactRow label={t('commandCenter.planeQueueBacklog')} value={String(snapshot.plane_summary.queue_backlog)} />
          <FactRow
            label={t('commandCenter.planeRollbackHealth')}
            value={t(`commandCenter.rollbackHealthStatus.${snapshot.plane_summary.import_rollback_health_status}`)}
          />
          <FactRow
            label={t('commandCenter.planeRollbackBatches')}
            value={t('commandCenter.planeRollbackBatchCounts', {
              inProgress: snapshot.plane_summary.import_rollback_in_progress,
              failed: snapshot.plane_summary.import_rollback_failed,
              partial: snapshot.plane_summary.import_rollback_partial,
            })}
          />
          <FactRow
            label={t('commandCenter.planeRollbackItems')}
            value={t('commandCenter.planeRollbackItemCounts', {
              missing: snapshot.plane_summary.import_rollback_missing_items,
              failed: snapshot.plane_summary.import_rollback_failed_items,
            })}
          />
          <FactRow
            label={t('commandCenter.planeArchiveRestoreHealth')}
            value={t(`commandCenter.rollbackHealthStatus.${snapshot.plane_summary.archive_restore_health_status}`)}
          />
          <FactRow
            label={t('commandCenter.planeArchiveRestoreBatches')}
            value={t('commandCenter.planeArchiveRestoreBatchCounts', {
              inProgress: snapshot.plane_summary.archive_restore_in_progress,
              failed: snapshot.plane_summary.archive_restore_failed,
              partial: snapshot.plane_summary.archive_restore_partial,
              rollbackInProgress: snapshot.plane_summary.archive_restore_rollback_in_progress,
              rollbackFailed: snapshot.plane_summary.archive_restore_rollback_failed,
            })}
          />
          <FactRow
            label={t('commandCenter.planeArchiveRestoreItems')}
            value={t('commandCenter.planeArchiveRestoreItemCounts', {
              missing: snapshot.plane_summary.archive_restore_missing_items,
              failed: snapshot.plane_summary.archive_restore_failed_items,
            })}
          />
          <FactRow label={t('commandCenter.planeLastEvent')} value={formatTime(snapshot.plane_summary.last_event_at)} />
          <FactRow
            label={t('commandCenter.planeRedactionScope')}
            value={t('commandCenter.redactionScope.metadata_only')}
          />
          <FactRow
            label={t('commandCenter.planeSandboxIsolation')}
            value={t('commandCenter.sandboxIsolation.local_or_per_user_sandbox')}
          />
        </div>
      </Panel>
    </>
  );
};

const WaterfallStep = ({ step, t }: { step: MemoryCommandWaterfallStep; t: MemoryTranslation }) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="flex items-start justify-between gap-2">
      <div className="text-xs font-semibold text-foreground">
        {isWaterfallPhase(step.phase) ? t(`commandCenter.waterfallPhase.${step.phase}`) : step.phase}
      </div>
      <StatusPill status={step.status} t={t} />
    </div>
    <div className="mt-2 text-lg font-semibold text-foreground">{step.event_count}</div>
    <div className="mt-1 line-clamp-3 text-xs leading-5 text-muted-foreground">
      {formatWaterfallDescription(step, t)}
    </div>
    {step.latest_at && <div className="mt-2 text-[11px] text-muted-foreground">{formatTime(step.latest_at)}</div>}
  </div>
);

const ReplayEventRow = ({ event, t }: { event: MemoryCommandReplayEvent; t: MemoryTranslation }) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-sm font-medium text-foreground">
        {isReplayPhase(event.phase) ? t(`commandCenter.replayPhase.${event.phase}`) : event.phase}
      </span>
      <span className="text-[11px] text-muted-foreground">{formatTime(event.occurred_at)}</span>
    </div>
    <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{event.summary}</div>
  </div>
);

const RetrievalTraceRunRow = ({ run, t }: { run: MemoryCommandTraceRun; t: MemoryTranslation }) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div className="min-w-0">
        <div className="line-clamp-2 text-sm font-medium text-foreground">
          {run.query_preview || t('commandCenter.retrievalQueryFallback')}
        </div>
        <div className="mt-1 text-[11px] text-muted-foreground">{run.trace_id}</div>
      </div>
      <StatusPill status={run.status} t={t} />
    </div>
    <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-muted-foreground md:grid-cols-4">
      <FactInline label={t('commandCenter.retrievalResults')} value={String(run.result_count)} />
      <FactInline label={t('commandCenter.retrievalSteps')} value={String(run.steps.length)} />
      <FactInline label={t('commandCenter.retrievalDuration')} value={formatDuration(run.duration_ms)} />
      <FactInline label={t('commandCenter.retrievalTime')} value={formatTime(run.occurred_at)} />
    </div>
    <div className="mt-3 space-y-2">
      {run.steps.slice(0, 6).map((step) => (
        <RetrievalTraceStepRow key={step.id} step={step} t={t} />
      ))}
    </div>
  </div>
);

const RetrievalTraceStepRow = ({ step, t }: { step: MemoryCommandTraceStep; t: MemoryTranslation }) => (
  <div className="rounded-full border border-border/40 bg-background/70 px-3 py-2">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="min-w-0 truncate text-xs font-medium text-foreground">{step.title}</span>
      <StatusPill status={step.status} t={t} />
    </div>
    <div className="mt-1 line-clamp-2 text-[11px] leading-5 text-muted-foreground">{step.description}</div>
    <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-muted-foreground md:grid-cols-4">
      <FactInline label={t('commandCenter.retrievalPhase')} value={step.phase} />
      <FactInline label={t('commandCenter.retrievalOutputs')} value={String(step.output_count)} />
      <FactInline label={t('commandCenter.retrievalResults')} value={String(step.result_count)} />
      <FactInline label={t('commandCenter.retrievalDuration')} value={formatDuration(step.duration_ms)} />
    </div>
  </div>
);

const EvalMetricRow = ({ metric, t }: { metric: MemoryCommandEvalMetric; t: MemoryTranslation }) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm font-medium text-foreground">
        {isEvalMetricId(metric.id) ? t(`commandCenter.evalMetric.${metric.id}`) : metric.label}
      </span>
      <StatusPill status={metric.status} t={t} />
    </div>
    <div className="mt-2 h-1.5 rounded-full bg-muted">
      <div
        className="h-1.5 rounded-full bg-primary"
        style={{ width: `${Math.max(0, Math.min(metric.score, 100))}%` }}
      />
    </div>
    <div className="mt-2 text-xs leading-5 text-muted-foreground">
      {isEvalMetricId(metric.id)
        ? t(`commandCenter.evalEvidence.${metric.id}`, { score: metric.score })
        : metric.evidence}
    </div>
  </div>
);

const ConnectorRow = ({ connector, t }: { connector: MemoryCommandConnectorStatus; t: MemoryTranslation }) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm font-medium text-foreground">
        {isConnectorId(connector.id) ? t(`commandCenter.connector.${connector.id}.label`) : connector.label}
      </span>
      <StatusPill status={connector.status} t={t} />
    </div>
    <div className="mt-1 text-xs leading-5 text-muted-foreground">
      {isConnectorId(connector.id) ? t(`commandCenter.connector.${connector.id}.notes`) : connector.notes}
    </div>
  </div>
);

const PrivacyRow = ({ signal, t }: { signal: MemoryCommandPrivacySignal; t: MemoryTranslation }) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm font-medium text-foreground">
        {isPrivacySignalId(signal.id) ? t(`commandCenter.privacySignal.${signal.id}.label`) : signal.label}
      </span>
      <StatusPill status={signal.status} t={t} />
    </div>
    <div className="mt-1 text-xs leading-5 text-muted-foreground">
      {isPrivacySignalId(signal.id)
        ? t(`commandCenter.privacySignal.${signal.id}.evidence`, { count: signal.event_count })
        : signal.evidence}
    </div>
  </div>
);

const StatusPill = ({ status, t }: { status: string; t: MemoryTranslation }) => (
  <span className="shrink-0 rounded-full border border-border bg-background px-2 py-0.5 text-[11px] text-muted-foreground">
    {isReadinessStatus(status) ? t(`commandCenter.readinessStatus.${status}`) : status}
  </span>
);

const FactRow = ({ label, value }: { label: string; value: string }) => (
  <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-lg border border-border/50 bg-accent/20 px-3 py-2">
    <span className="truncate text-xs text-muted-foreground">{label}</span>
    <span className="truncate text-right text-xs font-medium text-foreground">{value || '-'}</span>
  </div>
);

const FactInline = ({ label, value }: { label: string; value: string }) => (
  <div className="min-w-0">
    <span className="block truncate">{label}</span>
    <span className="block truncate font-medium text-foreground">{value}</span>
  </div>
);

const Panel = ({
  title,
  className,
  children,
  action,
}: {
  title: string;
  className?: string;
  children: ReactNode;
  action?: ReactNode;
}) => (
  <div className={cn('space-y-3', className)}>
    <div className="flex items-center justify-between">
      <h4 className="text-sm font-semibold text-foreground">{title}</h4>
      {action}
    </div>
    {children}
  </div>
);

const EmptyState = ({ label }: { label: string }) => (
  <div className="rounded-lg border border-dashed border-border/70 p-4 text-sm text-muted-foreground">{label}</div>
);

const formatWaterfallDescription = (step: MemoryCommandWaterfallStep, t: MemoryTranslation): string => {
  if (!isWaterfallPhase(step.phase)) return step.description;
  if (step.event_count > 0) {
    return t('commandCenter.waterfallDescription.withEvents', { count: step.event_count });
  }
  if (step.phase === 'scan' || step.phase === 'index' || step.phase === 'inject') {
    return t(`commandCenter.waterfallDescription.${step.phase}`);
  }
  return t('commandCenter.waterfallDescription.default');
};
