'use client';

import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { useState } from 'react';
import { ArrowLeft, Download, Loader2, ShieldAlert } from 'lucide-react';

import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import { exportMemoryArchive } from '@/services/memory/archive';
import type { MemoryImportDryRunResponse } from '@/services/memory/archive';
import type { ExternalSource } from '@/services/migrationDiscovery';

import {
  CoverageMatrix,
  HermesArchitectureMappingCard,
  MigrationLaneMatrix,
  SessionPreviewCard,
  SummaryCell,
  TokenEconomicsCard,
} from './PreviewCards';
import {
  CronSkippedPanel,
  ImportWarningsPanel,
  InstructionPreviewPanel,
  MappingsPanel,
  McpServersPanel,
  PreviewItemsPanel,
} from './PreviewPanels';
import { resolveSourceDisplayName, type TranslationFn } from './wizardShared';

export function PreviewStep({
  source,
  dryRun,
  importing,
  importSecrets,
  onImportSecretsChange,
  importSessions,
  onImportSessionsChange,
  onConfirm,
  onBack,
  t,
}: {
  source: ExternalSource;
  dryRun: MemoryImportDryRunResponse;
  importing: boolean;
  importSecrets: boolean;
  onImportSecretsChange: (value: boolean) => void;
  importSessions: boolean;
  onImportSessionsChange: (value: boolean) => void;
  onConfirm: () => void;
  onBack: () => void;
  t: TranslationFn;
}) {
  const { result } = dryRun;
  const { summary, mappings, warnings } = result;
  const tMemory = useTranslations('memory');
  const locale = useLocale();
  const [exportingBackup, setExportingBackup] = useState(false);
  const [trustedSourceConfirmed, setTrustedSourceConfirmed] = useState(false);

  const isPiOrHasSkills =
    source.competitor === 'pi' || (source.skill_count ?? 0) > 0 || (dryRun.pending_skills?.length ?? 0) > 0;

  const previewBuckets = Object.entries(result.normalized_data ?? {}).filter(
    ([, entries]) => Array.isArray(entries) && entries.length > 0,
  );
  const lanes = (dryRun.migration_lanes ?? []).map((lane) =>
    lane.lane === 'session' && !importSessions
      ? { ...lane, status: 'manual', detail_parts: [{ code: 'session_skipped', params: {} }] }
      : lane,
  );

  const statusColors: Record<string, string> = {
    ready: 'text-emerald-600 dark:text-emerald-400',
    warning: 'text-amber-600 dark:text-amber-400',
    critical: 'text-destructive',
    missing: 'text-muted-foreground',
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack} className="h-8 w-8 p-0">
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h2 className="text-lg font-semibold">
          {t('preview.title', { source: resolveSourceDisplayName(source.competitor, t) })}
        </h2>
      </div>

      {source.competitor === 'hermes' && (
        <div className="rounded-xl border border-primary/20 bg-primary/5 px-4 py-3 text-xs text-muted-foreground">
          {t('preview.hermesEconomyHint')}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryCell label={t('preview.totalItems')} value={summary.total_items} />
        <SummaryCell label={t('preview.mappedItems')} value={summary.mapped_items} />
        <SummaryCell label={t('preview.unmappedItems')} value={summary.unmapped_items} />
        <SummaryCell label={t('preview.status')} value={summary.status} className={statusColors[summary.status]} />
      </div>

      <CoverageMatrix items={dryRun.coverage_items ?? []} t={t} />

      <MigrationLaneMatrix lanes={lanes} t={t} />

      <PreviewItemsPanel buckets={previewBuckets} t={t} />

      {(dryRun.session_preview?.length ?? 0) > 0 && (
        <label className="flex cursor-pointer items-start gap-2 rounded-xl border border-border/50 bg-secondary/20 px-4 py-3 text-xs">
          <input
            type="checkbox"
            data-testid="migration-import-sessions"
            className="mt-0.5 rounded border-border"
            checked={importSessions}
            onChange={(event) => onImportSessionsChange(event.target.checked)}
            disabled={importing}
          />
          <span className="min-w-0">
            <span className="block font-medium text-foreground">
              {t('preview.importSessionsLabel', { count: dryRun.session_preview?.length ?? 0 })}
            </span>
            <span className="mt-0.5 block leading-relaxed text-muted-foreground">
              {t('preview.importSessionsHint')}
            </span>
          </span>
        </label>
      )}

      {importSessions && <SessionPreviewCard sessions={dryRun.session_preview ?? []} t={t} />}

      {source.competitor === 'hermes' && <HermesArchitectureMappingCard t={t} />}

      <CronSkippedPanel items={dryRun.cron_skipped ?? []} t={t} />

      {dryRun.token_economics && (
        <TokenEconomicsCard
          data={dryRun.token_economics}
          sourceName={resolveSourceDisplayName(source.competitor, t)}
          t={t}
        />
      )}

      {(dryRun.instruction_total_chars ?? 0) > 8000 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-700 dark:text-amber-400">
          {t('preview.instructionLargeWarning', { count: dryRun.instruction_total_chars ?? 0 })}
        </div>
      )}

      {dryRun.providers_configured === false && source.has_api_keys && (
        <div className="space-y-2 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-xs text-destructive">
          <p>{t('preview.providersMissingHint')}</p>
          <Button asChild size="sm" variant="outline" className="h-7 text-xs">
            <Link href="/settings/models">{t('preview.configureProvidersLink')}</Link>
          </Button>
        </div>
      )}

      {(dryRun.instruction_preview_persona || (dryRun.instruction_preview_rule_names?.length ?? 0) > 0) && (
        <InstructionPreviewPanel
          persona={dryRun.instruction_preview_persona}
          ruleNames={dryRun.instruction_preview_rule_names ?? []}
          t={t}
        />
      )}

      {dryRun.pending_skills && dryRun.pending_skills.length > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-700 dark:text-amber-400">
          {(dryRun.pending_skills_total ?? dryRun.pending_skills.length) > dryRun.pending_skills.length
            ? t('preview.pendingSkillsTruncated', {
                kept: dryRun.pending_skills.length,
                total: dryRun.pending_skills_total,
              })
            : t('preview.pendingSkillsHint', { count: dryRun.pending_skills.length })}
        </div>
      )}

      {summary.mapped_items > 0 && <p className="text-xs text-muted-foreground">{tMemory('importDedupeHint')}</p>}

      <MappingsPanel mappings={mappings} t={t} />

      <ImportWarningsPanel warnings={warnings} t={t} />

      <McpServersPanel servers={dryRun.mcp_servers_preview ?? []} t={t} />

      <div className="flex flex-wrap gap-4 text-[11px] text-muted-foreground/50">
        <span>
          {t('preview.expiresAt')}:{' '}
          {new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(
            new Date(dryRun.expires_at),
          )}
        </span>
      </div>

      <div className="space-y-3 rounded-xl border border-border/50 bg-secondary/20 p-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground">{t('preview.backupHint')}</p>
          <Button
            size="sm"
            variant="outline"
            className="h-8 shrink-0 text-xs"
            disabled={exportingBackup || importing}
            onClick={async () => {
              setExportingBackup(true);
              try {
                const { archive } = await exportMemoryArchive();
                const blob = new Blob([JSON.stringify(archive, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const anchor = document.createElement('a');
                anchor.href = url;
                anchor.download = `myrm-pre-migration-backup-${Date.now()}.json`;
                anchor.click();
                URL.revokeObjectURL(url);
              } finally {
                setExportingBackup(false);
              }
            }}
          >
            {exportingBackup ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="mr-1.5 h-3.5 w-3.5" />
            )}
            {exportingBackup ? t('preview.exportingBackup') : t('preview.exportBackup')}
          </Button>
        </div>

        {source.has_api_keys && (
          <label className="flex cursor-pointer items-start gap-2 text-xs">
            <input
              type="checkbox"
              className="mt-0.5 rounded border-border"
              checked={importSecrets}
              onChange={(event) => onImportSecretsChange(event.target.checked)}
              disabled={importing}
            />
            <span className="text-muted-foreground">{t('preview.importSecretsLabel')}</span>
          </label>
        )}

        {isPiOrHasSkills && (
          <div className="space-y-2 rounded-xl border border-amber-500/30 bg-amber-500/5 p-3.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-amber-800 dark:text-amber-300">
              <ShieldAlert className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
              <span>{t('preview.trustedSourceTitle')}</span>
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">{t('preview.trustedSourceDesc')}</p>
            <label className="flex cursor-pointer items-start gap-2 pt-1 text-xs">
              <input
                type="checkbox"
                data-testid="migration-trusted-source-checkbox"
                className="mt-0.5 rounded border-border"
                checked={trustedSourceConfirmed}
                onChange={(event) => setTrustedSourceConfirmed(event.target.checked)}
                disabled={importing}
              />
              <span className="font-medium text-foreground">{t('preview.trustedSourceConfirmLabel')}</span>
            </label>
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-3 pt-2">
        <Button variant="outline" onClick={onBack} disabled={importing}>
          {t('preview.cancel')}
        </Button>
        <Button
          onClick={onConfirm}
          disabled={
            importing ||
            summary.status === 'critical' ||
            summary.status === 'missing' ||
            (isPiOrHasSkills && !trustedSourceConfirmed)
          }
        >
          {importing && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {importing ? t('preview.importing') : t('preview.confirmImport')}
        </Button>
      </div>
    </div>
  );
}
