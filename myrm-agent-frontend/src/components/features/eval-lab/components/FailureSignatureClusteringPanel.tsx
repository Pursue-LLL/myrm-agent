'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Cpu,
  Layers,
  Sparkles,
  Wrench,
  Zap,
} from 'lucide-react';

export interface SignatureClusterItem {
  cluster_id: string;
  ci: string;
  qi: string;
  mi: string;
  failure_mode: string;
  verdict: 'addressable' | 'model_limit' | 'flake';
  case_count: number;
  affected_case_indices: number[];
  sample_messages: string[];
  remediation_hint: string;
  patch_proposal?: {
    op: string;
    path: string;
    value: unknown;
    rationale: string;
    target_component: string;
  } | null;
}

interface FailureSignatureClusteringPanelProps {
  clusters: SignatureClusterItem[];
  profileId?: string;
}

export function FailureSignatureClusteringPanel({ clusters, profileId }: FailureSignatureClusteringPanelProps) {
  const t = useTranslations('evalLab.clustering');
  const [expandedClusterId, setExpandedClusterId] = useState<string | null>(null);
  const [copiedPatchId, setCopiedPatchId] = useState<string | null>(null);

  if (!clusters || clusters.length === 0) {
    return null;
  }

  const toggleExpand = (id: string) => {
    setExpandedClusterId((prev) => (prev === id ? null : id));
  };

  const handleCopyPatch = (cluster: SignatureClusterItem) => {
    if (!cluster.patch_proposal) return;
    const patchJson = JSON.stringify([cluster.patch_proposal], null, 2);
    navigator.clipboard.writeText(patchJson);
    setCopiedPatchId(cluster.cluster_id);
    setTimeout(() => setCopiedPatchId(null), 2000);
  };

  const handleApplyNavigate = (cluster: SignatureClusterItem) => {
    if (typeof window === 'undefined') return;
    const targetAgentId = profileId || '';
    const searchParams = new URLSearchParams();
    if (targetAgentId) searchParams.set('agentId', targetAgentId);
    searchParams.set('tab', 'capabilities');
    if (cluster.patch_proposal) {
      searchParams.set('patchProposal', JSON.stringify([cluster.patch_proposal]));
    }
    window.location.href = `/settings#capabilities?${searchParams.toString()}`;
  };

  const getVerdictBadge = (verdict: string) => {
    switch (verdict) {
      case 'addressable':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
            <Sparkles className="w-3 h-3" />
            {t('verdictAddressable')}
          </span>
        );
      case 'model_limit':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-purple-500/10 text-purple-600 border border-purple-500/20">
            <Cpu className="w-3 h-3" />
            {t('verdictModelLimit')}
          </span>
        );
      case 'flake':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-amber-500/10 text-amber-600 border border-amber-500/20">
            <AlertTriangle className="w-3 h-3" />
            {t('verdictFlake')}
          </span>
        );
    }
  };

  return (
    <div className="border rounded-xl p-5 bg-card/60 shadow-sm space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-5 h-5 text-primary" />
          <h3 className="font-semibold text-base text-foreground tracking-tight">{t('panelTitle')}</h3>
          <span className="text-xs px-2 py-0.5 rounded-full bg-secondary font-medium text-muted-foreground">
            {clusters.length} {t('clustersFound')}
          </span>
        </div>
        <p className="text-xs text-muted-foreground hidden sm:block">{t('panelSubtitle')}</p>
      </div>

      <div className="space-y-3">
        {clusters.map((cluster) => {
          const isExpanded = expandedClusterId === cluster.cluster_id;
          const hasPatch = Boolean(cluster.patch_proposal);

          return (
            <div
              key={cluster.cluster_id}
              className="border rounded-lg bg-background/80 hover:border-primary/40 transition-colors overflow-hidden"
            >
              <div
                className="p-3.5 flex items-start justify-between gap-3 cursor-pointer select-none"
                onClick={() => toggleExpand(cluster.cluster_id)}
              >
                <div className="flex items-start gap-2.5 flex-1 min-w-0">
                  <button
                    type="button"
                    className="mt-0.5 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  </button>
                  <div className="space-y-1 flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      {getVerdictBadge(cluster.verdict)}
                      <span className="text-xs font-mono font-medium text-foreground truncate max-w-[280px] sm:max-w-md">
                        {cluster.ci}
                      </span>
                      <span className="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono">
                        qi: {cluster.qi}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground line-clamp-1">{cluster.remediation_hint}</p>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-xs font-medium text-destructive px-2 py-1 rounded bg-destructive/10">
                    {cluster.case_count} {t('cases')}
                  </span>
                </div>
              </div>

              {isExpanded && (
                <div className="px-4 pb-4 pt-1 border-t bg-muted/20 space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                    <div>
                      <span className="text-muted-foreground font-medium block mb-1">{t('affectedCases')}:</span>
                      <div className="flex flex-wrap gap-1">
                        {cluster.affected_case_indices.map((idx) => (
                          <span key={idx} className="px-1.5 py-0.5 rounded bg-muted font-mono text-[11px]">
                            Case #{idx + 1}
                          </span>
                        ))}
                      </div>
                    </div>

                    {cluster.sample_messages && cluster.sample_messages.length > 0 && (
                      <div>
                        <span className="text-muted-foreground font-medium block mb-1">{t('sampleQueries')}:</span>
                        <ul className="list-disc list-inside space-y-0.5 text-muted-foreground">
                          {cluster.sample_messages.map((msg, i) => (
                            <li key={i} className="truncate font-mono text-[11px]" title={msg}>
                              {msg}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>

                  {hasPatch && cluster.patch_proposal && (
                    <div className="mt-2 p-3 rounded-lg border bg-card/80 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                          <Zap className="w-3.5 h-3.5 text-amber-500" />
                          {t('patchProposalTitle')} (RFC-6902)
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleCopyPatch(cluster);
                            }}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs bg-muted hover:bg-muted/80 text-foreground transition-colors"
                          >
                            {copiedPatchId === cluster.cluster_id ? (
                              <>
                                <Check className="w-3 h-3 text-emerald-500" />
                                {t('copied')}
                              </>
                            ) : (
                              <>
                                <Copy className="w-3 h-3" />
                                {t('copyPatch')}
                              </>
                            )}
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleApplyNavigate(cluster);
                            }}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs bg-primary text-primary-foreground hover:bg-primary/90 font-medium transition-colors"
                          >
                            {t('reviewAndApply')}
                            <ArrowRight className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                      <pre className="p-2 rounded bg-muted/60 font-mono text-[11px] overflow-x-auto text-foreground">
                        {JSON.stringify([cluster.patch_proposal], null, 2)}
                      </pre>
                      <p className="text-[11px] text-muted-foreground">{cluster.patch_proposal.rationale}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default FailureSignatureClusteringPanel;
