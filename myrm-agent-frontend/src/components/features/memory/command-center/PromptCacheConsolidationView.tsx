'use client';

/**
 * [INPUT]
 * @/services/memory/ephemeralDelta::PreviewDeltaInjectionResponseDTO, PromptCacheMetricsDTO
 *
 * [OUTPUT]
 * PromptCacheConsolidationView: Subview for session tail-delta preview and layout diagnostics.
 *
 * [POS]
 * Subcomponent for Item 98 (PromptCachePreservingEphemeralDeltaMemorySuite).
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Lock, Sparkles, Zap, TrendingUp, Cpu, RotateCw } from 'lucide-react';
import type { PreviewDeltaInjectionResponseDTO, PromptCacheMetricsDTO } from '@/services/memory/ephemeralDelta';

interface PromptCacheConsolidationViewProps {
  sessionId: string;
  preview: PreviewDeltaInjectionResponseDTO | null;
  metrics: PromptCacheMetricsDTO | null;
  onSimulatePreview: () => Promise<void>;
  isLoading: boolean;
}

export function PromptCacheConsolidationView({
  sessionId,
  preview,
  metrics,
  onSimulatePreview,
  isLoading,
}: PromptCacheConsolidationViewProps): React.JSX.Element {
  const t = useTranslations('memory.commandCenter.promptCache.consolidation');
  const tBase = useTranslations('memory.commandCenter.promptCache.baseContext');
  const layoutStableLabel = t('layoutStable');

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-lg border border-border bg-card/60 backdrop-blur-sm space-y-1">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[11px] font-medium">{t('prefixLayout')}</span>
            <Lock className="w-3.5 h-3.5 text-emerald-500" />
          </div>
          <div className="text-xl font-bold text-foreground">{layoutStableLabel}</div>
          <div className="text-[10px] text-emerald-600 dark:text-emerald-400">
            {metrics?.system_prompt_frozen
              ? t('systemPrefixFrozen')
              : t('chatRingHint')}
          </div>
        </div>

        <div className="p-3.5 rounded-lg border border-border bg-card/60 backdrop-blur-sm space-y-1">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[11px] font-medium">{t('avoidedTokens')}</span>
            <Cpu className="w-3.5 h-3.5 text-blue-500" />
          </div>
          <div className="text-xl font-bold text-foreground">—</div>
          <div className="text-[10px] text-blue-600">{t('estimatedSavings')}</div>
        </div>

        <div className="p-3.5 rounded-lg border border-border bg-card/60 backdrop-blur-sm space-y-1">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[11px] font-medium">{t('perceptionLatency')}</span>
            <Zap className="w-3.5 h-3.5 text-amber-500" />
          </div>
          <div className="text-xl font-bold text-foreground">—</div>
          <div className="text-[10px] text-amber-600">{t('notMeasured')}</div>
        </div>

        <div className="p-3.5 rounded-lg border border-border bg-card/60 backdrop-blur-sm space-y-1">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[11px] font-medium">{t('inFlightDeltas')}</span>
            <TrendingUp className="w-3.5 h-3.5 text-purple-500" />
          </div>
          <div className="text-xl font-bold text-foreground">
            {metrics?.in_flight_deltas_count ?? '—'}
          </div>
          <div className="text-[10px] text-purple-600 font-mono truncate">{sessionId.slice(0, 12)}</div>
        </div>
      </div>

      <p className="text-[11px] leading-relaxed text-muted-foreground">{tBase('myrmBody')}</p>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isLoading}
          onClick={() => void onSimulatePreview()}
          className="text-xs"
        >
          <RotateCw className={`w-3.5 h-3.5 mr-1.5 ${isLoading ? 'animate-spin' : ''}`} />
          {t('simulateInjection')}
        </Button>
        {metrics?.system_prompt_frozen === true && (
          <Badge variant="outline" className="text-[10px] text-emerald-600 border-emerald-500/40">
            <Sparkles className="w-3 h-3 mr-1" />
            {t('systemPrefixFrozen')}
          </Badge>
        )}
      </div>

      {preview && (
        <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-2 max-w-full overflow-x-auto">
          <p className="text-[11px] font-medium text-foreground">{t('augmentedHumanPreview')}</p>
          <pre className="text-[10px] leading-relaxed text-muted-foreground whitespace-pre-wrap break-words font-mono">
            {preview.tail_tag_snippet || preview.augmented_final_human_message}
          </pre>
        </div>
      )}
    </div>
  );
}
