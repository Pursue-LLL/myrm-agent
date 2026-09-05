/**
 * [INPUT]
 * - services/statistics::getSearchQuotas, getBrowserRuntimeSummary, resetSearchQuota, updateSearchQuotaLimit (POS: Runtime operational cost telemetry client)
 * - lucide-react (POS: Modern iconography)
 * - next-intl::useTranslations (POS: i18n hooks)
 *
 * [OUTPUT]
 * - RuntimeCostMeterCard: Modern high-fidelity search quota & browser compute telemetry dashboard
 *
 * [POS]
 * Operational runtime cost monitoring panel displaying free search tiers, browser compute minutes,
 * and outbound network transfer volume with dual-theme responsive UI, auto-healing reset, and full i18n.
 */

'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslations } from 'next-intl';
import {
  Search,
  Globe,
  RotateCcw,
  Sliders,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Activity,
  ShieldCheck,
} from 'lucide-react';
import {
  getSearchQuotas,
  getBrowserRuntimeSummary,
  resetSearchQuota,
  updateSearchQuotaLimit,
  type SearchQuotaItem,
  type BrowserRuntimeSummary,
} from '@/services/statistics';
import { cn } from '@/lib/utils/classnameUtils';

interface RuntimeCostMeterCardProps {
  className?: string;
}

