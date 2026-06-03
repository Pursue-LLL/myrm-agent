'use client';

/**
 * [INPUT]
 * @/services/memoryArchive::MemoryImportDryRunResult (POS: Frontend Memory Archive and import API client)
 *
 * [OUTPUT]
 * MemoryImportReviewDialog: server-bound import dry-run review and confirm surface.
 *
 * [POS]
 * 记忆导入审查弹窗。只展示服务端 dry-run 结果并触发确认，不直接写入记忆。
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import type { MemoryImportDryRunResult } from '@/services/memoryArchive';

interface MemoryImportReviewDialogProps {
  open: boolean;
  dryRun: MemoryImportDryRunResult | null;
  payloadHash: string | null;
  expiresAt: string | null;
  importing: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

const statusClass: Record<MemoryImportDryRunResult['summary']['status'], string> = {
  ready: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  critical: 'border-destructive/30 bg-destructive/10 text-destructive',
  missing: 'border-muted-foreground/20 bg-muted text-muted-foreground',
};

const WARNING_KEYS = [
  'no_native_buckets',
  'myrm_archive_memory_section_missing',
  'myrm_archive_non_memory_sections_review_only',
  'agentmemory_version_unsupported',
  'agentmemory_too_many_sessions',
  'agentmemory_too_many_memories',
  'agentmemory_too_many_summaries',
  'agentmemory_too_many_observations',
  'agentmemory_graph_skipped',
  'agentmemory_access_logs_skipped',
  'claude_code_too_many_lines',
  'claude_code_too_many_entries',
  'claude_code_no_conversation_entries',
  'claude_code_no_lines',
  'hermes_no_files',
  'hermes_api_keys_detected',
  'hermes_skills_detected',
  'openclaw_no_sessions',
  'openclaw_no_memories',
  'openclaw_skills_detected',
  'cursor_no_rules',
  'cursor_empty_payload',
  'codex_no_instructions',
  'codex_empty_payload',
  'unsupported_source',
] as const;

type WarningKey = (typeof WARNING_KEYS)[number];

const isWarningKey = (value: string): value is WarningKey => WARNING_KEYS.includes(value as WarningKey);

export const MemoryImportReviewDialog = memo<MemoryImportReviewDialogProps>(
  ({ open, dryRun, payloadHash, expiresAt, importing, onOpenChange, onConfirm }) => {
    const t = useTranslations('memory.importReview');
    const expiresLabel = expiresAt ? new Date(expiresAt).toLocaleString() : t('notAvailable');

    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[88vh] max-w-3xl overflow-hidden p-0">
          <div className="flex max-h-[88vh] flex-col">
            <DialogHeader className="border-b border-border px-5 py-4">
              <DialogTitle>{t('title')}</DialogTitle>
              <DialogDescription>{t('description')}</DialogDescription>
            </DialogHeader>

            {dryRun && (
              <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <SummaryTile label={t('source')} value={t(`sources.${dryRun.summary.source}`)} />
                  <SummaryTile label={t('total')} value={dryRun.summary.total_items.toLocaleString()} />
                  <SummaryTile label={t('mapped')} value={dryRun.summary.mapped_items.toLocaleString()} />
                  <SummaryTile label={t('unmapped')} value={dryRun.summary.unmapped_items.toLocaleString()} />
                  <SummaryTile label={t('expiresAt')} value={expiresLabel} />
                  <SummaryTile
                    label={t('reviewHash')}
                    value={payloadHash ? payloadHash.slice(0, 12) : t('notAvailable')}
                  />
                </div>

                <div className={`rounded-lg border px-3 py-2 text-sm ${statusClass[dryRun.summary.status]}`}>
                  {t(`statuses.${dryRun.summary.status}`)}
                </div>

                <div className="hidden overflow-hidden rounded-lg border border-border md:block">
                  <div className="grid grid-cols-[1.3fr_1fr_0.9fr_0.9fr] gap-2 border-b border-border bg-muted/60 px-3 py-2 text-xs font-medium text-muted-foreground">
                    <span>{t('sourceBucket')}</span>
                    <span>{t('targetBucket')}</span>
                    <span className="text-right">{t('items')}</span>
                    <span className="text-right">{t('status')}</span>
                  </div>
                  <div className="divide-y divide-border">
                    {dryRun.mappings.map((mapping) => (
                      <div
                        key={`${mapping.source_bucket}:${mapping.target_bucket ?? 'none'}`}
                        className="grid grid-cols-[1.3fr_1fr_0.9fr_0.9fr] gap-2 px-3 py-2 text-sm"
                      >
                        <span className="truncate text-foreground">{mapping.source_bucket}</span>
                        <span className="truncate text-muted-foreground">
                          {mapping.target_bucket ?? t('notMapped')}
                        </span>
                        <span className="text-right tabular-nums text-muted-foreground">
                          {mapping.imported_count.toLocaleString()}/{mapping.item_count.toLocaleString()}
                        </span>
                        <span className="text-right text-muted-foreground">
                          {t(`mappingStatuses.${mapping.status}`)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="space-y-2 md:hidden">
                  {dryRun.mappings.map((mapping) => (
                    <div
                      key={`${mapping.source_bucket}:${mapping.target_bucket ?? 'none'}:mobile`}
                      className="rounded-lg border border-border bg-muted/20 px-3 py-2"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-foreground">{mapping.source_bucket}</p>
                          <p className="mt-1 truncate text-xs text-muted-foreground">
                            {mapping.target_bucket ?? t('notMapped')}
                          </p>
                        </div>
                        <span className="shrink-0 text-xs text-muted-foreground">
                          {t(`mappingStatuses.${mapping.status}`)}
                        </span>
                      </div>
                      <p className="mt-2 text-xs tabular-nums text-muted-foreground">
                        {mapping.imported_count.toLocaleString()}/{mapping.item_count.toLocaleString()}
                      </p>
                    </div>
                  ))}
                </div>

                {dryRun.warnings.length > 0 && (
                  <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                    <p className="text-xs font-medium text-amber-700 dark:text-amber-300">{t('warnings')}</p>
                    <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                      {dryRun.warnings.map((warning) => (
                        <li key={warning}>{isWarningKey(warning) ? t(`warningMessages.${warning}`) : warning}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            <DialogFooter className="border-t border-border px-5 py-4">
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={importing}>
                {t('cancel')}
              </Button>
              <Button
                onClick={onConfirm}
                disabled={!dryRun || dryRun.summary.mapped_items === 0 || importing}
                className="min-w-28"
              >
                {importing ? t('importing') : t('confirm')}
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    );
  },
);

MemoryImportReviewDialog.displayName = 'MemoryImportReviewDialog';

function SummaryTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 px-3 py-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 truncate text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}
