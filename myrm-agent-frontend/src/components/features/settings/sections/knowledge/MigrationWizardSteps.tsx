'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import {
  ArrowLeft,
  ArrowRightLeft,
  CheckCircle2,
  Folder,
  Loader2,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldAlert,
  Download,
} from 'lucide-react';

import { queueMigrationChatAgent } from '@/lib/migrationChatHandoff';
import { exportMemoryArchive } from '@/services/memoryArchive';

import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import { getMigrationSourceDisplayName, type ExternalSource, type DiscoveryResponse } from '@/services/migrationDiscovery';
import type { AgentListItem } from '@/services/agent';
import type {
  MemoryImportConfirmResponse,
  MemoryImportCoverageItem,
  MemoryImportDryRunResponse,
  MigrationLanePreviewItem,
} from '@/services/memoryArchive';
import type { SkillMigrationSubmitResponse } from '@/services/skillMigration';

export interface TranslationFn {
  (key: string, values?: Record<string, string | number>): string;
}

const COVERAGE_LABEL_KEYS = new Set([
  'instruction_lane',
  'memory_lane',
  'memory_persona',
  'skills_review',
  'api_keys_manual',
  'mcp_ready',
  'mcp_manual',
  'channels_manual',
  'agent_config_manual',
  'no_importable_data',
]);

