/**
 * [INPUT]
 * - pairedSignificance: Record<string, PairedSignificanceData> from matrix report
 * - profileIds: string[]
 * - getProfileLabel: (pid: string) => string
 * - onFilterCases?: (indices: number[] | null, filterType: 'regression' | 'improved' | null) => void
 * - activeFilterType?: 'regression' | 'improved' | null
 *
 * [OUTPUT]
 * - React component rendering paired McNemar test, Bootstrap 95% CI, Meta-Harness 4-Mechanism plateau diagnosis, and interactive case drill-down
 *
 * [POS]
 * - Frontend visual chip & honest education component in Eval Lab Matrix view
 */

import React, { useState, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  Scale,
  TrendingUp,
  TrendingDown,
  Zap,
  Minus,
  AlertTriangle,
  Filter,
  CheckCircle2,
  XCircle,
  HelpCircle,
  ShieldCheck,
  ShieldAlert,
} from 'lucide-react';
import type {
  SignificanceVerdict,
  PlateauMechanism,
  McNemarData,
  BootstrapCIData,
  PlateauData,
  ContinuousMetricsDelta,
  PairedSignificanceData,
} from './pairedSignificanceTypes';

export type {
  SignificanceVerdict,
  PlateauMechanism,
  McNemarData,
  BootstrapCIData,
  PlateauData,
  ContinuousMetricsDelta,
  PairedSignificanceData,
};

interface Props {
  pairedSignificance: Record<string, PairedSignificanceData>;
  profileIds: string[];
  getProfileLabel: (pid: string) => string;
  onFilterCases?: (indices: number[] | null, filterType: 'regression' | 'improved' | null) => void;
  activeFilterType?: 'regression' | 'improved' | null;
}

