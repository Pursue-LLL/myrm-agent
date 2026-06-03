'use client';

/**
 * [INPUT]
 * @/services/memoryCommandCenter::MemoryCommandCenterResponse (POS: Frontend Personal Brain Command Center client)
 * ./MemoryCommandCenterAdvancedPanels::MemoryAdvancedVerifyPanels (POS: 个人大脑指挥中心验证面板)
 *
 * [OUTPUT]
 * ObserveSection, UnderstandSection, ActSection, VerifySection: Personal Brain Command Center section panels.
 *
 * [POS]
 * 个人大脑指挥中心基础展示面板。按观察、理解、治理、验证分区展示记忆快照、证据、治理和运行状态。
 */

import { lazy, Suspense, type ReactNode } from 'react';
import { useEffect, useRef } from 'react';
import type { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type {
  ConsolidationLastSummary,
  MemoryCommandCenterResponse,
  MemoryCommandConflictItem,
  MemoryCommandDiagnosticRun,
  MemoryCommandGovernanceItem,
  MemoryCommandInfluenceItem,
  MemoryCommandReplayOverlay,
  MemoryCommandTimelineEvent,
} from '@/services/memoryCommandCenter';
import type { MemoryType } from '@/services/memory';
import { MemoryAdvancedVerifyPanels } from './MemoryCommandCenterAdvancedPanels';
import { resolveReplaySessionId } from './memoryLiveStream';

const MemoryHealthDashboard = lazy(() => import('./MemoryHealthDashboard'));

const MEMORY_TYPES: MemoryType[] = [
  'profile',
  'semantic',
  'episodic',
  'procedural',
  'conversation',
  'claim',
  'task_digest',
];
const SPACE_KINDS = ['global', 'agent', 'channel', 'conversation', 'task', 'shared', 'unknown'] as const;
const RECORD_STATUSES = ['pending', 'approved', 'rejected', 'active', 'archived', 'success'] as const;
const RUNTIME_STATUSES = ['available', 'unavailable', 'custom', 'not_used', 'proxied_by_sandbox'] as const;
const COVERAGE_STATUSES = ['not_tracked', 'partial', 'complete'] as const;

type MemoryTranslation = ReturnType<typeof useTranslations<'memory'>>;
type SpaceKind = (typeof SPACE_KINDS)[number];
type RecordStatus = (typeof RECORD_STATUSES)[number];
type RuntimeStatus = (typeof RUNTIME_STATUSES)[number];
type CoverageStatus = (typeof COVERAGE_STATUSES)[number];
type DoctorAction = 'run_diagnostics' | 'run_health_refresh';

const formatTime = (value: string): string =>
  new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));

const isMemoryType = (value: string): value is MemoryType => MEMORY_TYPES.includes(value as MemoryType);
const isSpaceKind = (value: string): value is SpaceKind => SPACE_KINDS.includes(value as SpaceKind);
const isRecordStatus = (value: string): value is RecordStatus => RECORD_STATUSES.includes(value as RecordStatus);
const isRuntimeStatus = (value: string): value is RuntimeStatus => RUNTIME_STATUSES.includes(value as RuntimeStatus);
const isCoverageStatus = (value: string): value is CoverageStatus =>
  COVERAGE_STATUSES.includes(value as CoverageStatus);