export default function RuntimeCostMeterCard({ className }: RuntimeCostMeterCardProps) {
  const t = useTranslations('settings.usageStatistics.runtimeMeter');
  const [quotas, setQuotas] = useState<SearchQuotaItem[]>([]);
  const [browserSummary, setBrowserSummary] = useState<BrowserRuntimeSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [isResetting, setIsResetting] = useState<boolean>(false);
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [editLimitValue, setEditLimitValue] = useState<number>(1000);

  const loadData = useCallback(async () => {
    try {
      const [quotaData, browserData] = await Promise.all([
        getSearchQuotas().catch(() => []),
        getBrowserRuntimeSummary().catch(() => null),
      ]);
      setQuotas(quotaData);
      setBrowserSummary(browserData);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleReset = async (provider?: string) => {
    setIsResetting(true);
    try {
      await resetSearchQuota(provider);
      await loadData();
    } finally {
      setIsResetting(false);
    }
  };

  const handleSaveLimit = async () => {
    if (!editingProvider || editLimitValue <= 0) return;
    try {
      await updateSearchQuotaLimit(editingProvider, editLimitValue);
      setEditingProvider(null);
      await loadData();
    } catch (err) {
      console.error('Failed to update quota limit:', err);
    }
  };

  if (loading) {
    return (
      <div className={cn('p-6 rounded-2xl bg-card border border-border/50 animate-pulse space-y-4', className)}>
        <div className="h-6 w-48 bg-muted rounded-md" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="h-44 bg-muted/60 rounded-xl" />
          <div className="h-44 bg-muted/60 rounded-xl" />
        </div>
      </div>
    );
  }

  return (
    <div className={cn('p-6 rounded-2xl bg-card border border-border/50 shadow-sm space-y-6', className)}>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-border/40">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-primary" />
            <h3 className="text-base font-semibold text-foreground tracking-tight">
              {t('title')}
            </h3>
            <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-primary/10 text-primary border border-primary/20">
              {t('badge')}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            {t('description')}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => handleReset()}
            disabled={isResetting}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border bg-background hover:bg-accent hover:text-foreground transition-all disabled:opacity-50"
            title={t('resetTooltip')}
          >
            <RotateCcw className={cn('w-3.5 h-3.5', isResetting && 'animate-spin')} />
            {t('resetAll')}
          </button>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Search Quotas (7 Cols) */}
        <div className="lg:col-span-7 space-y-3">
          <div className="flex items-center justify-between text-xs font-medium text-foreground">
            <span className="flex items-center gap-1.5">
              <Search className="w-4 h-4 text-primary" />
              {t('searchPool')}
            </span>
            <span className="text-muted-foreground text-[11px]">{t('monthlyStats')}</span>
          </div>

          <div className="space-y-2.5">
            {quotas.map((item) => {
              const isDepleted = item.status === 'depleted';
              const isWarning = item.status === 'warning' || item.status === 'critical';

              return (
                <div
                  key={item.provider}
                  className={cn(
                    'p-3.5 rounded-xl border transition-all text-xs space-y-2',
                    isDepleted
                      ? 'bg-destructive/5 border-destructive/30'
                      : isWarning
                        ? 'bg-amber-500/5 border-amber-500/30'
                        : 'bg-background/80 border-border/40 hover:border-border/80',
                  )}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground uppercase tracking-wider text-[11px]">
                        {item.provider}
                      </span>
                      {!item.is_metered ? (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] rounded bg-secondary text-secondary-foreground font-normal">
                          <ShieldCheck className="w-3 h-3" />
                          {t('unlimited')}
                        </span>
                      ) : isDepleted ? (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] rounded bg-destructive/10 text-destructive font-medium">
                          <XCircle className="w-3 h-3" />
                          {t('depleted')}
                        </span>
                      ) : isWarning ? (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] rounded bg-amber-500/10 text-amber-500 font-medium">
                          <AlertTriangle className="w-3 h-3" />
                          {t('warning', { percent: item.percentage })}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] rounded bg-emerald-500/10 text-emerald-500 font-medium">
                          <CheckCircle2 className="w-3 h-3" />
                          {t('healthy')}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2 text-muted-foreground">
                      {item.is_metered ? (
                        <span>
                          <strong className="text-foreground">{item.used_count.toLocaleString()}</strong> /{' '}
                          {item.quota_limit.toLocaleString()} {t('callsUnit')}
                        </span>
                      ) : (
                        <span>
                          <strong className="text-foreground">{item.used_count.toLocaleString()}</strong> {t('callsUnit')}
                        </span>
                      )}

                      {item.is_metered && (
                        <button
                          onClick={() => {
                            setEditingProvider(item.provider);
                            setEditLimitValue(item.quota_limit);
                          }}
                          className="p-1 hover:bg-accent rounded text-muted-foreground hover:text-foreground transition-colors"
                          title={t('editLimitTitle')}
                        >
                          <Sliders className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Progress Bar for Metered Providers */}
                  {item.is_metered && (
                    <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                      <motion.div
                        className={cn(
                          'h-full rounded-full',
                          isDepleted
                            ? 'bg-destructive'
                            : item.percentage >= 95
                              ? 'bg-amber-600'
                              : item.percentage >= 80
                                ? 'bg-amber-500'
                                : 'bg-emerald-500',
                        )}
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.min(100, item.percentage)}%` }}
                        transition={{ duration: 0.5, ease: 'easeOut' }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Browser Compute & Network Summary (5 Cols) */}
        <div className="lg:col-span-5 space-y-3">
          <div className="flex items-center justify-between text-xs font-medium text-foreground">
            <span className="flex items-center gap-1.5">
              <Globe className="w-4 h-4 text-primary" />
              {t('browserTitle')}
            </span>
            <span className="text-muted-foreground text-[11px]">{t('monthlySummary')}</span>
          </div>

          <div className="p-4 rounded-xl border border-border/40 bg-background/80 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 rounded-lg bg-muted/40 space-y-1">
                <span className="text-[11px] text-muted-foreground">{t('activeComputeTime')}</span>
                <div className="text-lg font-bold text-foreground">
                  {browserSummary ? `${browserSummary.active_compute_minutes} 分钟` : '0 分钟'}
                </div>
                <span className="text-[10px] text-muted-foreground block">
                  {t('sessionsCount', { count: browserSummary?.session_count ?? 0 })}
                </span>
              </div>

              <div className="p-3 rounded-lg bg-muted/40 space-y-1">
                <span className="text-[11px] text-muted-foreground">{t('networkTransfer')}</span>
                <div className="text-lg font-bold text-foreground">
                  {browserSummary ? `${browserSummary.total_megabytes_transferred} MB` : '0 MB'}
                </div>
                <span className="text-[10px] text-muted-foreground block">
                  {t('requestsCount', { count: browserSummary?.total_requests ?? 0 })}
                </span>
              </div>
            </div>

            <div className="pt-2 border-t border-border/30 flex items-center justify-between text-xs">
              <span className="text-muted-foreground">{t('estimatedCost')}</span>
              <span className="font-semibold text-primary font-mono text-sm">
                ${browserSummary?.estimated_compute_cost_usd?.toFixed(3) ?? '0.000'}
              </span>
            </div>

            <div className="p-2.5 rounded-lg bg-primary/5 border border-primary/10 text-[11px] text-muted-foreground leading-relaxed flex items-start gap-2">
              <ShieldCheck className="w-4 h-4 text-primary shrink-0 mt-0.5" />
              <span>
                {t('watchdogTip')}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Edit Limit Dialog Modal */}
      {editingProvider && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-sm rounded-xl border border-border bg-card p-5 shadow-lg space-y-4">
            <div className="space-y-1">
              <h4 className="text-sm font-semibold text-foreground">{t('editLimitTitle')}</h4>
              <p className="text-xs text-muted-foreground">
                {t('editLimitDesc', { provider: editingProvider })}
              </p>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-medium text-foreground">{t('limitLabel')}</label>
              <input
                type="number"
                min={1}
                max={10000000}
                value={editLimitValue}
                onChange={(e) => setEditLimitValue(parseInt(e.target.value, 10) || 0)}
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setEditingProvider(null)}
                className="px-3 py-1.5 text-xs rounded-lg border border-border hover:bg-accent text-muted-foreground hover:text-foreground transition-all"
              >
                {t('cancel')}
              </button>
              <button
                onClick={handleSaveLimit}
                className="px-3 py-1.5 text-xs rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 font-medium transition-all"
              >
                {t('save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
