'use client';

/**
 * [INPUT]
 * @/services/memoryArchive::MemoryArchiveRestoreDryRunResult / execution DTOs (POS: Frontend Memory Archive and import API client)
 *
 * [OUTPUT]
 * MemoryArchiveRestoreDialog: GUI review surface for archive restore and immediate rollback.
 *
 * [POS]
 * 记忆归档恢复弹窗。展示分区预检、冲突、恢复结果和回滚结果；不直接读取文件或持有业务状态。
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type {
  MemoryArchiveRestoreDryRunResult,
  MemoryArchiveRestoreResult,
  MemoryArchiveRestoreRollbackPreview,
  MemoryArchiveRestoreRollbackResult,
  MemoryArchiveRestoreSectionPlan,
  MemoryArchiveSectionName,
} from '@/services/memoryArchive';

interface MemoryArchiveRestoreDialogProps {
  open: boolean;
  preview: MemoryArchiveRestoreDryRunResult | null;
  result: MemoryArchiveRestoreResult | null;
  rollbackPreview: MemoryArchiveRestoreRollbackPreview | null;
  rollbackResult: MemoryArchiveRestoreRollbackResult | null;
  selectedSections: MemoryArchiveSectionName[];
  reviewing: boolean;
  restoring: boolean;
  rollingBack: boolean;
  onOpenChange: (open: boolean) => void;
  onToggleSection: (section: MemoryArchiveSectionName) => void;
  onConfirm: () => void;
  onRollback: () => void;
}

const sectionKeys: MemoryArchiveSectionName[] = ['memory', 'shared_context', 'conversation', 'replay', 'audit'];

const planStatusClass: Record<MemoryArchiveRestoreDryRunResult['plan']['status'], string> = {
  ready: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  critical: 'border-destructive/30 bg-destructive/10 text-destructive',
};

export const MemoryArchiveRestoreDialog = memo<MemoryArchiveRestoreDialogProps>(
  ({
    open,
    preview,
    result,
    rollbackPreview,
    rollbackResult,
    selectedSections,
    reviewing,
    restoring,
    rollingBack,
    onOpenChange,
    onToggleSection,
    onConfirm,
    onRollback,
  }) => {
    const t = useTranslations('memory.archiveRestore');
    const sections = preview?.plan.sections ?? [];
    const sectionMap = new Map(sections.map((section) => [section.section, section]));
    const restoredRows = result ? Object.entries(result.restored).filter(([, count]) => count > 0) : [];
    const rollbackRows = rollbackResult
      ? Object.entries(rollbackResult.rolled_back).filter(([, count]) => count > 0)
      : [];
    const securityFindings = preview?.plan.security_findings ?? [];
    const hasBlockedFindings = Boolean(preview && preview.plan.blocked_items > 0);
    const sectionSelectionDisabled = reviewing || restoring || rollingBack || Boolean(result);

    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[88vh] max-w-4xl overflow-hidden p-0">
          <div className="flex max-h-[88vh] flex-col">
            <DialogHeader className="border-b border-border px-5 py-4">
              <DialogTitle>{t('title')}</DialogTitle>
              <DialogDescription>{t('description')}</DialogDescription>
            </DialogHeader>

            {preview && (
              <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
                <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
                  <SummaryTile label={t('total')} value={preview.plan.total_items.toLocaleString()} />
                  <SummaryTile label={t('restorable')} value={preview.plan.restorable_items.toLocaleString()} />
                  <SummaryTile label={t('skipped')} value={preview.plan.skipped_items.toLocaleString()} />
                  <SummaryTile label={t('conflicts')} value={preview.plan.conflict_items.toLocaleString()} />
                  <SummaryTile label={t('blocked')} value={preview.plan.blocked_items.toLocaleString()} />
                  <SummaryTile label={t('planHash')} value={preview.plan.plan_hash.slice(0, 12)} />
                </div>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <SummaryTile label={t('payloadHash')} value={preview.payload_hash.slice(0, 12)} />
                  <SummaryTile label={t('journalMode')} value={t('journalModeValue')} />
                </div>

                <div className={`rounded-lg border px-3 py-2 text-sm ${planStatusClass[preview.plan.status]}`}>
                  {t(`statuses.${preview.plan.status}`)}
                </div>

                <div className="rounded-lg border border-border bg-muted/20 px-3 py-3">
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-sm font-medium text-foreground">{t('selectedSections')}</p>
                    <p className="text-xs text-muted-foreground">
                      {reviewing ? t('refreshingPlan') : t('selectedSectionsDesc')}
                    </p>
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                    {sectionKeys.map((key) => {
                      const section = sectionMap.get(key);
                      return (
                        <SectionToggle
                          key={key}
                          section={key}
                          itemCount={section?.item_count ?? 0}
                          selected={selectedSections.includes(key)}
                          disabled={!section || sectionSelectionDisabled}
                          onToggle={onToggleSection}
                        />
                      );
                    })}
                  </div>
                </div>

                <div className="hidden overflow-hidden rounded-lg border border-border md:block">
                  <div className="grid grid-cols-[1fr_0.8fr_0.8fr_0.8fr_0.8fr_0.8fr] gap-2 border-b border-border bg-muted/60 px-3 py-2 text-xs font-medium text-muted-foreground">
                    <span>{t('section')}</span>
                    <span className="text-right">{t('items')}</span>
                    <span className="text-right">{t('restorable')}</span>
                    <span className="text-right">{t('skipped')}</span>
                    <span className="text-right">{t('conflicts')}</span>
                    <span className="text-right">{t('blocked')}</span>
                  </div>
                  <div className="divide-y divide-border">
                    {sectionKeys.map((key) => {
                      const section = sectionMap.get(key);
                      return section ? <SectionPlanRow key={key} section={section} /> : null;
                    })}
                  </div>
                </div>

                <div className="grid gap-2 md:hidden">
                  {sectionKeys.map((key) => {
                    const section = sectionMap.get(key);
                    return section ? <SectionPlanCard key={`${key}:mobile`} section={section} /> : null;
                  })}
                </div>

                {preview.plan.warning_codes.length > 0 && (
                  <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                    <p className="text-xs font-medium text-amber-700 dark:text-amber-300">{t('warnings')}</p>
                    <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                      {preview.plan.warning_codes.map((warning) => (
                        <li key={warning}>{formatWarning(t, warning)}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {securityFindings.length > 0 && (
                  <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2">
                    <p className="text-xs font-medium text-destructive">{t('securityFindings')}</p>
                    <div className="mt-2 grid gap-1.5 text-xs text-muted-foreground">
                      {securityFindings.slice(0, 8).map((finding, index) => (
                        <div
                          key={`${finding.section}:${finding.item_kind}:${finding.source_id}:${index}`}
                          className="flex flex-wrap items-center gap-1.5"
                        >
                          <span className="font-medium text-foreground">{t(`sections.${finding.section}`)}</span>
                          <span>{finding.item_kind}</span>
                          {finding.source_id && <span className="max-w-52 truncate">{finding.source_id}</span>}
                          <span className="rounded-full border border-border bg-background px-1.5 py-0.5">
                            {t(`securityVerdicts.${finding.verdict}`)}
                          </span>
                          {finding.codes.length > 0 && <span className="truncate">{finding.codes.join(', ')}</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {result && (
                  <div className="rounded-lg border border-border bg-muted/20 px-3 py-3">
                    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                      <SummaryTile label={t('restored')} value={result.total_restored.toLocaleString()} />
                      <SummaryTile label={t('skipped')} value={result.skipped_items.toLocaleString()} />
                      <SummaryTile label={t('conflicts')} value={result.conflict_items.toLocaleString()} />
                      <SummaryTile label={t('restoreBatch')} value={result.restore_batch_id.slice(-12)} />
                    </div>
                    {restoredRows.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {restoredRows.map(([section, count]) => (
                          <span
                            key={section}
                            className="rounded-full border border-border bg-background px-2 py-0.5 text-[11px]"
                          >
                            {section}: {count}
                          </span>
                        ))}
                      </div>
                    )}
                    {result.diagnostic_status && (
                      <div className="mt-3 rounded-lg border border-border bg-background px-3 py-2">
                        <p className="text-xs font-medium text-muted-foreground">{t('postRestoreDiagnostic')}</p>
                        <p className="mt-1 text-sm text-foreground">
                          {t('postRestoreDiagnosticDesc', {
                            status: formatDiagnosticStatus(t, result.diagnostic_status),
                            failed: result.diagnostic_failed_count ?? 0,
                          })}
                        </p>
                        {result.diagnostic_run_id && (
                          <p className="mt-1 truncate text-xs text-muted-foreground">
                            {t('diagnosticRun')}: {result.diagnostic_run_id}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {rollbackPreview && (
                  <div className="rounded-lg border border-border bg-muted/20 px-3 py-3">
                    <p className="text-sm font-medium text-foreground">{t('rollbackPreview')}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t('rollbackPreviewDesc', {
                        count: rollbackPreview.reversible_items,
                        missing: rollbackPreview.missing_items,
                      })}
                    </p>
                  </div>
                )}

                {rollbackResult && (
                  <div className="rounded-lg border border-border bg-muted/20 px-3 py-3">
                    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                      <SummaryTile label={t('rolledBack')} value={rollbackResult.total_rolled_back.toLocaleString()} />
                      <SummaryTile label={t('missing')} value={rollbackResult.missing_items.toLocaleString()} />
                      <SummaryTile label={t('failed')} value={rollbackResult.failed_items.toLocaleString()} />
                      <SummaryTile
                        label={t('integrity')}
                        value={t(`integrityStatus.${rollbackResult.integrity_status}`)}
                      />
                    </div>
                    {rollbackRows.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {rollbackRows.map(([section, count]) => (
                          <span
                            key={section}
                            className="rounded-full border border-border bg-background px-2 py-0.5 text-[11px]"
                          >
                            {section}: {count}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            <DialogFooter className="border-t border-border px-5 py-4">
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={restoring || rollingBack}>
                {t('close')}
              </Button>
              {result && !rollbackResult ? (
                <Button
                  variant="destructive"
                  onClick={onRollback}
                  disabled={rollingBack || Boolean(rollbackPreview && rollbackPreview.reversible_items === 0)}
                  className="min-w-32"
                >
                  {rollingBack ? t('rollingBack') : t('rollback')}
                </Button>
              ) : (
                <Button
                  onClick={onConfirm}
                  disabled={
                    !preview ||
                    selectedSections.length === 0 ||
                    preview.plan.restorable_items === 0 ||
                    hasBlockedFindings ||
                    restoring ||
                    reviewing ||
                    Boolean(result)
                  }
                >
                  {restoring ? t('restoring') : t('confirm')}
                </Button>
              )}
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    );
  },
);

MemoryArchiveRestoreDialog.displayName = 'MemoryArchiveRestoreDialog';

function SectionPlanRow({ section }: { section: MemoryArchiveRestoreSectionPlan }) {
  const t = useTranslations('memory.archiveRestore');
  return (
    <div className="grid grid-cols-[1fr_0.8fr_0.8fr_0.8fr_0.8fr_0.8fr] gap-2 px-3 py-2 text-sm">
      <span className="truncate text-foreground">{t(`sections.${section.section}`)}</span>
      <span className="text-right tabular-nums text-muted-foreground">{section.item_count.toLocaleString()}</span>
      <span className="text-right tabular-nums text-muted-foreground">{section.restorable_items.toLocaleString()}</span>
      <span className="text-right tabular-nums text-muted-foreground">{section.skipped_items.toLocaleString()}</span>
      <span className="text-right tabular-nums text-muted-foreground">{section.conflict_items.toLocaleString()}</span>
      <span className="text-right tabular-nums text-muted-foreground">{section.blocked_items.toLocaleString()}</span>
    </div>
  );
}

function SectionPlanCard({ section }: { section: MemoryArchiveRestoreSectionPlan }) {
  const t = useTranslations('memory.archiveRestore');
  return (
    <div className="rounded-lg border border-border bg-muted/20 px-3 py-2">
      <p className="text-sm font-medium text-foreground">{t(`sections.${section.section}`)}</p>
      <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <span>
          {t('items')}: {section.item_count.toLocaleString()}
        </span>
        <span>
          {t('restorable')}: {section.restorable_items.toLocaleString()}
        </span>
        <span>
          {t('skipped')}: {section.skipped_items.toLocaleString()}
        </span>
        <span>
          {t('conflicts')}: {section.conflict_items.toLocaleString()}
        </span>
        <span>
          {t('blocked')}: {section.blocked_items.toLocaleString()}
        </span>
      </div>
    </div>
  );
}

function SectionToggle({
  section,
  itemCount,
  selected,
  disabled,
  onToggle,
}: {
  section: MemoryArchiveSectionName;
  itemCount: number;
  selected: boolean;
  disabled: boolean;
  onToggle: (section: MemoryArchiveSectionName) => void;
}) {
  const t = useTranslations('memory.archiveRestore');
  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      onClick={() => onToggle(section)}
      className={[
        'min-h-16 rounded-lg border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-55',
        selected
          ? 'border-primary/40 bg-primary/10 text-foreground'
          : 'border-border bg-background text-muted-foreground hover:bg-accent',
      ].join(' ')}
    >
      <span className="block text-sm font-medium">{t(`sections.${section}`)}</span>
      <span className="mt-1 block text-xs tabular-nums">{t('sectionItemCount', { count: itemCount })}</span>
    </button>
  );
}

function SummaryTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 px-3 py-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 truncate text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

function formatDiagnosticStatus(
  t: ReturnType<typeof useTranslations<'memory.archiveRestore'>>,
  status: string,
): string {
  const known = ['ready', 'warning', 'critical', 'missing', 'failed'];
  return known.includes(status) ? t(`diagnosticStatuses.${status}`) : status;
}

function formatWarning(t: ReturnType<typeof useTranslations<'memory.archiveRestore'>>, warning: string): string {
  const known = [
    'section_not_selected',
    'memory_section_invalid',
    'no_native_buckets',
    'shared_context_conflicts',
    'conversation_conflicts',
    'replay_conflicts',
    'replay_missing_chats',
    'audit_conflicts',
    'no_reversible_items',
    'restore_targets_missing',
    'security_preflight_blocked',
    'security_findings_truncated',
  ];
  return known.includes(warning) ? t(`warningMessages.${warning}`) : warning;
}