export const ObserveSection = ({
  snapshot,
  liveStream,
  t,
  onEventClick,
}: {
  snapshot: MemoryCommandCenterResponse;
  liveStream: MemoryCommandTimelineEvent[];
  t: MemoryTranslation;
  onEventClick?: (event: MemoryCommandTimelineEvent) => void;
}) => (
  <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
    <Panel title={t('commandCenter.typesTitle')}>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {MEMORY_TYPES.map((type) => (
          <MetricTile key={type} label={t(`types.${type}`)} value={snapshot.overview.by_type[type] ?? 0} dense />
        ))}
      </div>
    </Panel>
    <Panel title={t('commandCenter.liveStreamTitle')} liveHint={t('commandCenter.liveStreamHint')}>
      <EventList
        events={liveStream}
        t={t}
        emptyLabel={t('commandCenter.timelineEmpty')}
        live
        onEventClick={onEventClick}
      />
    </Panel>
    <Panel title={t('commandCenter.healthDashboard.totalScore')} className="xl:col-span-2">
      <Suspense
        fallback={
          <div className="flex items-center justify-center rounded-lg border border-dashed border-border/70 p-12">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        }
      >
        <MemoryHealthDashboard health={snapshot.health} t={t} />
      </Suspense>
    </Panel>
    <Panel title={t('commandCenter.spacesTitle')} className="xl:col-span-2">
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {snapshot.spaces.slice(0, 12).map((space) => (
          <div key={`${space.kind}:${space.namespace}`} className="rounded-lg border border-border/50 bg-accent/20 p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-foreground">{space.label || space.namespace}</div>
                <div className="mt-1 truncate text-xs text-muted-foreground">{space.namespace}</div>
              </div>
              <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">
                {translateSpaceKind(space.kind, t)}
              </span>
            </div>
            {space.kind === 'shared' && (
              <div className="mt-2 text-xs text-muted-foreground">
                {t('commandCenter.bindingCount', { count: space.binding_count })}
              </div>
            )}
          </div>
        ))}
      </div>
    </Panel>
  </div>
);

export const UnderstandSection = ({ snapshot, t }: { snapshot: MemoryCommandCenterResponse; t: MemoryTranslation }) => (
  <div className="space-y-4">
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel title={t('commandCenter.influenceTitle')}>
        {snapshot.influence.length ? (
          <div className="space-y-2">
            {snapshot.influence.map((item) => (
              <InfluenceRow key={item.id} item={item} t={t} />
            ))}
          </div>
        ) : (
          <EmptyState label={t('commandCenter.influenceEmpty')} />
        )}
      </Panel>
      <Panel title={t('commandCenter.conflictsTitle')}>
        {snapshot.conflicts.length ? (
          <div className="space-y-2">
            {snapshot.conflicts.map((item) => (
              <ConflictRow key={item.id} item={item} t={t} />
            ))}
          </div>
        ) : (
          <EmptyState label={t('commandCenter.conflictsEmpty')} />
        )}
      </Panel>
    </div>
  </div>
);

export const ActSection = ({
  snapshot,
  t,
  actionId,
  onAction,
  onDoctorAction,
  onRollbackImport,
  consolidationSummary,
  onConsolidationRollback,
}: {
  snapshot: MemoryCommandCenterResponse;
  t: MemoryTranslation;
  actionId: string | null;
  onAction: (item: MemoryCommandGovernanceItem, action: 'approve' | 'reject') => void;
  onDoctorAction: (action: DoctorAction) => void;
  onRollbackImport: (importBatchId: string) => void;
  consolidationSummary?: ConsolidationLastSummary | null;
  onConsolidationRollback?: () => void;
}) => (
  <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
    <div className="space-y-4">
      <Panel title={t('commandCenter.governanceTitle')}>
        {snapshot.governance.length ? (
          <div className="space-y-2">
            {snapshot.governance.map((item) => (
              <GovernanceRow
                key={`${item.kind}:${item.id}`}
                item={item}
                t={t}
                actionId={actionId}
                onAction={onAction}
              />
            ))}
          </div>
        ) : (
          <EmptyState label={t('commandCenter.governanceEmpty')} />
        )}
      </Panel>
      {consolidationSummary?.available && (
        <Panel title={t('commandCenter.consolidationRollbackTitle')}>
          <ConsolidationRollbackCard
            summary={consolidationSummary}
            t={t}
            loading={actionId === 'consolidation:rollback'}
            onRollback={onConsolidationRollback}
          />
        </Panel>
      )}
    </div>
    <Panel title={t('commandCenter.migrationTitle')}>
      <MigrationPanel
        snapshot={snapshot}
        t={t}
        actionId={actionId}
        onDoctorAction={onDoctorAction}
        onRollbackImport={onRollbackImport}
      />
    </Panel>
  </div>
);

