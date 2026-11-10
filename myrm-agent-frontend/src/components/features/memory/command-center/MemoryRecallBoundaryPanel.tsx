'use client';

import React, { memo, useEffect, useEffectEvent, useState } from 'react';
import { useTranslations } from 'next-intl';
import { CheckCircle, Database, Inbox, Layers, Pin, RefreshCw, Shield, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  getMemoryRecallBoundary,
  type MemoryApprovedRecord,
  type MemoryFourPartitionSummary,
  type MemoryRecallBoundaryData,
  type MemoryRecallScopeLevel,
  type MemoryRecallWritePolicy,
} from '@/services/memory/commandCenter';

interface MemoryRecallBoundaryPanelProps {
  agentId?: string;
  taskId?: string;
  className?: string;
}

type BoundaryTab = 'candidates' | 'approved' | 'partitions' | 'scopes';
type PartitionId = MemoryApprovedRecord['partition'];

const PARTITION_IDS: readonly PartitionId[] = [
  'identity',
  'session_memory',
  'operating_instructions',
  'retrievable_evidence',
];

/** The count field and locale keys of each partition: one table feeds the partition cards and the per-record badge. */
const PARTITION_COPY: Record<
  PartitionId,
  { count: keyof MemoryFourPartitionSummary; title: string; description: string }
> = {
  identity: { count: 'identity_count', title: 'partitionIdentity', description: 'partitionIdentityDescription' },
  session_memory: {
    count: 'session_memory_count',
    title: 'partitionSessionMemory',
    description: 'partitionSessionMemoryDescription',
  },
  operating_instructions: {
    count: 'operating_instructions_count',
    title: 'partitionOperatingInstructions',
    description: 'partitionOperatingInstructionsDescription',
  },
  retrievable_evidence: {
    count: 'retrievable_evidence_count',
    title: 'partitionRetrievableEvidence',
    description: 'partitionRetrievableEvidenceDescription',
  },
};

/** Locale keys of each scope level: the server sends the level and its namespace pattern, the wording is localized here. */
const SCOPE_COPY: Record<MemoryRecallScopeLevel, { title: string; description: string }> = {
  global: { title: 'scopeGlobal', description: 'scopeGlobalDescription' },
  agent: { title: 'scopeAgent', description: 'scopeAgentDescription' },
  channel: { title: 'scopeChannel', description: 'scopeChannelDescription' },
  conversation: { title: 'scopeConversation', description: 'scopeConversationDescription' },
  task: { title: 'scopeTask', description: 'scopeTaskDescription' },
  shared: { title: 'scopeShared', description: 'scopeSharedDescription' },
};

const WRITE_POLICY_COPY: Record<MemoryRecallWritePolicy, string> = {
  inherit: 'writePolicyInherit',
  global: 'writePolicyGlobal',
  client: 'writePolicyClient',
  agent: 'writePolicyAgent',
  channel: 'writePolicyChannel',
  conversation: 'writePolicyConversation',
  task: 'writePolicyTask',
};

