'use client';

/**
 * [INPUT]
 * Props: config, onUpdateConfig
 *
 * [OUTPUT]
 * DialecticCadenceControlsView: cadence and depth tuning panel for Item 112 lab.
 *
 * [POS]
 * Sub-view in TwoLayerDialecticStudioCard.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Sliders, RotateCcw, Check, Sparkles, Layers, Cpu } from 'lucide-react';
import type { DialecticCadenceConfigDTO } from '@/services/memory/twoLayerDialectic';
import { FALLBACK_CADENCE_CONFIG } from './twoLayerDialecticFallbacks';

export interface DialecticCadenceControlsViewProps {
  config: DialecticCadenceConfigDTO;
  onUpdateConfig: (newConfig: DialecticCadenceConfigDTO) => void;
}

export const DialecticCadenceControlsView: React.FC<
  DialecticCadenceControlsViewProps
> = ({ config, onUpdateConfig }) => {
  const t = useTranslations('memory.commandCenter.promptCache.twoLayerCadence');
  const tHud = useTranslations('memory.commandCenter.promptCache.twoLayerHud');
  const [contextCadence, setContextCadence] = useState<number>(config.context_cadence);
  const [dialecticCadence, setDialecticCadence] = useState<number>(config.dialectic_cadence);
  const [dialecticDepth, setDialecticDepth] = useState<number>(config.dialectic_depth);
  const [reasoningLevel, setReasoningLevel] = useState<'fast' | 'standard' | 'deep'>(
    config.dialectic_reasoning_level,
  );
  const [savedBanner, setSavedBanner] = useState<boolean>(false);

  const reasoningLabels: Record<'fast' | 'standard' | 'deep', string> = {
    fast: t('reasoningFast'),
    standard: t('reasoningStandard'),
    deep: t('reasoningDeep'),
  };

  const handleApply = () => {
    onUpdateConfig({
      context_cadence: contextCadence,
      dialectic_cadence: dialecticCadence,
      dialectic_depth: dialecticDepth,
      dialectic_reasoning_level: reasoningLevel,
    });
    setSavedBanner(true);
    setTimeout(() => setSavedBanner(false), 2500);
  };

  const handleResetDefaults = () => {
    setContextCadence(FALLBACK_CADENCE_CONFIG.context_cadence);
    setDialecticCadence(FALLBACK_CADENCE_CONFIG.dialectic_cadence);
    setDialecticDepth(FALLBACK_CADENCE_CONFIG.dialectic_depth);
    setReasoningLevel(FALLBACK_CADENCE_CONFIG.dialectic_reasoning_level);
    onUpdateConfig(FALLBACK_CADENCE_CONFIG);
  };

  return (
    <div className="p-4 bg-card/60 rounded-lg border border-border space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-border/60 pb-3">
        <div className="flex items-center gap-2">
          <Sliders className="w-4 h-4 text-primary" />
          <h3 className="text-xs font-semibold text-foreground">{t('panelTitle')}</h3>
        </div>
        <button
          type="button"
          onClick={handleResetDefaults}
          className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md bg-muted hover:bg-muted/80 text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <RotateCcw className="w-3 h-3" />
          <span>{t('resetDefaults')}</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="p-3 rounded-lg bg-muted/20 border border-border space-y-2">
          <div className="flex items-center justify-between text-xs gap-2">
            <label htmlFor="context-cadence-slider" className="font-medium text-foreground flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-blue-500 shrink-0" />
              <span>{t('layer1IntervalLabel')}</span>
            </label>
            <span className="font-mono font-semibold text-primary shrink-0">
              {tHud('everyNTurns', { count: contextCadence })}
            </span>
          </div>
          <input
            id="context-cadence-slider"
            type="range"
            min={1}
            max={15}
            value={contextCadence}
            onChange={(e) => setContextCadence(Number(e.target.value))}
            className="w-full accent-primary cursor-pointer"
          />
          <p className="text-[11px] text-muted-foreground leading-relaxed">{t('layer1IntervalHint')}</p>
        </div>

        <div className="p-3 rounded-lg bg-muted/20 border border-border space-y-2">
          <div className="flex items-center justify-between text-xs gap-2">
            <label htmlFor="dialectic-cadence-slider" className="font-medium text-foreground flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-purple-500 shrink-0" />
              <span>{t('layer2IntervalLabel')}</span>
            </label>
            <span className="font-mono font-semibold text-purple-600 dark:text-purple-400 shrink-0">
              {tHud('everyNTurns', { count: dialecticCadence })}
            </span>
          </div>
          <input
            id="dialectic-cadence-slider"
            type="range"
            min={1}
            max={10}
            value={dialecticCadence}
            onChange={(e) => setDialecticCadence(Number(e.target.value))}
            className="w-full accent-purple-500 cursor-pointer"
          />
          <p className="text-[11px] text-muted-foreground leading-relaxed">{t('layer2IntervalHint')}</p>
        </div>

        <div className="p-3 rounded-lg bg-muted/20 border border-border space-y-2">
          <div className="text-xs font-medium text-foreground flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
            <label htmlFor="dialectic-depth-radio-group">{t('depthLabel')}</label>
          </div>
          <div id="dialectic-depth-radio-group" className="grid grid-cols-3 gap-2">
            {[1, 2, 3].map((depth) => (
              <button
                key={`depth-${depth}`}
                type="button"
                onClick={() => setDialecticDepth(depth)}
                className={`py-1.5 px-2 text-xs rounded-md border text-center transition-all focus:outline-none focus:ring-2 focus:ring-primary ${
                  dialecticDepth === depth
                    ? 'bg-primary text-primary-foreground border-primary font-medium'
                    : 'bg-background text-muted-foreground border-input hover:text-foreground'
                }`}
              >
                {t('passButton', { depth })}
              </button>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground leading-relaxed">{t('depthHint')}</p>
        </div>

        <div className="p-3 rounded-lg bg-muted/20 border border-border space-y-2">
          <div className="text-xs font-medium text-foreground flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-emerald-500" />
            <label htmlFor="reasoning-level-radio-group">{t('reasoningLabel')}</label>
          </div>
          <div id="reasoning-level-radio-group" className="grid grid-cols-3 gap-2">
            {(['fast', 'standard', 'deep'] as const).map((lvl) => (
              <button
                key={`lvl-${lvl}`}
                type="button"
                onClick={() => setReasoningLevel(lvl)}
                className={`py-1.5 px-2 text-xs rounded-md border text-center transition-all focus:outline-none focus:ring-2 focus:ring-primary ${
                  reasoningLevel === lvl
                    ? 'bg-primary text-primary-foreground border-primary font-medium'
                    : 'bg-background text-muted-foreground border-input hover:text-foreground'
                }`}
              >
                {reasoningLabels[lvl]}
              </button>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground leading-relaxed">{t('reasoningHint')}</p>
        </div>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between pt-2">
        <div>
          {savedBanner ? (
            <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
              <Check className="w-3.5 h-3.5" />
              <span>{t('savedBanner')}</span>
            </span>
          ) : null}
        </div>
        <button
          type="button"
          aria-label={t('applyAria')}
          onClick={handleApply}
          className="flex items-center justify-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <Check className="w-3.5 h-3.5" />
          <span>{t('applyLabel')}</span>
        </button>
      </div>
    </div>
  );
};