export const VerifySection = ({
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
  onDoctorAction: (action: DoctorAction) => void;
  onConnectClick?: () => void;
}) => (
  <div className="grid gap-4 xl:grid-cols-2">
    <Panel title={t('commandCenter.runtimeTitle')}>
      <RuntimePanel snapshot={snapshot} t={t} />
    </Panel>
    <Panel title={t('commandCenter.costTitle')}>
      <CostPanel snapshot={snapshot} t={t} />
    </Panel>
    <Panel title={t('commandCenter.replayTitle')} className="xl:col-span-2">
      {snapshot.replay.length ? (
        <div className="grid gap-2 md:grid-cols-2">
          {snapshot.replay.map((item) => (
            <ReplayRow key={item.chat_id} item={item} t={t} />
          ))}
        </div>
      ) : (
        <EmptyState label={t('commandCenter.replayEmpty')} />
      )}
    </Panel>
    <MemoryAdvancedVerifyPanels
      snapshot={snapshot}
      t={t}
      actionId={actionId}
      diagnosticRun={diagnosticRun}
      onDoctorAction={onDoctorAction}
      onConnectClick={onConnectClick}
    />
  </div>
);

const GovernanceRow = ({
  item,
  t,
  actionId,
  onAction,
}: {
  item: MemoryCommandGovernanceItem;
  t: MemoryTranslation;
  actionId: string | null;
  onAction: (item: MemoryCommandGovernanceItem, action: 'approve' | 'reject') => void;
}) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-foreground">{translateMemoryType(item.title, t)}</div>
        <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{item.description}</div>
      </div>
      <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-700 dark:text-amber-300">
        {translateRecordStatus(item.status, t)}
      </span>
    </div>
    <div className="mt-3 flex flex-wrap gap-2">
      {(['approve', 'reject'] as const).map((action) =>
        item.available_actions.includes(action) ? (
          <button
            key={action}
            type="button"
            disabled={actionId === `${item.target_kind}:${item.id}:${action}`}
            onClick={() => onAction(item, action)}
            className="rounded-full border border-border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-60"
          >
            {t(`commandCenter.actions.${action}`)}
          </button>
        ) : null,
      )}
    </div>
  </div>
);

const InfluenceRow = ({ item, t }: { item: MemoryCommandInfluenceItem; t: MemoryTranslation }) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-sm font-medium text-foreground">
        {t('commandCenter.influenceRefs', { count: item.influence_refs.length })}
      </span>
      <span className="text-[11px] text-muted-foreground">{formatTime(item.occurred_at)}</span>
    </div>
    <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{item.answer_preview}</div>
    <div className="mt-2 flex flex-wrap gap-1.5">
      {item.influence_refs.slice(0, 4).map((ref) => (
        <span key={ref.memory_id} className="rounded-full border border-border bg-background px-2 py-0.5 text-[11px]">
          {translateMemoryType(ref.memory_type, t)}
          {typeof ref.score === 'number' ? ` · ${ref.score.toFixed(2)}` : ''}
        </span>
      ))}
    </div>
  </div>
);

const ConflictRow = ({ item, t }: { item: MemoryCommandConflictItem; t: MemoryTranslation }) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-sm font-medium text-foreground">{t(`commandCenter.conflictKind.${item.kind}`)}</span>
      <span className="text-[11px] text-muted-foreground">
        {item.created_at ? formatTime(item.created_at) : t('commandCenter.unknown')}
      </span>
    </div>
    <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{item.description}</div>
  </div>
);

const EventList = ({
  events,
  t,
  emptyLabel,
  live = false,
  onEventClick,
}: {
  events: MemoryCommandTimelineEvent[];
  t: MemoryTranslation;
  emptyLabel: string;
  live?: boolean;
  onEventClick?: (event: MemoryCommandTimelineEvent) => void;
}) => {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!live || events.length === 0) return;
    listRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }, [events, live]);

  return events.length ? (
    <div
      ref={listRef}
      className={cn('space-y-2', live && 'max-h-80 overflow-y-auto pr-1')}
      aria-live={live ? 'polite' : undefined}
    >
      {events.map((event) => {
        const replaySessionId = resolveReplaySessionId(event);
        const clickable = Boolean(onEventClick && replaySessionId);
        return (
          <button
            key={event.id}
            type="button"
            disabled={!clickable}
            onClick={() => onEventClick?.(event)}
            className={cn(
              'w-full rounded-lg border border-border/50 bg-accent/20 p-3 text-left transition-colors',
              clickable && 'cursor-pointer hover:border-primary/40 hover:bg-accent/35',
              !clickable && 'cursor-default',
            )}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-border/60 bg-background/70 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                {translateOperationKind(event.kind, t, event)}
              </span>
              <span className="text-sm font-medium text-foreground">{translateTimelineTitle(event, t)}</span>
            </div>
            <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
              {formatLiveStreamDescription(event, t)}
            </div>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <span className="text-[11px] text-muted-foreground">{formatTime(event.occurred_at)}</span>
              {clickable ? (
                <span className="text-[11px] font-medium text-primary/80">{t('commandCenter.openSessionReplay')}</span>
              ) : null}
            </div>
          </button>
        );
      })}
    </div>
  ) : (
    <EmptyState label={emptyLabel} />
  );
};

