'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::MemoryCommandCenterResponse (POS: Frontend Personal Brain Command Center client)
 * ./MemoryCommandCenterDoctorPanel::DoctorExecutableAction (POS: 个人大脑指挥中心 Memory Doctor 面板)
 * ./memoryCommandCenterFormat::translateRecordStatus (POS: 个人大脑指挥中心面板共用的枚举守卫与文案格式化)
 *
 * [OUTPUT]
 * GovernanceRow: 待审批记忆行与批准 / 拒绝动作。
 * MigrationPanel: 迁移覆盖、适配器就绪度与 missing 状态的迁移向导入口。
 * ConsolidationRollbackCard: 最近一次整合摘要与一键回滚。
 *
 * [POS]
 * 个人大脑指挥中心的治理动作行、迁移覆盖与适配器状态面板，以及整合回滚卡片。
 */

import { cn } from '@/lib/utils/classnameUtils';
import type {
  ConsolidationLastSummary,
  MemoryCommandCenterResponse,
  MemoryCommandGovernanceItem,
} from '@/services/memory/commandCenter';
import type { DoctorExecutableAction } from './MemoryCommandCenterDoctorPanel';
import {
  isCoverageStatus,
  isMigrationAdapterStatus,
  translateMemoryType,
  translateRecordStatus,
  type MemoryTranslation,
  type MigrationAdapterStatus,
} from './memoryCommandCenterFormat';

export const GovernanceRow = ({
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

export const MigrationPanel = ({
  snapshot,
  t,
  actionId,
  onDoctorAction,
  onRollbackImport,
  onOpenMigrationWizard,
}: {
  snapshot: MemoryCommandCenterResponse;
  t: MemoryTranslation;
  actionId: string | null;
  onDoctorAction: (action: DoctorExecutableAction) => void;
  onRollbackImport: (importBatchId: string) => void;
  onOpenMigrationWizard: (source: string) => void;
}) => {
  const status = isCoverageStatus(snapshot.migration.coverage_status)
    ? snapshot.migration.coverage_status
    : 'not_tracked';
  const importBatchId = snapshot.migration.last_import_batch_id;
  const rollbackActionId = importBatchId ? `migration:rollback:${importBatchId}` : '';
  const rollbackPreviewActionId = importBatchId ? `migration:rollback-preview:${importBatchId}` : '';
  const rollbackBusy = actionId === rollbackActionId || actionId === rollbackPreviewActionId;
  const adapterStatus = snapshot.migration.adapter_status;
  const sourceOrder = Array.from(new Set([...snapshot.migration.supported_sources, ...Object.keys(adapterStatus)]));
  const adapterEntries = sourceOrder.map((source) => {
    const rawStatus = adapterStatus[source];
    return {
      source,
      status: isMigrationAdapterStatus(rawStatus) ? rawStatus : 'missing',
    };
  });
  const adapterStatusBadgeClass = (statusValue: MigrationAdapterStatus): string => {
    if (statusValue === 'ready') {
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300';
    }
    if (statusValue === 'planned') {
      return 'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300';
    }
    return 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300';
  };
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
      {adapterEntries.length > 0 && (
        <div className="mt-3 space-y-2">
          <div className="text-xs font-medium text-foreground">{t('commandCenter.migrationAdapterStatusTitle')}</div>
          <div className="grid gap-2 sm:grid-cols-2">
            {adapterEntries.map(({ source, status: entryStatus }) => (
              <div
                key={`${source}:${entryStatus}`}
                className="space-y-2 rounded-lg border border-border/60 bg-background/80 px-2.5 py-2"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate text-xs text-foreground">{source}</span>
                  <span
                    className={cn(
                      'rounded-full border px-2 py-0.5 text-[11px] font-medium',
                      adapterStatusBadgeClass(entryStatus),
                    )}
                  >
                    {t(`commandCenter.migrationAdapterStatus.${entryStatus}`)}
                  </span>
                </div>
                {entryStatus === 'missing' && (
                  <div className="space-y-1.5">
                    <p className="text-[11px] leading-5 text-muted-foreground">
                      {t('commandCenter.migrationAdapterMissingHint', { source })}
                    </p>
                    <button
                      type="button"
                      onClick={() => onOpenMigrationWizard(source)}
                      className="rounded-md border border-border bg-background px-2.5 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-accent"
                    >
                      {t('commandCenter.migrationAdapterOpenWizard')}
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
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
              {snapshot.migration.last_import_readiness_status && (
                <div className="mt-1 truncate text-[11px] text-muted-foreground">
                  {t('commandCenter.lastImportReadiness', {
                    status: t(`commandCenter.readinessStatus.${snapshot.migration.last_import_readiness_status}`),
                  })}
                </div>
              )}
              {snapshot.migration.last_import_first_turn_outcome && (
                <div className="mt-1 truncate text-[11px] text-muted-foreground">
                  {t('commandCenter.lastImportFirstTurn', {
                    outcome: t(`commandCenter.firstTurnOutcome.${snapshot.migration.last_import_first_turn_outcome}`),
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

export const ConsolidationRollbackCard = ({
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