export function CoverageMatrix({ items, t }: { items: MemoryImportCoverageItem[]; t: TranslationFn }) {
  if (items.length === 0) return null;

  const statusStyles: Record<string, string> = {
    ready: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
    review: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400',
    manual: 'border-border/60 bg-secondary/30 text-muted-foreground',
    missing: 'border-destructive/30 bg-destructive/10 text-destructive',
  };

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">{t('preview.coverageTitle')}</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        {items.map((item) => (
          <div
            key={item.key}
            className={cn('rounded-lg border px-3 py-2.5 text-xs', statusStyles[item.status] ?? statusStyles.manual)}
          >
            <div className="font-medium">
              {COVERAGE_LABEL_KEYS.has(item.label) ? t(`preview.coverageLabels.${item.label}`) : item.label}
            </div>
            <div className="mt-0.5 opacity-80">{t(`preview.coverageStatus.${item.status}`)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ScanStep({
  discovery,
  scanning,
  previewing,
  previewingSource,
  includeEpisodic,
  onIncludeEpisodicChange,
  agents,
  targetAgentId,
  onTargetAgentIdChange,
  onScan,
  onPreview,
  t,
}: {
  discovery: DiscoveryResponse | null;
  scanning: boolean;
  previewing: boolean;
  previewingSource: ExternalSource | null;
  includeEpisodic: boolean;
  onIncludeEpisodicChange: (value: boolean) => void;
  agents: AgentListItem[];
  targetAgentId: string | null;
  onTargetAgentIdChange: (value: string | null) => void;
  onScan: () => void;
  onPreview: (source: ExternalSource) => void;
  t: TranslationFn;
}) {
  const sources = discovery?.sources ?? [];
  const hasOpenClawSource = sources.some((source) => source.competitor === 'openclaw');

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-accent/10 p-2.5">
            <ArrowRightLeft className="h-5 w-5 text-accent-foreground" />
          </div>
          <div>
            <h2 className="text-lg font-semibold">{t('title')}</h2>
            <p className="text-sm text-muted-foreground">{t('description')}</p>
          </div>
        </div>
        <Button size="sm" variant="outline" onClick={onScan} disabled={scanning} className="shrink-0">
          {scanning ? (
            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="mr-2 h-3.5 w-3.5" />
          )}
          {scanning ? t('scanning') : discovery ? t('rescan') : t('scanButton')}
        </Button>
      </div>

      {discovery && sources.length === 0 && (
        <div className="rounded-xl border border-border/50 bg-secondary/20 p-8 text-center">
          <Search className="mx-auto mb-3 h-8 w-8 text-muted-foreground/40" />
          <p className="text-sm font-medium text-muted-foreground">{t('noSourcesFound')}</p>
          <p className="mt-1 text-xs text-muted-foreground/60">{t('noSourcesHint')}</p>
        </div>
      )}

      {sources.length > 0 && (
        <div className="space-y-3 rounded-xl border border-border/50 bg-secondary/20 p-4">
          <label className="block text-xs font-medium text-muted-foreground">{t('targetAgentLabel')}</label>
          <select
            value={targetAgentId ?? ''}
            onChange={(e) => onTargetAgentIdChange(e.target.value ? e.target.value : null)}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          >
            <option value="">{t('targetAgentCreate')}</option>
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
          <p className="text-[11px] text-muted-foreground/70">{t('targetAgentHint')}</p>
          {hasOpenClawSource && (
            <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
              <input
                type="checkbox"
                checked={includeEpisodic}
                onChange={(e) => onIncludeEpisodicChange(e.target.checked)}
                className="rounded border-border"
              />
              {t('scanIncludeEpisodic')}
            </label>
          )}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {sources.map((source) => {
          const isThisPreviewing = previewing && previewingSource?.competitor === source.competitor;
          return (
            <SourceCard
              key={`${source.competitor}-${source.root}`}
              source={source}
              previewing={isThisPreviewing}
              disabled={previewing}
              onPreview={() => onPreview(source)}
              t={t}
            />
          );
        })}
      </div>
    </div>
  );
}

function SourceCard({
  source,
  previewing,
  disabled,
  onPreview,
  t,
}: {
  source: ExternalSource;
  previewing: boolean;
  disabled: boolean;
  onPreview: () => void;
  t: TranslationFn;
}) {
  const confidenceVariant =
    source.confidence === 'high' ? 'default' : source.confidence === 'medium' ? 'secondary' : 'outline';
  const confidenceLabel =
    source.confidence === 'high'
      ? t('sourceCard.confidenceHigh')
      : source.confidence === 'medium'
        ? t('sourceCard.confidenceMedium')
        : t('sourceCard.confidenceLow');

  return (
    <div className="rounded-xl border border-border/50 bg-card p-5 space-y-3 hover:border-border transition-colors">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2.5">
          <div className="rounded-lg bg-primary/10 p-2">
            <Folder className="h-4 w-4 text-primary" />
          </div>
          <div>
            <span className="text-sm font-semibold">{getMigrationSourceDisplayName(source.competitor)}</span>
            <Badge variant={confidenceVariant} className="ml-2 text-[10px]">
              {confidenceLabel}
            </Badge>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
        {source.memory_count_estimate > 0 && (
          <span className="rounded-md bg-secondary/60 px-2 py-0.5">
            {t('sourceCard.memories', { count: source.memory_count_estimate })}
          </span>
        )}
        {source.skill_count > 0 && (
          <span className="rounded-md bg-secondary/60 px-2 py-0.5">
            {t('sourceCard.skills', { count: source.skill_count })}
          </span>
        )}
        <span className="rounded-md bg-secondary/60 px-2 py-0.5">
          {t('sourceCard.files', { count: source.files.length })}
        </span>
      </div>

      {source.has_api_keys && (
        <div className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
          <ShieldAlert className="h-3.5 w-3.5" />
          {t('sourceCard.apiKeysDetected')}
        </div>
      )}

      <div className="text-[11px] text-muted-foreground/50 truncate" title={source.root}>
        {t('sourceCard.rootPath')}: {source.root}
      </div>

      <Button size="sm" className="w-full h-8 text-xs" onClick={onPreview} disabled={disabled}>
        {previewing ? (
          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
        ) : (
          <Search className="mr-1.5 h-3.5 w-3.5" />
        )}
        {previewing ? t('sourceCard.previewing') : t('sourceCard.previewButton')}
      </Button>
    </div>
  );
}

function MigrationLaneMatrix({ lanes, t }: { lanes: MigrationLanePreviewItem[]; t: TranslationFn }) {
  if (lanes.length === 0) return null;

  const statusStyles: Record<string, string> = {
    ready: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
    review: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400',
    manual: 'border-border/60 bg-secondary/30 text-muted-foreground',
    missing: 'border-destructive/30 bg-destructive/10 text-destructive',
    warning: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400',
    critical: 'border-destructive/30 bg-destructive/10 text-destructive',
    pending: 'border-border/60 bg-secondary/30 text-muted-foreground',
  };

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">{t('preview.lanesTitle')}</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        {lanes.map((lane) => (
          <div
            key={lane.lane}
            className={cn('rounded-lg border px-3 py-2.5 text-xs', statusStyles[lane.status] ?? statusStyles.manual)}
          >
            <div className="font-medium">{t(`preview.laneLabels.${lane.label}`, { defaultValue: lane.label })}</div>
            <div className="mt-1 text-muted-foreground">{lane.detail}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PreviewStep({
  source,
  dryRun,
  importing,
  importSecrets,
  onImportSecretsChange,
  onConfirm,
  onBack,
  t,
}: {
  source: ExternalSource;
  dryRun: MemoryImportDryRunResponse;
  importing: boolean;
  importSecrets: boolean;
  onImportSecretsChange: (value: boolean) => void;
  onConfirm: () => void;
  onBack: () => void;
  t: TranslationFn;
}) {
  const { result } = dryRun;
  const { summary, mappings, warnings } = result;
  const [exportingBackup, setExportingBackup] = useState(false);

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
          {t('preview.title', { source: getMigrationSourceDisplayName(source.competitor) })}
        </h2>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryCell label={t('preview.totalItems')} value={summary.total_items} />
        <SummaryCell label={t('preview.mappedItems')} value={summary.mapped_items} />
        <SummaryCell label={t('preview.unmappedItems')} value={summary.unmapped_items} />
        <SummaryCell label={t('preview.status')} value={summary.status} className={statusColors[summary.status]} />
      </div>

      <CoverageMatrix items={dryRun.coverage_items ?? []} t={t} />

      <MigrationLaneMatrix lanes={dryRun.migration_lanes ?? []} t={t} />

      {(dryRun.instruction_total_chars ?? 0) > 8000 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-700 dark:text-amber-400">
          {t('preview.instructionLargeWarning', { count: dryRun.instruction_total_chars ?? 0 })}
        </div>
      )}

      {dryRun.providers_configured === false && source.has_api_keys && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-xs text-destructive space-y-2">
          <p>{t('preview.providersMissingHint')}</p>
          <Button asChild size="sm" variant="outline" className="h-7 text-xs">
            <Link href="/settings/models">{t('preview.configureProvidersLink')}</Link>
          </Button>
        </div>
      )}

      {(dryRun.instruction_preview_persona || (dryRun.instruction_preview_rule_names?.length ?? 0) > 0) && (
        <div className="space-y-2 rounded-xl border border-border/50 bg-secondary/20 p-4">
          <h3 className="text-sm font-medium">{t('preview.instructionPreviewTitle')}</h3>
          {dryRun.instruction_preview_persona && (
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-background/80 p-3 text-[11px] text-muted-foreground">
              {dryRun.instruction_preview_persona}
            </pre>
          )}
          {(dryRun.instruction_preview_rule_names?.length ?? 0) > 0 && (
            <ul className="list-disc pl-5 text-xs text-muted-foreground space-y-1">
              {dryRun.instruction_preview_rule_names?.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {dryRun.pending_skills && dryRun.pending_skills.length > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-700 dark:text-amber-400">
          {t('preview.pendingSkillsHint', { count: dryRun.pending_skills.length })}
        </div>
      )}

      {mappings.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">{t('preview.mappings')}</h3>
          <div className="rounded-xl border border-border/50 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-secondary/40">
                <tr>
                  <th className="px-4 py-2 text-left font-medium text-muted-foreground text-xs">
                    {t('preview.tableSource')}
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-muted-foreground text-xs">
                    {t('preview.tableTarget')}
                  </th>
                  <th className="px-4 py-2 text-right font-medium text-muted-foreground text-xs">
                    {t('preview.tableItems')}
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-muted-foreground text-xs">
                    {t('preview.tableStatus')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30">
                {mappings.map((m, i) => (
                  <tr key={i} className="hover:bg-secondary/20 transition-colors">
                    <td className="px-4 py-2 font-mono text-xs">{m.source_bucket}</td>
                    <td className="px-4 py-2 font-mono text-xs">{m.target_bucket ?? '—'}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{m.item_count}</td>
                    <td className="px-4 py-2">
                      <Badge variant={m.status === 'mapped' ? 'default' : 'secondary'} className="text-[10px]">
                        {m.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">{t('preview.warnings')}</h3>
          <ul className="list-disc pl-5 space-y-1">
            {warnings.map((w, i) => (
              <li key={i} className="text-xs text-amber-600 dark:text-amber-400">
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap gap-4 text-[11px] text-muted-foreground/50">
        <span>
          {t('preview.dryRunId')}: {dryRun.dry_run_id}
        </span>
        <span>
          {t('preview.expiresAt')}: {new Date(dryRun.expires_at).toLocaleString()}
        </span>
      </div>

      <div className="rounded-xl border border-border/50 bg-secondary/20 p-4 space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground">{t('preview.backupHint')}</p>
          <Button
            size="sm"
            variant="outline"
            className="h-8 text-xs shrink-0"
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
          <label className="flex items-start gap-2 text-xs cursor-pointer">
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
      </div>

      <div className="flex flex-wrap gap-3 pt-2">
        <Button variant="outline" onClick={onBack} disabled={importing}>
          {t('preview.cancel')}
        </Button>
        <Button
          onClick={onConfirm}
          disabled={importing || summary.status === 'critical' || summary.status === 'missing'}
        >
          {importing && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {importing ? t('preview.importing') : t('preview.confirmImport')}
        </Button>
      </div>
    </div>
  );
}

function SummaryCell({ label, value, className = '' }: { label: string; value: string | number; className?: string }) {
  return (
    <div className="rounded-xl border border-border/50 bg-secondary/20 p-3">
      <div className="text-[11px] text-muted-foreground/60 mb-1">{label}</div>
      <div className={cn('text-lg font-semibold tabular-nums', className)}>{value}</div>
    </div>
  );
}

export function ResultStep({
  result,
  skillSubmitResult,
  skillSubmitFailed,
  secretsImportMessage,
  rollingBack,
  onRollback,
  onRetrySkillSubmit,
  retryingSkills,
  onDone,
  t,
}: {
  result: MemoryImportConfirmResponse;
  skillSubmitResult: SkillMigrationSubmitResponse | null;
  skillSubmitFailed: boolean;
  secretsImportMessage: string | null;
  rollingBack: boolean;
  onRetrySkillSubmit: () => void;
  retryingSkills: boolean;
  onDone: () => void;
  t: TranslationFn;
}) {
  const router = useRouter();

  const handleStartChat = () => {
    if (!result.target_agent_id) {
      return;
    }
    queueMigrationChatAgent(result.target_agent_id);
    router.push('/');
  };

  return (
    <div className="space-y-6 text-center max-w-lg mx-auto py-8">
      <CheckCircle2 className="mx-auto h-12 w-12 text-emerald-500" />
      <div className="space-y-2">
        <h2 className="text-xl font-semibold">{t('result.title')}</h2>
        <p className="text-sm text-muted-foreground">{t('result.totalImported', { count: result.total_imported })}</p>
        {skillSubmitResult && (
          <p className="text-sm text-muted-foreground">
            {t('result.skillsSubmitted', { count: skillSubmitResult.total_items })}
          </p>
        )}
        {skillSubmitFailed && (
          <p className="text-sm text-amber-600 dark:text-amber-400">{t('result.skillsSubmitFailed')}</p>
        )}
        {secretsImportMessage && <p className="text-sm text-muted-foreground">{secretsImportMessage}</p>}
        {result.agent_created && result.target_agent_id && (
          <p className="text-sm text-muted-foreground">{t('result.agentCreated', { id: result.target_agent_id })}</p>
        )}
        {!result.agent_created && result.target_agent_id && (
          <p className="text-sm text-muted-foreground">{t('result.agentUpdated', { id: result.target_agent_id })}</p>
        )}
        {result.global_instructions_updated && (
          <p className="text-sm text-muted-foreground">{t('result.globalInstructionsUpdated')}</p>
        )}
        {(result.workspace_rules_written ?? 0) > 0 && (
          <p className="text-sm text-muted-foreground">
            {t('result.workspaceRulesWritten', { count: result.workspace_rules_written })}
          </p>
        )}
        {(result.workspace_rules_skipped ?? 0) > 0 && (
          <p className="text-sm text-amber-600 dark:text-amber-400">
            {t('result.workspaceRulesSkipped', { count: result.workspace_rules_skipped })}
          </p>
        )}
      </div>

      <div className="flex flex-wrap justify-center gap-4 text-[11px] text-muted-foreground/50">
        <span>
          {t('result.batchId')}: {result.import_batch_id}
        </span>
      </div>

      <p className="text-xs text-muted-foreground/60">
        {skillSubmitResult
          ? t('result.nextStepsWithSkills')
          : skillSubmitFailed
            ? t('result.nextStepsPartialFailure')
            : t('result.nextStepsMemoryOnly')}
      </p>

      <div className="flex flex-wrap justify-center gap-2">
        {result.target_agent_id && (
          <Button size="sm" className="h-8 text-xs" onClick={handleStartChat}>
            {t('result.startChat')}
          </Button>
        )}
        {skillSubmitFailed && (
          <Button
            size="sm"
            variant="secondary"
            className="h-8 text-xs"
            onClick={onRetrySkillSubmit}
            disabled={retryingSkills}
          >
            {retryingSkills && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            {retryingSkills ? t('result.retryingSkillsSubmit') : t('result.retrySkillsSubmit')}
          </Button>
        )}
        {skillSubmitResult && (
          <Button asChild size="sm" variant="secondary" className="h-8 text-xs">
            <Link href="/settings/memory?sub=migration">{t('result.reviewSkills')}</Link>
          </Button>
        )}
        <Button asChild size="sm" variant="outline" className="h-8 text-xs">
          <Link href="/settings/mcp">{t('result.configureMcp')}</Link>
        </Button>
        <Button asChild size="sm" variant="outline" className="h-8 text-xs">
          <Link href="/settings/channels">{t('result.configureChannels')}</Link>
        </Button>
        <Button asChild size="sm" variant="outline" className="h-8 text-xs">
          <Link href="/settings/models">{t('result.configureProviders')}</Link>
        </Button>
      </div>

      <p className="text-xs text-muted-foreground/60">{t('result.rollbackAvailable')}</p>

      <div className="flex justify-center gap-3 pt-2">
        <Button variant="outline" size="sm" onClick={onRollback} disabled={rollingBack}>
          {rollingBack ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
          )}
          {rollingBack ? t('result.rollingBack') : t('result.rollbackButton')}
        </Button>
        <Button size="sm" onClick={onDone}>
          {t('result.done')}
        </Button>
      </div>
    </div>
  );
}
