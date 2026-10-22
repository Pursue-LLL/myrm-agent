/**
 * [INPUT]
 * - roiTypes: HighYieldRoutineCatalogProps, HighYieldRoutineSpec
 * - roiService: fetchHighYieldRoutines
 * - lucide-react: Zap, Clock, TrendingUp, Play, Sparkles
 * - next-intl: useTranslations
 *
 * [OUTPUT]
 * - HighYieldRoutineCatalog: Pre-packaged high-yield out-of-the-box workflows
 *
 * [POS]
 * Out-of-the-box routine catalog for AgentMeasurableRoiAndDailyTimeSavedHUD (Item 51 P0).
 * Strictly under 240 lines. Zero `any`.
 */

'use client';

import React, { memo, useState, useEffect, useCallback } from 'react';
import {
  Zap,
  Clock,
  TrendingUp,
  Play,
  Sparkles,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import type {
  HighYieldRoutineSpec,
  HighYieldRoutineCatalogProps,
} from './roiTypes';
import { fetchHighYieldRoutines } from './roiService';

export const HighYieldRoutineCatalog: React.FC<HighYieldRoutineCatalogProps> = memo(({
  routines: initialRoutines,
  onTriggerRoutine,
  className = '',
}) => {
  const t = useTranslations('roiDashboard');
  const [routines, setRoutines] = useState<HighYieldRoutineSpec[]>(initialRoutines || []);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (initialRoutines && initialRoutines.length > 0) {
      setRoutines(initialRoutines);
      return;
    }

    let isMounted = true;
    setLoading(true);

    void fetchHighYieldRoutines()
      .then((data) => {
        if (isMounted) {
          setRoutines(data);
        }
      })
      .finally(() => {
        if (isMounted) {
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [initialRoutines]);

  const handleRun = useCallback(
    (routine: HighYieldRoutineSpec) => {
      if (onTriggerRoutine) {
        onTriggerRoutine(routine);
      }
    },
    [onTriggerRoutine]
  );

  return (
    <section
      data-testid="high-yield-routine-catalog-root"
      aria-label={t('routineCatalogTitle')}
      className={`rounded-2xl border border-slate-800 bg-slate-900/90 text-slate-100 p-5 shadow-xl backdrop-blur-md flex flex-col gap-4 ${className}`}
    >
      {/* Header */}
      <header className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="p-2 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
            <Zap className="w-4 h-4" />
          </span>
          <div>
            <h3 className="text-sm font-bold tracking-tight text-slate-100 flex items-center gap-1.5">
              <span>{t('routineCatalogTitle')}</span>
              <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold bg-purple-500/20 text-purple-300">
                {routines.length}
              </span>
            </h3>
            <p className="text-[11px] text-slate-400 font-medium">
              {t('routineCatalogSubtitle')}
            </p>
          </div>
        </div>
      </header>

      {/* Routine Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        {loading && routines.length === 0 ? (
          <div className="col-span-2 py-8 text-center text-xs text-slate-500">
            {t('loadingRoutines')}
          </div>
        ) : (
          routines.map((item) => (
            <article
              key={item.routine_id}
              data-testid={`routine-card-${item.routine_id}`}
              className="p-4 rounded-xl bg-slate-950/70 border border-slate-800/80 hover:border-slate-700 transition-all flex flex-col justify-between gap-3 group"
            >
              <div className="flex flex-col gap-1.5">
                <div className="flex items-start justify-between gap-2">
                  <h4 className="text-xs font-semibold text-slate-200 group-hover:text-blue-300 transition-colors line-clamp-1">
                    {item.title_zh}
                  </h4>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 shrink-0">
                    {item.typical_roi_multiplier}x ROI
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                  {item.description_zh}
                </p>
              </div>

              <div className="pt-2 border-t border-slate-850 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-[10px] text-slate-400 font-mono">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3 text-blue-400" />
                    <span>~{item.estimated_minutes_saved}m</span>
                  </span>
                  <span>·</span>
                  <span className="flex items-center gap-1">
                    <Sparkles className="w-3 h-3 text-purple-400" />
                    <span className="capitalize">{item.category}</span>
                  </span>
                </div>

                <button
                  type="button"
                  data-testid={`trigger-routine-btn-${item.routine_id}`}
                  onClick={() => {
                    handleRun(item);
                  }}
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-blue-600/90 hover:bg-blue-600 text-white text-xs font-semibold shadow-xs transition-colors"
                >
                  <Play className="w-3 h-3 fill-current" />
                  <span>{t('runRoutineBtn')}</span>
                </button>
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
});

HighYieldRoutineCatalog.displayName = 'HighYieldRoutineCatalog';