const RuntimePanel = ({ snapshot, t }: { snapshot: MemoryCommandCenterResponse; t: MemoryTranslation }) => (
  <div className="grid gap-2">
    <RuntimeRow label={t('commandCenter.deployMode')} value={snapshot.runtime.deploy_mode} />
    <RuntimeRow label={t('commandCenter.storageMode')} value={snapshot.runtime.storage_mode} />
    <RuntimeRow
      label={t('commandCenter.vectorStatus')}
      value={translateRuntimeStatus(snapshot.runtime.vector_status, t)}
    />
    <RuntimeRow
      label={t('commandCenter.embeddingStatus')}
      value={translateRuntimeStatus(snapshot.runtime.embedding_status, t)}
    />
    <RuntimeRow
      label={t('commandCenter.eventLedgerStatus')}
      value={translateRuntimeStatus(snapshot.runtime.event_ledger_status, t)}
    />
    <RuntimeRow
      label={t('commandCenter.healthSnapshotStatus')}
      value={translateRuntimeStatus(snapshot.runtime.health_snapshot_status, t)}
    />
    <RuntimeRow
      label={t('commandCenter.controlPlaneStatus')}
      value={translateRuntimeStatus(snapshot.runtime.control_plane_status, t)}
    />
  </div>
);

const CostPanel = ({ snapshot, t }: { snapshot: MemoryCommandCenterResponse; t: MemoryTranslation }) => (
  <div className="grid gap-2 sm:grid-cols-2">
    <MetricTile label={t('commandCenter.promptTokens')} value={snapshot.cost.prompt_tokens} dense />
    <MetricTile label={t('commandCenter.cachedTokens')} value={snapshot.cost.cached_tokens} dense />
    <MetricTile label={t('commandCenter.completionTokens')} value={snapshot.cost.completion_tokens} dense />
    <MetricTile
      label={t('commandCenter.cacheFriendly')}
      value={snapshot.cost.cache_friendly ? t('enabled') : t('disabled')}
      dense
    />
  </div>
);