export const MemoryRecallBoundaryPanel = memo<MemoryRecallBoundaryPanelProps>(({ agentId, taskId, className }) => {
  const t = useTranslations('memoryRecallBoundary');
  const tMemory = useTranslations('memory');
  const [data, setData] = useState<MemoryRecallBoundaryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [activeTab, setActiveTab] = useState<BoundaryTab>('candidates');

  const fetchBoundary = async () => {
    setLoading(true);
    setFailed(false);
    try {
      setData(await getMemoryRecallBoundary(agentId, taskId));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  };

  const loadBoundary = useEffectEvent(() => fetchBoundary());
  useEffect(() => {
    loadBoundary();
  }, [agentId, taskId]);

  if (loading && !data) {
    return (
      <div className={cn('p-6 rounded-xl border border-border/60 bg-card/40 animate-pulse space-y-4', className)}>
        <div className="h-6 w-1/3 bg-muted rounded" />
        <div className="h-20 bg-muted/60 rounded" />
      </div>
    );
  }

  if (failed || !data) {
    return (
      <div
        className={cn(
          'p-6 rounded-xl border border-destructive/30 bg-destructive/5 text-destructive-text space-y-3',
          className,
        )}
      >
        <p className="text-sm font-medium">{t('loadError')}</p>
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

  const tabs: { id: BoundaryTab; icon: LucideIcon; iconClass: string; label: string }[] = [
    {
      id: 'candidates',
      icon: Inbox,
      iconClass: 'text-amber-500',
      label: `${t('candidateReviewTitle')} (${data.total_candidates})`,
    },
    {
      id: 'approved',
      icon: CheckCircle,
      iconClass: 'text-emerald-500',
      label: `${t('approvedRecordsTitle')} (${data.total_approved})`,
    },
    { id: 'partitions', icon: Layers, iconClass: 'text-indigo-500', label: t('fourPartitionsTitle') },
    { id: 'scopes', icon: Shield, iconClass: 'text-blue-500', label: t('scopeTitle') },
  ];

  return (
    <div className={cn('space-y-6', className)}>
      <div className="p-5 rounded-xl border border-border/60 bg-card/60 backdrop-blur flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Shield className="h-4 w-4 text-primary" />
            {t('title')}
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">{t('subtitle')}</p>
          <p className="text-[11px] text-muted-foreground mt-1.5">
            {t('policyWrite')}: {t(WRITE_POLICY_COPY[data.write_policy])}
          </p>
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

      <div
        role="tablist"
        className="grid grid-cols-2 sm:grid-cols-4 gap-1 p-1 rounded-xl border border-border/60 bg-accent/20"
      >
        {tabs.map(({ id, icon: Icon, iconClass, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={activeTab === id}
            onClick={() => setActiveTab(id)}
            className={cn(
              'py-1.5 px-3 text-xs font-medium rounded-lg transition-colors flex items-center justify-center gap-1.5',
              activeTab === id
                ? 'bg-background text-foreground ring-1 ring-border/60'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Icon className={cn('h-3.5 w-3.5 shrink-0', iconClass)} />
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'candidates' && (
        <div className="space-y-3">
          {data.candidate_records.length === 0 ? (
            <div className="p-8 text-center rounded-xl border border-dashed border-border/70 bg-card/30">
              <Inbox className="h-6 w-6 text-muted-foreground/60 mx-auto mb-2" />
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
                      {tMemory(`types.${cand.memory_type}`)}
                    </span>
                    {cand.confidence !== null && (
                      <span className="text-[11px] text-muted-foreground font-mono">
                        {t('confidence')}: {(cand.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-foreground/90 leading-relaxed font-sans">{cand.content_preview}</p>
                  <p className="text-[11px] text-amber-500 font-medium pt-1 border-t border-border/30">
                    {t('candidateReviewDesc')}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'approved' && (
        <div className="space-y-3">
          {data.approved_records.length === 0 ? (
            <div className="p-8 text-center rounded-xl border border-dashed border-border/70 bg-card/30">
              <Database className="h-6 w-6 text-muted-foreground/60 mx-auto mb-2" />
              <p className="text-xs text-muted-foreground">{t('noApproved')}</p>
            </div>
          ) : (
            <>
              {data.total_approved > data.approved_records.length && (
                <p className="text-xs text-muted-foreground">
                  {t('approvedSampleNote', { shown: data.approved_records.length, total: data.total_approved })}
                </p>
              )}
              <div className="grid gap-2.5">
                {data.approved_records.map((appr) => (
                  <div
                    key={appr.id}
                    className="p-3.5 rounded-lg border border-border/60 bg-card/60 hover:bg-accent/10 transition-colors space-y-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="px-2 py-0.5 text-[11px] font-medium rounded bg-primary/10 text-primary border border-primary/20">
                          {tMemory(`types.${appr.memory_type}`)}
                        </span>
                        <span className="px-2 py-0.5 text-[11px] font-medium rounded bg-muted text-muted-foreground">
                          {t(PARTITION_COPY[appr.partition].title)}
                        </span>
                      </div>
                      {appr.is_pinned && (
                        <span className="flex items-center gap-1 text-[11px] text-primary font-medium">
                          <Pin className="h-3 w-3" />
                          {t('pinned')}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-foreground/90 leading-relaxed font-sans">{appr.content_preview}</p>
                    <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground pt-1 border-t border-border/30">
                      <span>{t('approvedScope', { namespace: appr.namespace })}</span>
                      <span className="font-mono">
                        {appr.importance !== null && `${t('importance')} ${appr.importance.toFixed(2)} · `}
                        {t('recalledCount', { count: appr.access_count })}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {activeTab === 'partitions' && (
        <div className="grid gap-3 sm:grid-cols-2">
          {PARTITION_IDS.map((id) => {
            const copy = PARTITION_COPY[id];
            return (
              <div key={id} className="p-4 rounded-xl border border-border/60 bg-card/60 space-y-2">
                <h4 className="text-xs font-semibold text-foreground flex items-center justify-between gap-2">
                  <span>{t(copy.title)}</span>
                  <span className="text-primary font-mono shrink-0">
                    {t('partitionCount', { count: data.partitions[copy.count] })}
                  </span>
                </h4>
                <p className="text-[11px] text-muted-foreground">{t(copy.description)}</p>
              </div>
            );
          })}
        </div>
      )}

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
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold">{t(SCOPE_COPY[sc.level].title)}</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground">
                      {sc.namespace_pattern}
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground">{t(SCOPE_COPY[sc.level].description)}</p>
                </div>
                <span
                  className={cn(
                    'px-2 py-0.5 text-[10px] font-medium rounded-full shrink-0',
                    sc.is_active
                      ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                      : 'bg-muted text-muted-foreground',
                  )}
                >
                  {sc.is_active ? t('scopeActive') : t('scopeRestricted')}
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
