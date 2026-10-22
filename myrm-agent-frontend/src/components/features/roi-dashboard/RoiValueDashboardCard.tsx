/**
 * [INPUT]
 * - roiTypes: RoiValueDashboardCardProps, RoiTimeRange, RoiMetricsSnapshot
 * - roiService: fetchRoiDashboardMetrics, calculateLocalRoiFallback
 * - lucide-react: Clock, TrendingUp, DollarSign, Cpu, Sparkles, Award, ChevronRight
 * - next-intl: useTranslations
 *
 * [OUTPUT]
 * - RoiValueDashboardCard: HUD dashboard card for measurable agent ROI & hours saved
 *
 * [POS]
 * Core productivity ROI visualizer for AgentMeasurableRoiAndDailyTimeSavedHUD (Item 51 P0).
 * Strictly under 320 lines. Zero `any`.
 */

'use client';

import React, { memo, useState, useEffect, useCallback } from 'react';
import {
  Clock,
  TrendingUp,
  DollarSign,
  Cpu,
  Sparkles,
  Award,
  ShieldCheck,
  ChevronRight,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import type {
  RoiTimeRange,
  RoiMetricsSnapshot,
  RoiValueDashboardCardProps,
} from './roiTypes';
import { fetchRoiDashboardMetrics, calculateLocalRoiFallback } from './roiService';

const TIME_RANGES: { key: RoiTimeRange; labelKey: string }[] = [
  { key: 'today', labelKey: 'tabToday' },
  { key: 'week', labelKey: 'tabWeek' },
  { key: 'all_time', labelKey: 'tabAllTime' },
];

export const RoiValueDashboardCard: React.FC<RoiValueDashboardCardProps> = memo(({
  metrics: initialMetrics,
  timeRange: propTimeRange,
  onTimeRangeChange,
  onOpenDigest,
  className = '',
}) => {
  const t = useTranslations('roiDashboard');
  const [activeRange, setActiveRange] = useState<RoiTimeRange>(propTimeRange || 'today');
  const [data, setData] = useState<RoiMetricsSnapshot>(
    initialMetrics || calculateLocalRoiFallback(activeRange)
  );
  const [loading, setLoading] = useState(false);
  const [showDigestModal, setShowDigestModal] = useState(false);

  const loadMetrics = useCallback(async (range: RoiTimeRange) => {
    setLoading(true);
    try {
      const res = await fetchRoiDashboardMetrics(range);
      setData(res);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleRangeChange = useCallback(
    (range: RoiTimeRange) => {
      setActiveRange(range);
      if (onTimeRangeChange) {
        onTimeRangeChange(range);
      }
      void loadMetrics(range);
    },
    [onTimeRangeChange, loadMetrics]
  );

  useEffect(() => {
    if (initialMetrics) {
      setData(initialMetrics);
    }
  }, [initialMetrics]);

  const handleOpenDigest = useCallback(() => {
    if (onOpenDigest) {
      onOpenDigest();
    } else {
      setShowDigestModal(true);
    }
  }, [onOpenDigest]);

  const digest = data.recent_digest;

  return (
    <article
      data-testid="roi-dashboard-card-root"
      aria-label={t('cardTitle')}
      className={`rounded-2xl border border-slate-800 bg-slate-900/90 text-slate-100 p-5 shadow-xl backdrop-blur-md flex flex-col gap-5 ${className}`}
    >
      {/* Header with Title and Time Range Switcher */}
      <header className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="p-2 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <TrendingUp className="w-4 h-4" />
          </span>
          <div>
            <h3 className="text-sm font-bold tracking-tight text-slate-100">
              {t('cardTitle')}
            </h3>
            <p className="text-[11px] text-slate-400 font-medium">
              {t('cardSubtitle')}
            </p>
          </div>
        </div>

        {/* Range Segment Switcher */}
        <nav
          data-testid="roi-range-switcher"
          className="inline-flex items-center p-1 bg-slate-950/80 rounded-xl border border-slate-800 gap-1"
          aria-label={t('rangeAriaLabel')}
        >
          {TIME_RANGES.map((r) => {
            const isActive = activeRange === r.key;
            return (
              <button
                key={r.key}
                type="button"
                data-testid={`roi-range-btn-${r.key}`}
                onClick={() => {
                  handleRangeChange(r.key);
                }}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                  isActive
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                {t(r.labelKey)}
              </button>
            );
          })}
        </nav>
      </header>

      {/* Hero Metrics Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Hours Saved Billboard */}
        <div
          data-testid="hours-saved-billboard"
          className="p-4 rounded-xl bg-gradient-to-br from-slate-800/80 to-slate-950/80 border border-slate-700/60 flex flex-col justify-between"
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase text-slate-400 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-blue-400" />
              <span>{t('hoursSavedLabel')}</span>
            </span>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
              {loading ? '...' : `${data.total_hours_saved} ${t('hoursUnit')}`}
            </span>
          </div>

          <div className="mt-3 flex items-baseline gap-2">
            <span
              data-testid="total-hours-saved-val"
              className="text-3xl font-extrabold tracking-tight font-mono text-white"
            >
              {data.total_hours_saved}
            </span>
            <span className="text-sm font-semibold text-slate-400">{t('hoursUnit')}</span>
          </div>
          <p className="mt-1 text-[11px] text-slate-400">
            {t('hoursEquivalenceHint', { rate: data.hourly_rate_baseline_usd })}
          </p>
        </div>

        {/* ROI Multiplier & Economic Comparison */}
        <div
          data-testid="roi-economic-billboard"
          className="p-4 rounded-xl bg-gradient-to-br from-emerald-950/20 to-slate-950/80 border border-emerald-900/40 flex flex-col justify-between"
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase text-slate-400 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
              <span>{t('economicValueTitle')}</span>
            </span>
            <span
              data-testid="net-roi-badge"
              className="px-2 py-0.5 rounded-full text-[11px] font-mono font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
            >
              {data.net_roi_multiplier}x ROI
            </span>
          </div>

          <div className="mt-2 grid grid-cols-2 gap-2 pt-2 border-t border-slate-800">
            <div>
              <span className="text-[10px] text-slate-400 flex items-center gap-1">
                <DollarSign className="w-3 h-3 text-emerald-400" />
                <span>{t('humanValueLabel')}</span>
              </span>
              <p
                data-testid="monetary-saved-val"
                className="text-lg font-bold font-mono text-emerald-400 mt-0.5"
              >
                ${data.total_monetary_saved_usd}
              </p>
            </div>
            <div>
              <span className="text-[10px] text-slate-400 flex items-center gap-1">
                <Cpu className="w-3 h-3 text-blue-400" />
                <span>{t('tokenCostLabel')}</span>
              </span>
              <p
                data-testid="compute-cost-val"
                className="text-lg font-bold font-mono text-slate-200 mt-0.5"
              >
                ${data.total_compute_cost_usd}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Task Category Labor Savings Breakdown List */}
      <section className="flex flex-col gap-2.5">
        <h4 className="text-xs font-semibold text-slate-300 flex items-center justify-between">
          <span>{t('categoryBreakdownTitle')}</span>
          <span className="text-[10px] font-mono text-slate-500">
            {data.categories_breakdown.length} {t('categoriesCount')}
          </span>
        </h4>

        <div className="flex flex-col gap-1.5">
          {data.categories_breakdown.map((item) => (
            <div
              key={item.category_key}
              data-testid={`category-item-${item.category_key}`}
              className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/60 border border-slate-800/80 hover:border-slate-700 transition-colors text-xs"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" />
                <span className="font-medium text-slate-200 truncate">
                  {item.label_zh}
                </span>
                <span className="text-[10px] text-slate-500 font-mono">
                  ({t('tasksCount', { count: item.tasks_count })})
                </span>
              </div>

              <div className="flex items-center gap-3 shrink-0 font-mono">
                <span className="text-slate-300 font-semibold">
                  {item.hours_saved}h
                </span>
                <span className="text-emerald-400 font-medium">
                  +${item.value_usd}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Weekly Digest / Milestone Footer Trigger */}
      {digest && (
        <footer className="pt-2 border-t border-slate-800">
          <button
            type="button"
            data-testid="open-digest-btn"
            onClick={handleOpenDigest}
            className="w-full py-2 px-3 rounded-xl bg-slate-950/80 hover:bg-slate-800/70 border border-slate-800 flex items-center justify-between text-xs text-slate-300 transition-colors group"
          >
            <div className="flex items-center gap-2">
              <Award className="w-3.5 h-3.5 text-amber-400" />
              <span className="font-semibold text-slate-200">{digest.week_label}</span>
              <span className="text-slate-500">·</span>
              <span className="text-[11px] text-slate-400">
                {t('digestSummarySnippet', {
                  tasks: digest.total_tasks_completed,
                  hours: digest.total_hours_saved,
                })}
              </span>
            </div>
            <ChevronRight className="w-4 h-4 text-slate-500 group-hover:text-slate-300 group-hover:translate-x-0.5 transition-transform" />
          </button>
        </footer>
      )}

      {/* Local Digest Modal */}
      {showDigestModal && digest && (
        <dialog
          open
          data-testid="weekly-digest-modal"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-transparent border-none m-0 max-w-none max-h-none w-full h-full"
        >
          <button
            type="button"
            className="fixed inset-0 bg-black/60 backdrop-blur-2xs cursor-default"
            onClick={() => {
              setShowDigestModal(false);
            }}
            aria-label={t('closeDigest')}
          />
          <div className="relative z-10 w-full max-w-md bg-slate-900 border border-slate-700 rounded-2xl p-6 shadow-2xl flex flex-col gap-4 text-xs">
            <header className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <Award className="w-4 h-4 text-amber-400" />
                <h4 className="text-sm font-bold text-slate-100">
                  {digest.week_label} {t('weeklyDigestTitle')}
                </h4>
              </div>
              <button
                type="button"
                data-testid="close-digest-modal-btn"
                onClick={() => {
                  setShowDigestModal(false);
                }}
                className="text-slate-400 hover:text-slate-200 text-xs font-semibold px-2 py-1 rounded-md bg-slate-800"
              >
                {t('closeDigest')}
              </button>
            </header>

            <div className="grid grid-cols-2 gap-3 p-3 bg-slate-950 rounded-xl border border-slate-800 font-mono">
              <div>
                <span className="text-[10px] text-slate-400 uppercase font-semibold">{t('completedTasks')}</span>
                <p className="text-sm font-bold text-slate-100 mt-0.5">{digest.total_tasks_completed}</p>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 uppercase font-semibold">{t('netHoursSaved')}</span>
                <p className="text-sm font-bold text-emerald-400 mt-0.5">{digest.total_hours_saved}h</p>
              </div>
            </div>

            <div className="flex flex-col gap-2 p-3 bg-slate-950/60 rounded-xl border border-slate-800/80">
              <div className="flex items-center justify-between">
                <span className="text-slate-400 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-blue-400" />
                  <span>{t('topAgent')}</span>
                </span>
                <span className="font-semibold text-slate-200">{digest.top_performer_agent}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400 flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  <span>{t('preventedErrors')}</span>
                </span>
                <span className="font-semibold text-emerald-400 font-mono">+{digest.prevented_errors_count}</span>
              </div>
            </div>
          </div>
        </dialog>
      )}
    </article>
  );
});

RoiValueDashboardCard.displayName = 'RoiValueDashboardCard';
