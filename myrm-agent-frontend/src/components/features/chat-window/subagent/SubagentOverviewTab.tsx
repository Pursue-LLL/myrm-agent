'use client';

/**
 * [INPUT]
 * @/store/chat/useSubagentStore::SubagentNode (POS: Multi-agent execution tree and stream state store)
 * ./SubagentErrorNotice::SubagentErrorNotice (POS: Failure and needs-review panel for a subagent node)
 *
 * [OUTPUT]
 * SubagentOverviewTab: Overview tab of the subagent detail drawer (handover report, failure notice, verification verdict, task spec, metadata).
 *
 * [POS]
 * Subagent inspection surface. Read-only summary of one node; copy actions are local to this tab.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import { Copy, FileCheck, Link as LinkIcon, Package, ShieldAlert, ShieldCheck, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';
import type { SubagentNode } from '@/store/chat/useSubagentStore';
import { SubagentErrorNotice } from './SubagentErrorNotice';

const CONFIDENCE_LABEL_KEYS: Record<string, 'detailConfidenceHigh' | 'detailConfidenceMedium' | 'detailConfidenceLow'> =
  {
    high: 'detailConfidenceHigh',
    medium: 'detailConfidenceMedium',
    low: 'detailConfidenceLow',
  };

interface SubagentOverviewTabProps {
  node: SubagentNode;
}

export const SubagentOverviewTab: React.FC<SubagentOverviewTabProps> = ({ node }) => {
  const t = useTranslations('subagentDashboard');

  const handleCopy = (text: string, copiedMessage: string) => {
    navigator.clipboard.writeText(text);
    toast.success(copiedMessage);
  };

  return (
    <div className="space-y-4">
      {node.handover_state && (
        <div className="p-3.5 rounded-lg border bg-blue-50/20 dark:bg-blue-950/20 border-blue-200/60 dark:border-blue-900/40 text-xs space-y-3">
          <div className="flex items-center justify-between font-bold text-blue-950 dark:text-blue-200">
            <div className="flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-blue-600 dark:text-blue-400" />
              <span>{t('detailHandoverTitle')}</span>
            </div>
            <Badge variant="outline" className="text-[10px] font-mono border-blue-300 dark:border-blue-800">
              {t('detailHandoverBadge')}
            </Badge>
          </div>

          {node.handover_state.summary && (
            <div className="bg-background/80 dark:bg-background/40 p-2.5 rounded-md border border-border/50">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                {t('detailExecutiveSummary')}
              </span>
              <p className="text-[12px] leading-relaxed text-foreground whitespace-pre-wrap">
                {node.handover_state.summary}
              </p>
            </div>
          )}

          {node.handover_state.findings && node.handover_state.findings.length > 0 && (
            <div>
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1.5">
                {t('detailKeyFindings', { count: node.handover_state.findings.length })}
              </span>
              <div className="space-y-1.5">
                {node.handover_state.findings.map((f, i) => {
                  const conf = (f.confidence || 'high').toLowerCase();
                  const confLabelKey = CONFIDENCE_LABEL_KEYS[conf];
                  const confColor =
                    conf === 'high'
                      ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20'
                      : conf === 'medium'
                        ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20'
                        : 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20';

                  return (
                    <div
                      key={i}
                      className="p-2 rounded-md border bg-background/60 dark:bg-background/30 text-[11px] flex flex-col gap-1"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="font-medium text-foreground">{f.finding}</span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[9px] uppercase font-mono font-bold border shrink-0 ${confColor}`}
                        >
                          {confLabelKey ? t(confLabelKey) : f.confidence}
                        </span>
                      </div>
                      {f.evidence && (
                        <div className="flex items-center gap-1 font-mono text-[10px] text-muted-foreground bg-muted/40 px-1.5 py-0.5 rounded">
                          <FileCheck className="w-3 h-3 text-muted-foreground shrink-0" />
                          <span className="truncate">{f.evidence}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {((node.handover_state.artifact_refs && node.handover_state.artifact_refs.length > 0) ||
            (node.handover_state.citations && node.handover_state.citations.length > 0)) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
              {node.handover_state.artifact_refs && node.handover_state.artifact_refs.length > 0 && (
                <div className="p-2 rounded-md border bg-background/50 dark:bg-background/20">
                  <span className="text-[10px] font-semibold text-muted-foreground flex items-center gap-1 mb-1">
                    <Package className="w-3 h-3 text-primary" /> {t('detailArtifacts')}
                  </span>
                  <div className="space-y-1">
                    {node.handover_state.artifact_refs.map((ref, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between gap-1 font-mono text-[10px] text-foreground bg-muted/30 px-1.5 py-0.5 rounded group"
                      >
                        <span className="truncate">{ref}</span>
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label={t('detailCopy')}
                          onClick={() => handleCopy(ref, t('detailCopiedArtifactPath'))}
                          className="h-5 px-1 opacity-60 group-hover:opacity-100"
                        >
                          <Copy className="w-2.5 h-2.5" />
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {node.handover_state.citations && node.handover_state.citations.length > 0 && (
                <div className="p-2 rounded-md border bg-background/50 dark:bg-background/20">
                  <span className="text-[10px] font-semibold text-muted-foreground flex items-center gap-1 mb-1">
                    <LinkIcon className="w-3 h-3 text-primary" /> {t('detailCitations')}
                  </span>
                  <div className="space-y-1">
                    {node.handover_state.citations.map((cite, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between gap-1 font-mono text-[10px] text-foreground bg-muted/30 px-1.5 py-0.5 rounded group"
                      >
                        <span className="truncate">{cite}</span>
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label={t('detailCopy')}
                          onClick={() => handleCopy(cite, t('detailCopiedCitationUrl'))}
                          className="h-5 px-1 opacity-60 group-hover:opacity-100"
                        >
                          <Copy className="w-2.5 h-2.5" />
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {node.handover_state.task_completed && node.handover_state.task_completed.length > 0 && (
            <div>
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                {t('detailCompletedChecklist')}
              </span>
              <ul className="space-y-0.5 list-disc list-inside text-[11px] text-muted-foreground">
                {node.handover_state.task_completed.map((task, i) => (
                  <li key={i} className="text-foreground">
                    {task}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <SubagentErrorNotice node={node} />

      {node.verification && (
        <div
          className={`p-3 rounded-lg border text-xs ${
            node.verification.passed
              ? 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-900/50 text-green-700 dark:text-green-300'
              : 'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-900/50 text-red-700 dark:text-red-300'
          }`}
        >
          <div className="flex items-center justify-between font-bold mb-1">
            <div className="flex items-center gap-1.5">
              {node.verification.passed ? <ShieldCheck className="w-4 h-4" /> : <ShieldAlert className="w-4 h-4" />}
              <span>{node.verification.passed ? t('detailVerificationPassed') : t('detailVerificationFailed')}</span>
            </div>
            <span>
              {t('detailVerificationRounds', {
                rounds: node.verification.rounds,
                maxRounds: node.verification.max_rounds,
              })}
            </span>
          </div>
          {node.verification.findings && node.verification.findings.length > 0 && (
            <ul className="mt-2 space-y-1 list-disc list-inside text-[11px]">
              {node.verification.findings.map((f, i) => (
                <li key={i}>
                  <span className="font-semibold uppercase">{f.severity}</span>: {f.description}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
          {t('detailTaskSpec')}
        </h4>
        <div className="relative p-3 rounded-lg border bg-muted/30 font-mono text-xs leading-relaxed group">
          <p className="whitespace-pre-wrap break-words">{node.description}</p>
          <Button
            size="sm"
            variant="ghost"
            aria-label={t('detailCopy')}
            onClick={() => handleCopy(node.description, t('detailCopiedTaskDescription'))}
            className={cn('absolute top-2 right-2 h-7 px-2 transition-opacity', REVEAL_ON_HOVER)}
          >
            <Copy className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
          {t('detailMetadata')}
        </h4>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="p-2.5 rounded-lg border bg-muted/20">
            <span className="text-muted-foreground text-[10px] block">{t('detailTaskId')}</span>
            <span className="font-mono text-[11px] truncate block">{node.task_id}</span>
          </div>
          <div className="p-2.5 rounded-lg border bg-muted/20">
            <span className="text-muted-foreground text-[10px] block">{t('detailParentTaskId')}</span>
            <span className="font-mono text-[11px] truncate block">{node.parent_task_id || t('detailRootTask')}</span>
          </div>
          <div className="p-2.5 rounded-lg border bg-muted/20">
            <span className="text-muted-foreground text-[10px] block">{t('detailRoleScope')}</span>
            <span className="font-mono text-[11px] truncate block">
              {node.role || node.control_scope || t('detailStandardLeaf')}
            </span>
          </div>
          <div className="p-2.5 rounded-lg border bg-muted/20">
            <span className="text-muted-foreground text-[10px] block">{t('detailProgress')}</span>
            <span className="font-mono text-[11px] truncate block">
              {node.progress}% ({t(`statusLabel.${node.status}`)})
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SubagentOverviewTab;
