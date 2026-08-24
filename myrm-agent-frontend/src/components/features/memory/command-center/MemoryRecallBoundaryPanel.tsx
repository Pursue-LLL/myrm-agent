'use client';

import React, { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Shield, Database, Sparkles, AlertTriangle, CheckCircle, RefreshCw, Pin, Layers, Eye } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { getMemoryRecallBoundary, type MemoryRecallBoundaryData } from '@/services/memory/commandCenter';

interface MemoryRecallBoundaryPanelProps {
  agentId?: string;
  taskId?: string;
  className?: string;
}

export const MemoryRecallBoundaryPanel = memo<MemoryRecallBoundaryPanelProps>(({ agentId, taskId, className }) => {
  const t = useTranslations('memoryRecallBoundary');
  const [data, setData] = useState<MemoryRecallBoundaryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'candidates' | 'approved' | 'scopes' | 'partitions'>('candidates');

  const fetchBoundary = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getMemoryRecallBoundary(agentId, taskId);
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load recall boundary');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBoundary();
  }, [agentId, taskId]);

  if (loading && !data) {
    return (
      <div className={cn('p-6 rounded-xl border border-border/60 bg-card/40 animate-pulse space-y-4', className)}>
        <div className="h-6 w-1/3 bg-muted rounded" />
        <div className="h-20 bg-muted/60 rounded" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div
        className={cn(
          'p-6 rounded-xl border border-destructive/30 bg-destructive/5 text-destructive space-y-3',
          className,
        )}
      >
        <p className="text-sm font-medium">{error || 'Unable to load recall boundary'}</p>
        <button
          type="button"
          onClick={fetchBoundary}
          className="px-3 py-1.5 text-xs font-medium rounded-lg bg-destructive/10 hover:bg-destructive/20 transition-colors"
        >
          {t('refresh')}
        </button>
      </div>
    );
  }

  const budgetPercent = Math.min(100, Math.round((data.budget_chars_used / data.budget_chars_total) * 100));

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header & Budget Card */}
      <div className="p-5 rounded-xl border border-border/60 bg-card/60 backdrop-blur shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
              <Shield className="h-4 w-4 text-primary" />
              {t('title')}
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">{t('subtitle')}</p>
          </div>
          <button
            type="button"
            onClick={fetchBoundary}
            disabled={loading}
            className="self-start sm:self-auto flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border hover:bg-accent transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            {t('refresh')}
          </button>
        </div>

        {/* 6000 Char Budget Progress */}
        <div className="p-3.5 rounded-lg border border-border/40 bg-accent/15 space-y-2">
          <div className="flex items-center justify-between text-xs font-medium">
            <span className="text-muted-foreground flex items-center gap-1.5">
              <Layers className="h-3.5 w-3.5 text-primary" />
              {t('budgetTitle')}
            </span>
            <span className="font-mono text-foreground">
              {t('budgetUsed', { used: data.budget_chars_used, total: data.budget_chars_total })}
            </span>
          </div>
          <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
            <div
              className={cn(
                'h-full transition-all duration-300 rounded-full',
                data.budget_overflow_risk === 'overflow'
                  ? 'bg-destructive'
                  : data.budget_overflow_risk === 'approaching_limit'
                    ? 'bg-amber-500'
                    : 'bg-primary',
              )}
              style={{ width: `${budgetPercent}%` }}
            />
          </div>
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>
              {data.budget_overflow_risk === 'overflow' && (
                <span className="text-destructive font-medium flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  {t('budgetRiskOverflow')}
                </span>
              )}
              {data.budget_overflow_risk === 'approaching_limit' && (
                <span className="text-amber-500 font-medium flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  {t('budgetRiskApproaching')}
                </span>
              )}
              {data.budget_overflow_risk === 'safe' && (
                <span className="text-emerald-500 font-medium flex items-center gap-1">
                  <CheckCircle className="h-3 w-3" />
                  {t('budgetRiskSafe')}
                </span>
              )}
            </span>
            <span>
              {t('policyWrite')}: {data.write_policy}
            </span>
          </div>
        </div>
      </div>

      {/* Navigation Sub-Tabs */}
      <div className="flex gap-1 p-1 rounded-lg border border-border/60 bg-accent/20">
        <button
          type="button"
          onClick={() => setActiveTab('candidates')}
          className={cn(
            'flex-1 py-1.5 px-3 text-xs font-medium rounded-md transition-colors flex items-center justify-center gap-1.5',
            activeTab === 'candidates'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <Sparkles className="h-3.5 w-3.5 text-amber-500" />
          {t('candidateReviewTitle')} ({data.total_candidates})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('approved')}
          className={cn(
            'flex-1 py-1.5 px-3 text-xs font-medium rounded-md transition-colors flex items-center justify-center gap-1.5',
            activeTab === 'approved'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
          {t('approvedRecordsTitle')} ({data.total_approved})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('partitions')}
          className={cn(
            'flex-1 py-1.5 px-3 text-xs font-medium rounded-md transition-colors flex items-center justify-center gap-1.5',
            activeTab === 'partitions'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <Layers className="h-3.5 w-3.5 text-indigo-500" />
          {t('fourPartitionsTitle')}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('scopes')}
          className={cn(
            'flex-1 py-1.5 px-3 text-xs font-medium rounded-md transition-colors flex items-center justify-center gap-1.5',
            activeTab === 'scopes'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <Shield className="h-3.5 w-3.5 text-blue-500" />
          {t('scopeTitle')}
        </button>
      </div>

      {/* Tab 1: Candidate Review Gate */}
      {activeTab === 'candidates' && (
        <div className="space-y-3">
          {data.candidate_records.length === 0 ? (
            <div className="p-8 text-center rounded-xl border border-dashed border-border/70 bg-card/30">
              <Sparkles className="h-6 w-6 text-muted-foreground/60 mx-auto mb-2" />
              <p className="text-xs text-muted-foreground">{t('noCandidates')}</p>
            </div>
          ) : (
            <div className="grid gap-2.5">
              {data.candidate_records.map((cand) => (
                <div
                  key={cand.id}
                  className="p-3.5 rounded-lg border border-border/60 bg-card/60 hover:bg-accent/10 transition-colors space-y-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="px-2 py-0.5 text-[11px] font-medium rounded bg-amber-500/10 text-amber-500 border border-amber-500/20">
                      {cand.memory_type}
                    </span>
                    <span className="text-[11px] text-muted-foreground font-mono">
                      {t('confidence')}: {(cand.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="text-xs text-foreground/90 leading-relaxed font-sans">{cand.content_preview}</p>
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1 border-t border-border/30">
                    <span>
                      {t('source')}: {cand.source}
                    </span>
                    <span className="text-amber-500 font-medium">{t('candidateReviewDesc')}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Approved In-Scope Records */}
      {activeTab === 'approved' && (
        <div className="space-y-3">
          {data.approved_records.length === 0 ? (
            <div className="p-8 text-center rounded-xl border border-dashed border-border/70 bg-card/30">
              <Database className="h-6 w-6 text-muted-foreground/60 mx-auto mb-2" />
              <p className="text-xs text-muted-foreground">{t('noApproved')}</p>
            </div>
          ) : (
            <div className="grid gap-2.5">
              {data.approved_records.map((appr) => (
                <div
                  key={appr.id}
                  className="p-3.5 rounded-lg border border-border/60 bg-card/60 hover:bg-accent/10 transition-colors space-y-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5">
                      <span className="px-2 py-0.5 text-[11px] font-medium rounded bg-primary/10 text-primary border border-primary/20">
                        {appr.memory_type}
                      </span>
                      <span className="px-2 py-0.5 text-[11px] font-medium rounded bg-muted text-muted-foreground">
                        {appr.partition}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                      {appr.is_pinned && (
                        <span className="flex items-center gap-1 text-primary font-medium">
                          <Pin className="h-3 w-3" />
                          {t('pinned')}
                        </span>
                      )}
                      <span>{appr.char_count} chars</span>
                    </div>
                  </div>
                  <p className="text-xs text-foreground/90 leading-relaxed font-sans">{appr.content_preview}</p>
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1 border-t border-border/30">
                    <span>scope: {appr.namespace}</span>
                    <span className="font-mono">
                      imp: {appr.importance.toFixed(2)} · hits: {appr.access_count}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Four Partitions (Mise en place) */}
      {activeTab === 'partitions' && (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="p-4 rounded-xl border border-border/60 bg-card/60 space-y-2">
            <h4 className="text-xs font-semibold text-foreground flex items-center justify-between">
              <span>{t('partitionIdentity')}</span>
              <span className="text-primary font-mono">{data.partitions.identity_count} items</span>
            </h4>
            <p className="text-[11px] text-muted-foreground">User personality, long-term tone, and preferences.</p>
            <div className="text-[11px] font-mono text-muted-foreground/80">{data.partitions.identity_chars} chars</div>
          </div>

          <div className="p-4 rounded-xl border border-border/60 bg-card/60 space-y-2">
            <h4 className="text-xs font-semibold text-foreground flex items-center justify-between">
              <span>{t('partitionWorkingMemory')}</span>
              <span className="text-primary font-mono">{data.partitions.working_memory_count} items</span>
            </h4>
            <p className="text-[11px] text-muted-foreground">
              Task digests, active dialogue history, and running context.
            </p>
            <div className="text-[11px] font-mono text-muted-foreground/80">
              {data.partitions.working_memory_chars} chars
            </div>
          </div>

          <div className="p-4 rounded-xl border border-border/60 bg-card/60 space-y-2">
            <h4 className="text-xs font-semibold text-foreground flex items-center justify-between">
              <span>{t('partitionOperatingInstructions')}</span>
              <span className="text-primary font-mono">{data.partitions.operating_instructions_count} items</span>
            </h4>
            <p className="text-[11px] text-muted-foreground">
              Procedural rules, tool failure rules, and operational guidelines.
            </p>
            <div className="text-[11px] font-mono text-muted-foreground/80">
              {data.partitions.operating_instructions_chars} chars
            </div>
          </div>

          <div className="p-4 rounded-xl border border-border/60 bg-card/60 space-y-2">
            <h4 className="text-xs font-semibold text-foreground flex items-center justify-between">
              <span>{t('partitionRetrievableEvidence')}</span>
              <span className="text-primary font-mono">{data.partitions.retrievable_evidence_count} items</span>
            </h4>
            <p className="text-[11px] text-muted-foreground">
              Semantic facts, episodic experiences, and knowledge claims.
            </p>
            <div className="text-[11px] font-mono text-muted-foreground/80">
              {data.partitions.retrievable_evidence_chars} chars
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Task Scope Boundary */}
      {activeTab === 'scopes' && (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">{t('scopeDescription')}</p>
          <div className="grid gap-2.5">
            {data.read_scopes.map((sc) => (
              <div
                key={sc.level}
                className={cn(
                  'p-3.5 rounded-lg border transition-colors flex items-start justify-between gap-3',
                  sc.is_active
                    ? 'border-primary/40 bg-primary/5 text-foreground'
                    : 'border-border/40 bg-muted/20 opacity-60 text-muted-foreground',
                )}
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold">{sc.label}</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground">
                      {sc.namespace_pattern}
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground">{sc.description}</p>
                </div>
                <span
                  className={cn(
                    'px-2 py-0.5 text-[10px] font-medium rounded-full shrink-0',
                    sc.is_active
                      ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                      : 'bg-muted text-muted-foreground',
                  )}
                >
                  {sc.is_active ? 'Active Scope' : 'Restricted'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});

MemoryRecallBoundaryPanel.displayName = 'MemoryRecallBoundaryPanel';
