'use client';

/**
 * [INPUT]
 * @/services/memoryArchive::*Rollback* (POS: Frontend Memory Archive and import API client)
 * translated memory namespace.
 *
 * [OUTPUT]
 * Shared chrome components for MemoryCommandCenter.
 *
 * [POS]
 * 个人大脑指挥中心轻量展示组件，避免容器文件承载弹窗和展示细节。
 */

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import type {
  MemoryImportRollbackPreviewResponse,
  MemoryImportRollbackResponse,
  MemoryImportRollbackWarning,
} from '@/services/memoryArchive';

const ROLLBACK_INTEGRITY_STATUSES = ['ready', 'warning', 'critical', 'not_checked'] as const;

type RollbackIntegrityStatus = (typeof ROLLBACK_INTEGRITY_STATUSES)[number];
type MemoryTranslation = ReturnType<typeof useTranslations<'memory'>>;

const isRollbackIntegrityStatus = (value: string): value is RollbackIntegrityStatus =>
  ROLLBACK_INTEGRITY_STATUSES.includes(value as RollbackIntegrityStatus);

const formatRollbackIntegrityStatus = (t: MemoryTranslation, value: string): string =>
  isRollbackIntegrityStatus(value) ? t(`commandCenter.rollbackIntegrityStatus.${value}`) : value;

const formatRollbackWarning = (t: MemoryTranslation, warning: MemoryImportRollbackWarning): string => {
  switch (warning.code) {
    case 'no_reversible_items':
      return t('commandCenter.rollbackWarnings.no_reversible_items');
    case 'profile_conflicts':
      return t('commandCenter.rollbackWarnings.profile_conflicts', { count: Number(warning.params.count ?? 0) });
    case 'profile_guarded':
      return t('commandCenter.rollbackWarnings.profile_guarded', { count: Number(warning.params.count ?? 0) });
    case 'memory_rows_missing':
      return t('commandCenter.rollbackWarnings.memory_rows_missing', { count: Number(warning.params.count ?? 0) });
    default:
      return t('commandCenter.rollbackWarnings.unknown');
  }
};

export const RollbackPreviewDialog = ({
  open,
  preview,
  result,
  loading,
  t,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  preview: MemoryImportRollbackPreviewResponse | null;
  result: MemoryImportRollbackResponse | null;
  loading: boolean;
  t: MemoryTranslation;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) => {
  const itemRows = preview ? Object.entries(preview.items_by_type).filter(([, count]) => count > 0) : [];
  const resultRows = result
    ? [
        [t('commandCenter.rollbackResultDeleted'), result.deleted_refs.length],
        [t('commandCenter.rollbackResultMissing'), result.missing_refs.length],
        [t('commandCenter.rollbackResultForbidden'), result.forbidden_refs.length],
        [t('commandCenter.rollbackResultFailed'), result.failed_refs.length],
      ]
    : [];
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="max-w-xl">
        <AlertDialogHeader>
          <AlertDialogTitle>{t('commandCenter.rollbackPreviewTitle')}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>{t('commandCenter.rollbackPreviewDesc')}</p>
              {preview && (
                <div className="rounded-lg border border-border/60 bg-accent/20 p-3">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <FactLine label={t('commandCenter.rollbackPreviewBatch')} value={preview.import_batch_id} />
                    <FactLine label={t('commandCenter.rollbackPreviewSource')} value={preview.source} />
                    <FactLine label={t('commandCenter.rollbackPreviewTotal')} value={String(preview.total_items)} />
                    <FactLine
                      label={t('commandCenter.rollbackPreviewReversible')}
                      value={String(preview.reversible_items)}
                    />
                    <FactLine label={t('commandCenter.rollbackPreviewSkipped')} value={String(preview.skipped_items)} />
                    <FactLine
                      label={t('commandCenter.rollbackPreviewConflicts')}
                      value={String(preview.conflict_items)}
                    />
                    <FactLine label={t('commandCenter.rollbackPreviewMissing')} value={String(preview.missing_items)} />
                  </div>
                  {itemRows.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {itemRows.map(([type, count]) => (
                        <span
                          key={type}
                          className="rounded-full border border-border bg-background px-2 py-0.5 text-[11px]"
                        >
                          {type}: {count}
                        </span>
                      ))}
                    </div>
                  )}
                  {preview.warnings.length > 0 && (
                    <div className="mt-3 space-y-1 text-xs text-amber-700 dark:text-amber-300">
                      {preview.warnings.map((warning) => (
                        <div key={warning.code}>{formatRollbackWarning(t, warning)}</div>
                      ))}
                    </div>
                  )}
                  {result && (
                    <div className="mt-3 rounded-md border border-border/70 bg-background/70 p-2">
                      <div className="grid gap-2 sm:grid-cols-2">
                        <FactLine
                          label={t('commandCenter.rollbackResultIntegrity')}
                          value={formatRollbackIntegrityStatus(t, result.integrity_status)}
                        />
                        <FactLine
                          label={t('commandCenter.rollbackResultTotal')}
                          value={String(result.total_rolled_back)}
                        />
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {resultRows.map(([label, count]) => (
                          <span
                            key={label}
                            className="rounded-full border border-border bg-muted px-2 py-0.5 text-[11px] text-foreground"
                          >
                            {label}: {count}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('commandCenter.rollbackPreviewCancel')}</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={!preview || preview.reversible_items === 0 || loading || Boolean(result)}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {loading ? t('commandCenter.rollingBackImport') : t('commandCenter.rollbackPreviewConfirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};

export const CommandCenterSkeleton = ({ className }: { className?: string }) => (
  <section className={cn('space-y-4 rounded-xl border border-border/60 bg-background/60 p-4', className)}>
    <div className="h-5 w-52 animate-pulse rounded bg-accent" />
    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="h-20 animate-pulse rounded-lg bg-accent/60" />
      ))}
    </div>
  </section>
);

export const MetricTile = ({
  label,
  value,
  dense = false,
}: {
  label: string;
  value: number | string;
  dense?: boolean;
}) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="text-xs font-medium text-muted-foreground">{label}</div>
    <div className={cn('mt-1 font-semibold text-foreground', dense ? 'text-lg' : 'text-2xl')}>{value}</div>
  </div>
);

export const StatusPill = ({ label, status }: { label: string; status: string }) => (
  <span className={cn('rounded-full border px-2 py-0.5 text-[11px] font-medium', healthClassName(status))}>
    {label}
  </span>
);

const FactLine = ({ label, value }: { label: string; value: string }) => (
  <div className="min-w-0">
    <div className="text-[11px] font-medium text-muted-foreground">{label}</div>
    <div className="mt-0.5 truncate text-xs text-foreground">{value}</div>
  </div>
);

const healthClassName = (status: string): string => {
  if (status === 'healthy') return 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20 dark:text-emerald-300';
  if (status === 'degraded') return 'bg-amber-500/10 text-amber-700 border-amber-500/20 dark:text-amber-300';
  if (status === 'critical') return 'bg-destructive/10 text-destructive border-destructive/20';
  return 'bg-muted text-muted-foreground border-border';
};