export default function PairedSignificancePanel({
  pairedSignificance,
  profileIds,
  getProfileLabel,
  onFilterCases,
  activeFilterType,
}: Props) {
  const t = useTranslations('evalLab.significance');
  const pairKeys = useMemo(() => Object.keys(pairedSignificance), [pairedSignificance]);

  const [activePairKey, setActivePairKey] = useState<string>(() => pairKeys[0] || '');

  const activeData: PairedSignificanceData | undefined =
    pairedSignificance[activePairKey] || (pairKeys.length > 0 ? pairedSignificance[pairKeys[0]] : undefined);

  if (!activeData || pairKeys.length === 0 || profileIds.length < 2) {
    return null;
  }

  const {
    base_id,
    candidate_id,
    base_pass_rate,
    candidate_pass_rate,
    delta_pass_rate,
    mcnemar,
    bootstrap_ci,
    plateau,
    verdict,
    regression_case_indices,
    improved_case_indices,
    continuous_delta,
  } = activeData;

  const getVerdictStyle = (v: SignificanceVerdict) => {
    switch (v) {
      case 'significant_improvement':
        return {
          badgeBg: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
          border: 'border-emerald-500/30 bg-emerald-500/5',
          icon: <TrendingUp className="w-5 h-5 text-emerald-500" />,
          label: t('verdict.significantImprovement'),
          desc: t('verdict.significantImprovementDesc'),
        };
      case 'significant_regression':
        return {
          badgeBg: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20',
          border: 'border-rose-500/30 bg-rose-500/5',
          icon: <TrendingDown className="w-5 h-5 text-rose-500" />,
          label: t('verdict.significantRegression'),
          desc: t('verdict.significantRegressionDesc'),
        };
      case 'efficiency_breakthrough':
        return {
          badgeBg: 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20',
          border: 'border-purple-500/30 bg-purple-500/5',
          icon: <Zap className="w-5 h-5 text-purple-500" />,
          label: t('verdict.efficiencyBreakthrough'),
          desc: t('verdict.efficiencyBreakthroughDesc'),
        };
      case 'insufficient_discordance':
        return {
          badgeBg: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
          border: 'border-amber-500/30 bg-amber-500/5',
          icon: <AlertTriangle className="w-5 h-5 text-amber-500" />,
          label: t('verdict.insufficientDiscordance'),
          desc: t('verdict.insufficientDiscordanceDesc'),
        };
      case 'no_significant_difference':
      default:
        return {
          badgeBg: 'bg-muted text-muted-foreground border-border',
          border: 'border-border bg-muted/20',
          icon: <Minus className="w-5 h-5 text-muted-foreground" />,
          label: t('verdict.noSignificantDifference'),
          desc: t('verdict.noSignificantDifferenceDesc'),
        };
    }
  };

  const verdictStyle = getVerdictStyle(verdict);

  const formatPercent = (val: number) => {
    const sign = val > 0 ? '+' : '';
    return `${sign}${(val * 100).toFixed(1)}%`;
  };

  const formatRatio = (val: number) => {
    const sign = val > 0 ? '+' : '';
    return `${sign}${(val * 100).toFixed(1)}%`;
  };

  return (
    <div
      data-testid="paired-significance-panel"
      className="p-4 sm:p-5 rounded-xl border bg-gradient-to-br from-card to-muted/20 shadow-sm space-y-4"
    >
      {/* Header & Pair switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <Scale className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold flex items-center gap-2 text-foreground">
              {t('panelTitle')}
              <span className="text-[11px] font-normal text-muted-foreground font-mono">
                McNemar · Bootstrap 95% CI
              </span>
            </h3>
            <p className="text-xs text-muted-foreground">{t('panelSubtitle')}</p>
          </div>
        </div>

        {/* Pair Pills */}
        {pairKeys.length > 1 && (
          <div className="flex items-center gap-1.5 overflow-x-auto py-1 max-w-full">
            {pairKeys.map((key) => {
              const pair = pairedSignificance[key];
              if (!pair) return null;
              const isSelected = (activePairKey || pairKeys[0]) === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => {
                    setActivePairKey(key);
                    onFilterCases?.(null, null);
                  }}
                  className={`px-2.5 py-1 text-xs rounded-full font-mono font-medium transition-all shrink-0 cursor-pointer ${
                    isSelected
                      ? 'bg-primary text-primary-foreground shadow-xs'
                      : 'bg-muted/60 hover:bg-muted text-muted-foreground'
                  }`}
                >
                  {getProfileLabel(pair.base_id)} ➔ {getProfileLabel(pair.candidate_id)}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Main Verdict Card */}
      <div className={`p-4 rounded-xl border ${verdictStyle.border} flex flex-col md:flex-row md:items-center justify-between gap-4 transition-all`}>
        <div className="flex items-start gap-3.5">
          <div className="p-2.5 rounded-xl bg-background/80 shadow-xs mt-0.5 shrink-0 border border-border/50">
            {verdictStyle.icon}
          </div>
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${verdictStyle.badgeBg}`}>
                {verdictStyle.label}
              </span>
              <span className="text-xs font-mono font-medium text-foreground">
                {getProfileLabel(base_id)} ({(base_pass_rate * 100).toFixed(1)}%) ➔{' '}
                {getProfileLabel(candidate_id)} ({(candidate_pass_rate * 100).toFixed(1)}%)
              </span>
              <span
                className={`text-xs font-mono font-bold ${
                  delta_pass_rate > 0
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : delta_pass_rate < 0
                      ? 'text-rose-600 dark:text-rose-400'
                      : 'text-muted-foreground'
                }`}
              >
                {formatPercent(delta_pass_rate)}
              </span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {verdictStyle.desc}
            </p>
          </div>
        </div>

        {/* Quick metrics column */}
        <div className="flex items-center gap-4 text-xs font-mono shrink-0 pl-12 md:pl-0">
          <div className="flex flex-col items-start md:items-end">
            <span className="text-[11px] font-sans text-muted-foreground">{t('mcnemarPVal')}</span>
            <span
              className={`font-semibold ${
                mcnemar.is_significant
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-muted-foreground'
              }`}
            >
              p = {mcnemar.p_value.toFixed(4)}
            </span>
          </div>
          <div className="flex flex-col items-start md:items-end">
            <span className="text-[11px] font-sans text-muted-foreground">{t('bootstrapCI')}</span>
            <span
              className={`font-semibold ${
                bootstrap_ci.crosses_zero
                  ? 'text-amber-600 dark:text-amber-400'
                  : 'text-foreground'
              }`}
            >
              [{formatPercent(bootstrap_ci.ci_lower)}, {formatPercent(bootstrap_ci.ci_upper)}]
            </span>
          </div>
        </div>
      </div>

      {/* Grid: Statistical Details & Plateau Diagnosis */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Box 1: Detailed Statistical Metrics */}
        <div className="p-4 rounded-xl border bg-card/60 space-y-3">
          <div className="flex items-center justify-between text-xs font-semibold text-foreground border-b pb-2">
            <span className="flex items-center gap-1.5">
              <Scale className="w-3.5 h-3.5 text-primary" />
              {t('contingencyTableTitle')}
            </span>
            <span className="font-mono text-[11px] text-muted-foreground">
              {mcnemar.test_type === 'exact_binomial'
                ? t('testExactBinomial')
                : mcnemar.test_type === 'edwards_continuity_chi2'
                  ? t('testEdwardsChi2')
                  : t('testNoDiscordant')}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div className="p-2 rounded-lg bg-muted/40 border border-border/40">
              <span className="text-[11px] text-muted-foreground block">{t('bothPass')}</span>
              <span className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                {mcnemar.contingency_table.both_pass}
              </span>
            </div>
            <div className="p-2 rounded-lg bg-muted/40 border border-border/40">
              <span className="text-[11px] text-muted-foreground block">{t('candOnlyImproved')}</span>
              <span className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                +{mcnemar.contingency_table.cand_only}
              </span>
            </div>
            <div className="p-2 rounded-lg bg-muted/40 border border-border/40">
              <span className="text-[11px] text-muted-foreground block">{t('baseOnlyRegressed')}</span>
              <span className="text-sm font-semibold text-rose-600 dark:text-rose-400">
                -{mcnemar.contingency_table.base_only}
              </span>
            </div>
            <div className="p-2 rounded-lg bg-muted/40 border border-border/40">
              <span className="text-[11px] text-muted-foreground block">{t('bothFail')}</span>
              <span className="text-sm font-semibold text-muted-foreground">
                {mcnemar.contingency_table.both_fail}
              </span>
            </div>
          </div>

          {/* Continuous metrics if available */}
          {continuous_delta && (
            <div className="pt-2 border-t text-xs space-y-1 font-mono">
              <div className="text-[11px] font-sans text-muted-foreground font-medium mb-1">
                {t('continuousDeltaTitle')} (95% CI)
              </div>
              <div className="flex items-center justify-between text-muted-foreground">
                <span>{t('tokenChange')}</span>
                <span className="text-foreground">
                  {formatRatio(continuous_delta.token_diff_pct)} [{formatRatio(continuous_delta.token_ci_95[0])},{' '}
                  {formatRatio(continuous_delta.token_ci_95[1])}]
                </span>
              </div>
              <div className="flex items-center justify-between text-muted-foreground">
                <span>{t('costChange')}</span>
                <span className="text-foreground">
                  {formatRatio(continuous_delta.cost_diff_pct)} [{formatRatio(continuous_delta.cost_ci_95[0])},{' '}
                  {formatRatio(continuous_delta.cost_ci_95[1])}]
                </span>
              </div>
              <div className="flex items-center justify-between text-muted-foreground">
                <span>{t('latencyChange')}</span>
                <span className="text-foreground">
                  {formatRatio(continuous_delta.latency_diff_pct)} [{formatRatio(continuous_delta.latency_ci_95[0])},{' '}
                  {formatRatio(continuous_delta.latency_ci_95[1])}]
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Box 2: Plateau Diagnosis & Honest Education */}
        <div className="p-4 rounded-xl border bg-card/60 space-y-3 flex flex-col justify-between">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-semibold text-foreground border-b pb-2">
              <span className="flex items-center gap-1.5">
                {plateau.mechanism === 'none' ? (
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
                ) : (
                  <ShieldAlert className="w-3.5 h-3.5 text-amber-500" />
                )}
                {t('plateauDiagnosisTitle')}
              </span>
              <span
                className={`px-2 py-0.5 rounded text-[11px] font-medium ${
                  plateau.mechanism === 'none'
                    ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                    : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                }`}
              >
                {t(`plateau.mechanism.${plateau.mechanism}`)}
              </span>
            </div>

            <div className="text-xs space-y-1.5">
              <p className="font-medium text-foreground">{plateau.title}</p>
              <p className="text-muted-foreground leading-relaxed">{plateau.explanation}</p>
              <div className="p-2 rounded-lg bg-muted/30 border border-border/30 text-xs">
                <span className="font-semibold text-foreground block mb-0.5">{t('honestRecommendation')}:</span>
                <span className="text-muted-foreground">{plateau.recommendation}</span>
              </div>
            </div>
          </div>

          {/* Actionable action badge */}
          {plateau.suggested_action && plateau.suggested_action !== 'none' && (
            <div className="pt-2 border-t flex items-center justify-between text-xs">
              <span className="text-[11px] text-muted-foreground">{t('suggestedAction')}:</span>
              <span className="px-2 py-0.5 rounded-md bg-primary/10 text-primary font-mono font-medium text-[11px]">
                {t(`suggestedActionMap.${plateau.suggested_action}`)}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Case Drill-down Toolbar */}
      {onFilterCases && (regression_case_indices.length > 0 || improved_case_indices.length > 0) && (
        <div className="flex flex-wrap items-center justify-between gap-2.5 pt-2 border-t text-xs">
          <div className="flex items-center gap-2">
            <Filter className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">{t('caseDrilldownTitle')}:</span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {regression_case_indices.length > 0 && (
              <button
                type="button"
                onClick={() =>
                  onFilterCases(
                    activeFilterType === 'regression' ? null : regression_case_indices,
                    activeFilterType === 'regression' ? null : 'regression'
                  )
                }
                className={`px-2.5 py-1 rounded-lg font-medium transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeFilterType === 'regression'
                    ? 'bg-rose-500 text-white shadow-xs'
                    : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 hover:bg-rose-500/20 border border-rose-500/20'
                }`}
              >
                <XCircle className="w-3.5 h-3.5" />
                {t('filterRegressionCases')} ({regression_case_indices.length})
              </button>
            )}

            {improved_case_indices.length > 0 && (
              <button
                type="button"
                onClick={() =>
                  onFilterCases(
                    activeFilterType === 'improved' ? null : improved_case_indices,
                    activeFilterType === 'improved' ? null : 'improved'
                  )
                }
                className={`px-2.5 py-1 rounded-lg font-medium transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeFilterType === 'improved'
                    ? 'bg-emerald-500 text-white shadow-xs'
                    : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/20'
                }`}
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                {t('filterImprovedCases')} ({improved_case_indices.length})
              </button>
            )}

            {activeFilterType && (
              <button
                type="button"
                onClick={() => onFilterCases(null, null)}
                className="px-2.5 py-1 rounded-lg bg-muted text-muted-foreground hover:text-foreground font-medium transition-all cursor-pointer"
              >
                {t('clearFilter')}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
