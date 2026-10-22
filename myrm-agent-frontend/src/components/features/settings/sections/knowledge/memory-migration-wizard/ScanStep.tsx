'use client';

import { useLocale } from 'next-intl';
import { ArrowRightLeft, Loader2, RefreshCw, Search } from 'lucide-react';

import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { Button } from '@/components/primitives/button';
import type { AgentListItem } from '@/services/agent';
import type { DiscoveryResponse, ExternalSource } from '@/services/migrationDiscovery';

import { CloudUploadZone, PasteImportLane, SourceCard } from './SourceLanes';
import type { TranslationFn } from './wizardShared';

export function ScanStep({
  discovery,
  scanning,
  uploading,
  previewing,
  previewingSource,
  includeEpisodic,
  onIncludeEpisodicChange,
  agents,
  targetAgentId,
  onTargetAgentIdChange,
  onScan,
  onUpload,
  onPreview,
  pasteText,
  pasting,
  pasteModelExtraction,
  onPasteTextChange,
  onPasteModelExtractionChange,
  onPastePreview,
  t,
}: {
  discovery: DiscoveryResponse | null;
  scanning: boolean;
  uploading: boolean;
  previewing: boolean;
  previewingSource: ExternalSource | null;
  includeEpisodic: boolean;
  onIncludeEpisodicChange: (value: boolean) => void;
  agents: AgentListItem[];
  targetAgentId: string | null;
  onTargetAgentIdChange: (value: string | null) => void;
  onScan: () => void;
  onUpload: (file: File) => void;
  onPreview: (source: ExternalSource) => void;
  pasteText: string;
  pasting: boolean;
  pasteModelExtraction: boolean;
  onPasteTextChange: (value: string) => void;
  onPasteModelExtractionChange: (value: boolean) => void;
  onPastePreview: () => void;
  t: TranslationFn;
}) {
  const locale = useLocale();
  const sources = discovery?.sources ?? [];
  const hasOpenClawSource = sources.some((source) => source.competitor === 'openclaw');
  const isCloudMode = discovery !== null && discovery.available === false;

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
        {!isCloudMode && (
          <Button size="sm" variant="outline" onClick={onScan} disabled={scanning} className="shrink-0">
            {scanning ? (
              <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-3.5 w-3.5" />
            )}
            {scanning ? t('scanning') : discovery ? t('rescan') : t('scanButton')}
          </Button>
        )}
      </div>

      {!isCloudMode && discovery && sources.length === 0 && (
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
                {getBuiltinAgentName(agent.id, agent.name || agent.id, locale)}
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

      <CloudUploadZone uploading={uploading} onUpload={onUpload} t={t} />

      <PasteImportLane
        text={pasteText}
        pasting={pasting}
        modelExtraction={pasteModelExtraction}
        onTextChange={onPasteTextChange}
        onModelExtractionChange={onPasteModelExtractionChange}
        onPreview={onPastePreview}
        t={t}
      />
    </div>
  );
}
