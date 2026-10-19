'use client';

import { useTranslations } from 'next-intl';

import { Badge } from '@/components/primitives/badge';
import { resolveImportWarning } from '@/lib/memory/importWarnings';
import type {
  CronMigrationSkippedPreviewItem,
  MCPServerPreviewItem,
  MemoryImportMappingItem,
} from '@/services/memory/archive';

import { CollapsibleSection } from './CollapsibleSection';
import { formatCronSkippedReason, type TranslationFn } from './wizardShared';

/**
 * Reference-only blocks of the review step. They are folded by default so the
 * counts, coverage matrix and confirm button stay above the fold, while every
 * detail remains one click away before the user commits the import.
 */

/**
 * Import warnings stay visible: the copy lives in the shared `memory.importWarnings`
 * namespace that the review dialog also renders, so this panel binds it directly
 * instead of receiving it from the wizard step.
 */
export function ImportWarningsPanel({ warnings, t }: { warnings: string[]; t: TranslationFn }) {
  const tWarning = useTranslations('memory.importWarnings');

  if (warnings.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">{t('preview.warnings')}</h3>
      <ul className="list-disc space-y-1 pl-5">
        {warnings.map((warning, index) => (
          <li key={`${warning}-${index}`} className="text-xs text-amber-600 dark:text-amber-400">
            {resolveImportWarning(warning, tWarning)}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function PreviewItemsPanel({
  buckets,
  t,
}: {
  buckets: [string, Record<string, unknown>[]][];
  t: TranslationFn;
}) {
  if (buckets.length === 0) {
    return null;
  }

  const total = buckets.reduce((sum, [, entries]) => sum + entries.length, 0);

  return (
    <CollapsibleSection title={t('preview.previewItemsTitle', { count: total })}>
      <div className="max-h-72 space-y-2 overflow-y-auto rounded-xl border border-border/50 bg-background/60 p-3">
        {buckets.map(([bucket, entries]) => (
          <div key={bucket} className="space-y-1.5">
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              {t(`preview.previewBucket.${bucket}`, { defaultValue: bucket })}
            </div>
            <ul className="space-y-1">
              {entries.map((entry, index) => (
                <li key={`${bucket}-${index}`} className="flex items-start gap-2 text-xs text-foreground/90">
                  <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-muted-foreground/50" />
                  <span className="min-w-0 break-words">{String(entry.content ?? '')}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </CollapsibleSection>
  );
}

export function CronSkippedPanel({ items, t }: { items: CronMigrationSkippedPreviewItem[]; t: TranslationFn }) {
  if (items.length === 0) {
    return null;
  }

  return (
    <CollapsibleSection
      title={t('preview.cronSkippedTitle', { count: items.length })}
      defaultOpen
      className="border-amber-500/30 bg-amber-500/5"
    >
      <ul className="space-y-1 text-xs text-muted-foreground">
        {items.map((item) => (
          <li key={`${item.name}-${item.reason}`}>
            <span className="font-medium text-foreground">{item.name}</span>
            {' — '}
            {formatCronSkippedReason(t, item.reason)}
          </li>
        ))}
      </ul>
    </CollapsibleSection>
  );
}

export function InstructionPreviewPanel({
  persona,
  ruleNames,
  t,
}: {
  persona?: string | null;
  ruleNames: string[];
  t: TranslationFn;
}) {
  return (
    <CollapsibleSection title={t('preview.instructionPreviewTitle')} badge={ruleNames.length || undefined}>
      {persona ? (
        <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-background/80 p-3 text-[11px] text-muted-foreground">
          {persona}
        </pre>
      ) : null}
      {ruleNames.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
          {ruleNames.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
      )}
    </CollapsibleSection>
  );
}

export function MappingsPanel({ mappings, t }: { mappings: MemoryImportMappingItem[]; t: TranslationFn }) {
  if (mappings.length === 0) {
    return null;
  }

  return (
    <CollapsibleSection title={t('preview.mappings')} badge={mappings.length}>
      <div className="overflow-hidden rounded-xl border border-border/50">
        <table className="w-full text-sm">
          <thead className="bg-secondary/40">
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">
                {t('preview.tableSource')}
              </th>
              <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">
                {t('preview.tableTarget')}
              </th>
              <th className="px-4 py-2 text-right text-xs font-medium text-muted-foreground">
                {t('preview.tableItems')}
              </th>
              <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">
                {t('preview.tableStatus')}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/30">
            {mappings.map((mapping, index) => (
              <tr key={`${mapping.source_bucket}-${index}`} className="transition-colors hover:bg-secondary/20">
                <td className="px-4 py-2 font-mono text-xs">{mapping.source_bucket}</td>
                <td className="px-4 py-2 font-mono text-xs">{mapping.target_bucket ?? '—'}</td>
                <td className="px-4 py-2 text-right tabular-nums">{mapping.item_count}</td>
                <td className="px-4 py-2">
                  <Badge variant={mapping.status === 'mapped' ? 'default' : 'secondary'} className="text-[10px]">
                    {mapping.status}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CollapsibleSection>
  );
}

export function McpServersPanel({ servers, t }: { servers: MCPServerPreviewItem[]; t: TranslationFn }) {
  if (servers.length === 0) {
    return null;
  }

  return (
    <CollapsibleSection title={t('preview.mcpServersTitle')} badge={servers.length}>
      <p className="text-xs text-muted-foreground">{t('preview.mcpServersHint')}</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {servers.map((server) => (
          <div
            key={server.name}
            className="space-y-0.5 rounded-lg border border-border/40 bg-background/60 px-3 py-2 text-xs"
          >
            <div className="truncate font-mono font-medium">{server.name}</div>
            <div className="text-muted-foreground">
              <Badge variant="secondary" className="mr-1.5 text-[10px]">
                {server.type}
              </Badge>
              {server.hostSerial ? (
                <Badge variant="outline" className="mr-1.5 text-[10px]">
                  {t('preview.mcpHostSerial')}
                </Badge>
              ) : null}
              {server.commandPreview || server.url || '—'}
            </div>
            {(server.envKeyCount ?? 0) > 0 && (
              <div className="text-amber-600 dark:text-amber-400">
                {t('preview.mcpEnvKeysRequired', { count: server.envKeyCount ?? 0 })}
              </div>
            )}
            {server.type !== 'stdio' &&
              typeof server.keepaliveInterval === 'number' &&
              server.keepaliveInterval > 0 && (
                <div className="text-muted-foreground">
                  {t('preview.mcpKeepalive', { seconds: server.keepaliveInterval })}
                </div>
              )}
            {server.keepaliveIntervalIgnored && (
              <div className="text-amber-600 dark:text-amber-400">{t('preview.mcpKeepaliveIgnored')}</div>
            )}
          </div>
        ))}
      </div>
    </CollapsibleSection>
  );
}
