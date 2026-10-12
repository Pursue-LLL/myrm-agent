/**
 * [INPUT]
 * Props: contextCadence, dialecticCadence, dialecticDepth, reasoningLevel, refreshing, onRefresh, onResetSession
 *
 * [OUTPUT]
 * TwoLayerDialecticHudBar: 4-metric telemetry HUD bar for Item 112.
 *
 * [POS]
 * Telemetry HUD header component in TwoLayerDialecticStudioCard.
 * Strict typing applied: No `any` types allowed. Accessible markup. Single file < 160 lines.
 */

'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import {
  Zap,
  RotateCcw,
  RefreshCw,
  Layers,
  Sparkles,
  SlidersHorizontal,
} from 'lucide-react';

export interface TwoLayerDialecticHudBarProps {
  contextCadence: number;
  dialecticCadence: number;
  dialecticDepth: number;
  reasoningLevel: string;
  refreshing: boolean;
  onRefresh: () => void;
  onResetSession: () => void;
}

export const TwoLayerDialecticHudBar: React.FC<TwoLayerDialecticHudBarProps> = ({
  contextCadence,
  dialecticCadence,
  dialecticDepth,
  reasoningLevel,
  refreshing,
  onRefresh,
  onResetSession,
}) => {
  const t = useTranslations('memory.commandCenter.promptCache.twoLayerHud');

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 bg-muted/40 rounded-lg border border-border">
      <div className="flex items-center gap-2.5 p-2 rounded bg-card/60 border border-border/80">
        <div className="p-1.5 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
          <Zap className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] text-muted-foreground font-medium">{t('prefixLayoutLabel')}</div>
          <div className="text-sm font-semibold text-foreground flex items-center gap-1">
            <span>{t('layoutStable')}</span>
            <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-normal">
              {t('chatRingSub')}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2.5 p-2 rounded bg-card/60 border border-border/80">
        <div className="p-1.5 rounded-md bg-blue-500/10 text-blue-600 dark:text-blue-400">
          <Layers className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] text-muted-foreground font-medium">{t('layer1CadenceLabel')}</div>
          <div className="text-sm font-semibold text-foreground flex items-center gap-1">
            <span>{t('everyNTurns', { count: contextCadence })}</span>
            <span className="text-[10px] text-muted-foreground font-normal">{t('lowFreqSnapshot')}</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2.5 p-2 rounded bg-card/60 border border-border/80">
        <div className="p-1.5 rounded-md bg-purple-500/10 text-purple-600 dark:text-purple-400">
          <Sparkles className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] text-muted-foreground font-medium">{t('layer2CadenceLabel')}</div>
          <div className="text-sm font-semibold text-foreground flex items-center gap-1">
            <span>{t('everyNTurns', { count: dialecticCadence })}</span>
            <span className="text-[10px] text-purple-600 dark:text-purple-400 font-normal">
              {t('conflictPatrol')}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between p-2 rounded bg-card/60 border border-border/80">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-md bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
            <SlidersHorizontal className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[11px] text-muted-foreground font-medium">{t('dialecticDepthLabel')}</div>
            <div className="text-sm font-semibold text-foreground">
              {t('passDepthLevel', { depth: dialecticDepth, level: reasoningLevel })}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label={t('refreshTelemetryAria')}
            onClick={onRefresh}
            disabled={refreshing}
            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
            title={t('refreshTelemetryAria')}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            aria-label={t('resetCadenceAria')}
            onClick={onResetSession}
            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
            title={t('resetCadenceAria')}
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};
