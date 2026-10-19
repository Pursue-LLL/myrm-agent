'use client';

/**
 * [INPUT]
 * @/services/memory/archive::MemoryImportDryRunResult (POS: Frontend Memory Archive and import API client)
 * @/lib/memory/importWarnings::resolveImportWarning (POS: 记忆导入告警文案解析)
 *
 * [OUTPUT]
 * MemoryImportReviewDialog: server-bound import dry-run review and confirm surface.
 *
 * [POS]
 * 记忆导入审查弹窗。展示服务端 dry-run 的映射表、有界解析样例与告警文案并触发确认，不直接写入记忆。
 */

import { memo } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { MEMORY_IMPORT_SOURCE_IDS, type MemoryImportDryRunResult } from '@/services/memory/archive';
import { resolveImportWarning } from '@/lib/memory/importWarnings';

interface MemoryImportReviewDialogProps {
  open: boolean;
  dryRun: MemoryImportDryRunResult | null;
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

const SOURCE_KEYS: readonly string[] = [...MEMORY_IMPORT_SOURCE_IDS, 'unknown'];

const isSourceKey = (value: string): boolean => SOURCE_KEYS.includes(value);

const TYPED_BUCKETS = [
  'profile',
  'semantic',
  'episodic',
  'procedural',
  'conversation',
  'claim',
  'task_digest',
] as const;

type TypedBucket = (typeof TYPED_BUCKETS)[number];

const isTypedBucket = (value: string): value is TypedBucket => TYPED_BUCKETS.includes(value as TypedBucket);

interface PreviewEntry {
  content: string;
  createdAt: string;
}

interface PreviewBucket {
  bucket: string;
  entries: PreviewEntry[];
}

const previewEntry = (raw: Record<string, unknown>): PreviewEntry | null => {
  const content = typeof raw.content === 'string' ? raw.content.trim() : '';
  return content ? { content, createdAt: typeof raw.created_at === 'string' ? raw.created_at : '' } : null;
};

// Timestamps are stored as UTC instants (or date-only values at UTC midnight); format in
// UTC so a date-only entry never shifts to the previous day in negative-offset locales.
const formatTimestamp = (value: string, locale: string): string => {
  if (!value) {
    return '';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return '';
  }
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' }).format(parsed);
};

const collectPreviewBuckets = (data: MemoryImportDryRunResult['normalized_data']): PreviewBucket[] =>
  Object.entries(data ?? {}).flatMap(([bucket, entries]) => {
    const parsed = (Array.isArray(entries) ? entries : []).flatMap((entry) =>
      entry && typeof entry === 'object' ? (previewEntry(entry) ?? []) : [],
    );
    return parsed.length ? [{ bucket, entries: parsed }] : [];
  });

export const MemoryImportReviewDialog = memo<MemoryImportReviewDialogProps>(
  ({ open, dryRun, expiresAt, importing, onOpenChange, onConfirm }) => {
    const t = useTranslations('memory.importReview');
    const locale = useLocale();
    const tType = useTranslations('memory.types');
    const tWarning = useTranslations('memory.importWarnings');
    const expiresLabel = expiresAt ? new Date(expiresAt).toLocaleString() : t('notAvailable');
    const previewBuckets = dryRun ? collectPreviewBuckets(dryRun.normalized_data) : [];
    const previewCount = previewBuckets.reduce((total, group) => total + group.entries.length, 0);
    const sourceKey = dryRun && isSourceKey(dryRun.summary.source) ? dryRun.summary.source : 'unknown';

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
                  <SummaryTile label={t('source')} value={t(`sources.${sourceKey}`)} />
                  <SummaryTile label={t('total')} value={dryRun.summary.total_items.toLocaleString()} />
                  <SummaryTile label={t('mapped')} value={dryRun.summary.mapped_items.toLocaleString()} />
                  <SummaryTile label={t('unmapped')} value={dryRun.summary.unmapped_items.toLocaleString()} />
                  <SummaryTile label={t('expiresAt')} value={expiresLabel} />
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

                {previewBuckets.length > 0 && (
                  <div className="overflow-hidden rounded-lg border border-border">
                    <div className="border-b border-border bg-muted/40 px-3 py-2">
                      <p className="text-xs font-medium text-foreground">
                        {t('previewTitle', { count: previewCount })}
                      </p>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        {dryRun.summary.mapped_items > previewCount
                          ? t('previewTruncated', { shown: previewCount, total: dryRun.summary.mapped_items })
                          : t('previewHint')}
                      </p>
                    </div>
                    <div className="max-h-64 space-y-3 overflow-y-auto px-3 py-3">
                      {previewBuckets.map(({ bucket, entries }) => (
                        <div key={bucket} className="space-y-1.5">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-medium text-foreground">
                              {isTypedBucket(bucket) ? tType(bucket) : bucket}
                            </span>
                            <span className="text-[11px] tabular-nums text-muted-foreground">{entries.length}</span>
                          </div>
                          <ul className="space-y-1.5">
                            {entries.map((entry, index) => (
                              <li
                                key={`${bucket}:${index}`}
                                className="rounded-md border border-border/60 bg-muted/20 px-2.5 py-1.5"
                              >
                                <p className="whitespace-pre-wrap break-words text-xs leading-5 text-foreground/90">
                                  {entry.content}
                                </p>
                                {formatTimestamp(entry.createdAt, locale) && (
                                  <p className="mt-1 text-[11px] text-muted-foreground">
                                    {formatTimestamp(entry.createdAt, locale)}
                                  </p>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {dryRun.warnings.length > 0 && (
                  <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                    <p className="text-xs font-medium text-amber-700 dark:text-amber-300">{t('warnings')}</p>
                    <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                      {dryRun.warnings.map((warning) => (
                        <li key={warning}>{resolveImportWarning(warning, tWarning)}</li>
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
