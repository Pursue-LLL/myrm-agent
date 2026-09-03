'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Info, ChevronDown, ChevronUp, Wrench, Layers, Cpu, Terminal, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export function HarnessAblationLeverageTooltip() {
  const t = useTranslations('agent.ablationGuide');
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-xl border border-border/60 bg-muted/20 p-2.5 transition-all text-xs">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 font-medium text-foreground">
          <Sparkles className="w-3.5 h-3.5 text-primary" />
          <span>{t('title')}</span>
          <span className="text-[10px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
            {t('badge')}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
        >
          <span>{expanded ? t('collapse') : t('expand')}</span>
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>
      </div>

      {expanded && (
        <div className="mt-2.5 pt-2 border-t border-border/40 space-y-2 text-muted-foreground leading-normal">
          <p>{t('description')}</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1 font-mono text-[11px]">
            <div className="flex items-center justify-between p-1.5 rounded bg-card border border-border/50">
              <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-semibold">
                <Wrench className="w-3 h-3" /> {t('toolTier')}
              </span>
              <span className="text-amber-500 font-semibold">★★★★★</span>
            </div>
            <div className="flex items-center justify-between p-1.5 rounded bg-card border border-border/50">
              <span className="flex items-center gap-1 text-blue-600 dark:text-blue-400 font-semibold">
                <Layers className="w-3 h-3" /> {t('middlewareTier')}
              </span>
              <span className="text-amber-500 font-semibold">★★★★☆</span>
            </div>
            <div className="flex items-center justify-between p-1.5 rounded bg-card border border-border/50">
              <span className="flex items-center gap-1 text-purple-600 dark:text-purple-400 font-semibold">
                <Cpu className="w-3 h-3" /> {t('memoryTier')}
              </span>
              <span className="text-amber-500 font-semibold">★★★☆☆</span>
            </div>
            <div className="flex items-center justify-between p-1.5 rounded bg-card border border-border/50">
              <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400 font-semibold">
                <Terminal className="w-3 h-3" /> {t('promptTier')}
              </span>
              <span className="text-amber-500 font-semibold">★★☆☆☆</span>
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground/80 italic">{t('cacheTip')}</p>
        </div>
      )}
    </div>
  );
}

export default HarnessAblationLeverageTooltip;