const MigrationPanel = ({
  snapshot,
  t,
  actionId,
  onDoctorAction,
  onRollbackImport,
}: {
  snapshot: MemoryCommandCenterResponse;
  t: MemoryTranslation;
  actionId: string | null;
  onDoctorAction: (action: DoctorAction) => void;
  onRollbackImport: (importBatchId: string) => void;
}) => {
  const status = isCoverageStatus(snapshot.migration.coverage_status)
    ? snapshot.migration.coverage_status
    : 'not_tracked';
  const importBatchId = snapshot.migration.last_import_batch_id;
  const rollbackActionId = importBatchId ? `migration:rollback:${importBatchId}` : '';
  const rollbackPreviewActionId = importBatchId ? `migration:rollback-preview:${importBatchId}` : '';
  const rollbackBusy = actionId === rollbackActionId || actionId === rollbackPreviewActionId;
  return (
    <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
      <div className="text-sm font-medium text-foreground">{t(`commandCenter.coverageStatus.${status}`)}</div>
      <div className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
        <span>{t('commandCenter.trackedImports', { count: snapshot.migration.tracked_imports })}</span>
        <span>{t('commandCenter.unmappedItems', { count: snapshot.migration.unmapped_items })}</span>
        <span>{t('commandCenter.importCleanupPending', { count: snapshot.migration.cleanup_pending_sessions })}</span>
        <span>
          {t('commandCenter.importCleanupRetained', {
            count:
              snapshot.migration.cleanup_confirmed_sessions +
              snapshot.migration.cleanup_expired_sessions +
              snapshot.migration.cleanup_rolled_back_sessions,
            days: snapshot.migration.cleanup_retention_days,
          })}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {snapshot.migration.supported_sources.map((source) => (
          <span key={source} className="rounded-full border border-border bg-background px-2 py-0.5 text-[11px]">
            {source}
          </span>
        ))}
      </div>
      {(snapshot.migration.verification_recommended || importBatchId) && (
        <div className="mt-3 rounded-lg border border-border/60 bg-background/70 p-3">
          <div className="text-xs font-medium text-foreground">{t('commandCenter.importPostVerifyTitle')}</div>
          <div className="mt-1 text-xs leading-5 text-muted-foreground">{t('commandCenter.importPostVerifyDesc')}</div>
          {importBatchId && (
            <>
              <div className="mt-2 truncate text-[11px] text-muted-foreground">
                {t('commandCenter.lastImportBatch', { batch: importBatchId })}
              </div>
              {snapshot.migration.last_import_diagnostic_status && (
                <div className="mt-1 truncate text-[11px] text-muted-foreground">
                  {t('commandCenter.lastImportDiagnostic', {
                    status: snapshot.migration.last_import_diagnostic_status,
                  })}
                </div>
              )}
            </>
          )}
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={() => onDoctorAction('run_diagnostics')}
              disabled={actionId === 'diagnostics:run_diagnostics'}
              className="rounded-lg border border-border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-60"
            >
              {actionId === 'diagnostics:run_diagnostics'
                ? t('commandCenter.verifyingImport')
                : t('commandCenter.verifyImport')}
            </button>
            {importBatchId && (
              <button
                type="button"
                onClick={() => onRollbackImport(importBatchId)}
                disabled={rollbackBusy}
                className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs font-medium text-destructive transition-colors hover:bg-destructive/10 disabled:opacity-60"
              >
                {rollbackBusy ? t('commandCenter.rollingBackImport') : t('commandCenter.rollbackImport')}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

const ReplayRow = ({ item, t }: { item: MemoryCommandReplayOverlay; t: MemoryTranslation }) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="truncate text-sm font-medium text-foreground">{item.chat_id}</span>
      <span className="text-[11px] text-muted-foreground">{formatTime(item.last_event_at)}</span>
    </div>
    <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{item.last_summary}</div>
    <div className="mt-2 text-[11px] text-muted-foreground">
      {t('commandCenter.replayMeta', { events: item.event_count, influences: item.influence_count })}
    </div>
  </div>
);

const Panel = ({
  title,
  liveHint,
  className,
  children,
}: {
  title: string;
  liveHint?: string;
  className?: string;
  children: ReactNode;
}) => (
  <div className={cn('space-y-3', className)}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h4 className="text-sm font-semibold text-foreground">{title}</h4>
      {liveHint ? (
        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-primary/80">
          <span
            aria-hidden
            className="h-1.5 w-1.5 rounded-full bg-primary shadow-[0_0_8px_hsl(var(--primary)/0.55)] animate-pulse"
          />
          {liveHint}
        </span>
      ) : null}
    </div>
    {children}
  </div>
);

const MetricTile = ({ label, value, dense = false }: { label: string; value: number | string; dense?: boolean }) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="text-xs font-medium text-muted-foreground">{label}</div>
    <div className={cn('mt-1 font-semibold text-foreground', dense ? 'text-lg' : 'text-2xl')}>{value}</div>
  </div>
);

const RuntimeRow = ({ label, value }: { label: string; value: string }) => (
  <div className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-accent/20 px-3 py-2">
    <span className="text-xs text-muted-foreground">{label}</span>
    <span className="truncate text-right text-xs font-medium text-foreground">{value}</span>
  </div>
);

const EmptyState = ({ label }: { label: string }) => (
  <div className="rounded-lg border border-dashed border-border/70 p-4 text-sm text-muted-foreground">{label}</div>
);

const translateMemoryType = (value: string, t: MemoryTranslation): string =>
  isMemoryType(value) ? t(`types.${value}`) : value;
const translateSpaceKind = (value: string, t: MemoryTranslation): string =>
  isSpaceKind(value) ? t(`commandCenter.spaceKind.${value}`) : value;
const translateRecordStatus = (value: string, t: MemoryTranslation): string =>
  isRecordStatus(value) ? t(`commandCenter.recordStatus.${value}`) : value;
const translateRuntimeStatus = (value: string, t: MemoryTranslation): string =>
  isRuntimeStatus(value) ? t(`commandCenter.runtimeStatus.${value}`) : value;
const translateTimelineTitle = (event: MemoryCommandTimelineEvent, t: MemoryTranslation): string => {
  if (event.title === 'memory_health') return t('commandCenter.healthCheck');
  return translateMemoryType(event.title, t);
};

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

const OPERATION_KINDS = [
  ...WATERFALL_PHASES,
  'reject',
  'forget',
  'correct',
  'maintenance',
  'import_memory',
  'export_memory',
  'health_check',
  'shared_context_proposal',
] as const;

const translateOperationKind = (kind: string, t: MemoryTranslation, event?: MemoryCommandTimelineEvent): string => {
  if (kind === 'inject' && event?.metadata?.trigger === 'pre_compact') {
    return t('commandCenter.operationKind.pre_compact');
  }
  if (kind === 'write' && event?.metadata?.trigger === 'archive_checkpoint') {
    return t('commandCenter.operationKind.archive_checkpoint');
  }
  if ((OPERATION_KINDS as readonly string[]).includes(kind)) {
    return t(
      `commandCenter.operationKind.${kind}` as `commandCenter.operationKind.${(typeof OPERATION_KINDS)[number]}`,
    );
  }
  return kind.replaceAll('_', ' ');
};

const formatLiveStreamDescription = (event: MemoryCommandTimelineEvent, t: MemoryTranslation): string => {
  if (event.kind === 'inject' && event.metadata?.trigger === 'pre_compact') {
    return t('commandCenter.preCompactLiveDescription', {
      count: String((event.metadata.recalled_ids as string | undefined)?.split(',').filter(Boolean).length ?? 0),
    });
  }
  if (event.kind === 'write' && event.metadata?.trigger === 'archive_checkpoint') {
    return t('commandCenter.archiveCheckpointLiveDescription', {
      tool: String(event.metadata.tool_name ?? 'tool'),
      path: String(event.metadata.archive_path ?? ''),
    });
  }
  const stepCount = event.metadata?.live_stream_step_count;
  if (event.kind === 'recall' && typeof stepCount === 'number' && stepCount > 1) {
    return t('commandCenter.recallBurstSummary', { count: stepCount, summary: event.description });
  }
  return event.description;
};

const ConsolidationRollbackCard = ({
  summary,
  t,
  loading,
  onRollback,
}: {
  summary: ConsolidationLastSummary;
  t: MemoryTranslation;
  loading: boolean;
  onRollback?: () => void;
}) => {
  const timeLabel = summary.timestamp
    ? new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(
        new Date(summary.timestamp),
      )
    : '';

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium text-foreground">{t('commandCenter.consolidationLastRun')}</span>
          <span className="text-[11px] text-muted-foreground">{timeLabel}</span>
        </div>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          {summary.summary ?? t('commandCenter.consolidationNoDetails')}
        </p>
        <div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
          <span>{t('commandCenter.consolidationAffected', { count: summary.affected_count ?? 0 })}</span>
          {!summary.rollback_available && (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-amber-600 dark:text-amber-400">
              {t('commandCenter.consolidationConflict')}
            </span>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={onRollback}
        disabled={loading || !summary.rollback_available}
        className={cn(
          'w-full rounded-lg border px-3 py-2 text-xs font-medium transition-colors disabled:opacity-60',
          summary.rollback_available
            ? 'border-amber-500/30 bg-amber-500/10 text-amber-700 hover:bg-amber-500/20 dark:text-amber-400'
            : 'border-border bg-background text-muted-foreground',
        )}
      >
        {loading
          ? t('commandCenter.consolidationRollingBack')
          : summary.rollback_available
            ? t('commandCenter.consolidationRollbackBtn')
            : t('commandCenter.consolidationRollbackUnavailable')}
      </button>
    </div>
  );
};
