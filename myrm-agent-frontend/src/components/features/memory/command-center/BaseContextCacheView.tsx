'use client';

/**
 * [INPUT]
 * Props: baseContext, onForceRefresh, refreshing
 *
 * [OUTPUT]
 * BaseContextCacheView: Layer 1 base context layout dashboard (prefix stability, not hit-rate SLA).
 *
 * [POS]
 * Sub-view in TwoLayerDialecticStudioCard for Item 112.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import {
  ShieldCheck,
  Hash,
  Clock,
  Layers,
  CheckCircle2,
  RefreshCw,
  Info,
} from 'lucide-react';
import type { BaseContextPayloadDTO } from '@/services/memory/twoLayerDialectic';

export interface BaseContextCacheViewProps {
  baseContext: BaseContextPayloadDTO;
  onForceRefresh: () => void;
  refreshing: boolean;
}

export const BaseContextCacheView: React.FC<BaseContextCacheViewProps> = ({
  baseContext,
  onForceRefresh,
  refreshing,
}) => {
  const t = useTranslations('memory.commandCenter.promptCache.baseContext');

  return (
    <div className="space-y-4">
      <div className="p-3.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 space-y-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-emerald-700 dark:text-emerald-400">
          <ShieldCheck className="w-4 h-4 shrink-0" />
          <span>{t('bannerTitle')}</span>
        </div>
        <p className="text-xs text-emerald-800 dark:text-emerald-300/90 leading-relaxed">{t('bannerBody')}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="p-3 rounded-lg border border-border bg-card/50 space-y-1">
          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <Hash className="w-3.5 h-3.5" />
            Layout hash
          </div>
          <div className="text-xs font-mono truncate">{baseContext.cache_control_hash}</div>
        </div>
        <div className="p-3 rounded-lg border border-border bg-card/50 space-y-1">
          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <Clock className="w-3.5 h-3.5" />
            Refreshed at turn
          </div>
          <div className="text-xs">{baseContext.refreshed_at_turn}</div>
        </div>
        <div className="p-3 rounded-lg border border-border bg-card/50 space-y-1">
          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <Layers className="w-3.5 h-3.5" />
            Compiled
          </div>
          <div className="text-xs">{new Date(baseContext.created_at).toLocaleString()}</div>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-2">
        <p className="text-[11px] font-medium text-foreground">Session summary snapshot</p>
        <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap">
          {baseContext.session_summary}
        </p>
        {baseContext.standing_peer_cards.length > 0 ? (
          <ul className="text-xs text-muted-foreground list-disc pl-4 space-y-1">
            {baseContext.standing_peer_cards.map((card) => (
              <li key={card}>{card}</li>
            ))}
          </ul>
        ) : null}
      </div>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={onForceRefresh}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-border hover:bg-muted/60 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          Recompile snapshot
        </button>
      </div>

      <div className="p-3.5 bg-card/40 rounded-lg border border-border space-y-2.5">
        <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
          <Info className="w-3.5 h-3.5 text-blue-500" />
          <span>{t('archTitle')}</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div className="p-3 rounded-md bg-rose-500/5 border border-rose-500/20 space-y-1.5">
            <div className="font-medium text-rose-600 dark:text-rose-400">{t('legacyTitle')}</div>
            <p className="text-muted-foreground text-[11px] leading-relaxed">{t('legacyBody')}</p>
          </div>

          <div className="p-3 rounded-md bg-emerald-500/5 border border-emerald-500/20 space-y-1.5">
            <div className="font-medium text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
              <span>{t('myrmTitle')}</span>
              <CheckCircle2 className="w-3.5 h-3.5" />
            </div>
            <p className="text-muted-foreground text-[11px] leading-relaxed">{t('myrmBody')}</p>
          </div>
        </div>
      </div>
    </div>
  );
};
