/**
 * [INPUT]
 * @/services/memory::(TargetNodeCandidateDTO, LiveCorrectionMutationResultDTO)
 * Lucide icons (GitCompare, CheckCircle2, ArrowRight, XCircle, ShieldAlert)
 *
 * [OUTPUT]
 * Component: ConflictLocalizationComparisonView
 *
 * [POS]
 * Candidate memory conflict localization & atomic comparison card for Item 128 Live Correction Studio.
 * Strictly typed, zero any, a11y compliant with visible focus rings. Single file < 250 lines.
 */

'use client';

import React from 'react';
import { ArrowRight, CheckCircle2, GitCompare, ShieldAlert, XCircle } from 'lucide-react';
import type { LiveCorrectionMutationResultDTO, TargetNodeCandidateDTO } from '@/services/memory';

interface ConflictLocalizationComparisonViewProps {
  candidates: TargetNodeCandidateDTO[];
  activeMutation?: LiveCorrectionMutationResultDTO | null;
}

const ACTION_BADGES: Record<string, { label: string; color: string }> = {
  supersede: {
    label: '版本更替 (Supersede)',
    color: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20',
  },
  retract: {
    label: '撤回清除 (Retract)',
    color: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20',
  },
  amend: {
    label: '增补修正 (Amend)',
    color: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
  },
  create_novel: {
    label: '新建条目 (Create Novel)',
    color: 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20',
  },
};

export const ConflictLocalizationComparisonView: React.FC<ConflictLocalizationComparisonViewProps> = ({
  candidates,
  activeMutation,
}) => {
  const targetId = activeMutation?.target_memory_id;
  const actionBadge = activeMutation?.action
    ? ACTION_BADGES[activeMutation.action] || {
        label: activeMutation.action,
        color: 'bg-muted text-foreground border-border',
      }
    : null;

  return (
    <section
      aria-label="冲突记忆定位与状态机对比"
      className="space-y-4 rounded-xl border border-border/80 bg-card/60 p-4 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <GitCompare className="h-4 w-4 text-primary" aria-hidden="true" />
          <h3 className="text-sm font-semibold text-foreground">
            记忆冲突定位与原子状态演进 (Conflict Localization & State Transition)
          </h3>
        </div>
        {actionBadge && (
          <span
            className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold ${actionBadge.color}`}
          >
            {actionBadge.label}
          </span>
        )}
      </div>

      {/* When a mutation has just occurred, render before/after diff banner */}
      {activeMutation && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs">
          <div className="mb-2 font-medium text-foreground">
            状态机转换比对 (State Transition Diff):
          </div>
          <div className="grid grid-cols-1 items-center gap-3 sm:grid-cols-[1fr,auto,1fr]">
            <div className="rounded border border-rose-500/20 bg-rose-500/5 p-2">
              <span className="block font-medium text-rose-600 dark:text-rose-400">
                原记忆记录 (Superseded Content):
              </span>
              <p className="mt-1 line-through text-muted-foreground">
                {activeMutation.superseded_content || '(无历史条目 / 全新创建)'}
              </p>
              {activeMutation.target_memory_id && (
                <span className="mt-1 block font-mono text-[10px] text-muted-foreground/70">
                  ID: {activeMutation.target_memory_id}
                </span>
              )}
            </div>

            <div className="flex justify-center text-primary" aria-hidden="true">
              <ArrowRight className="h-5 w-5" />
            </div>

            <div className="rounded border border-emerald-500/20 bg-emerald-500/5 p-2">
              <span className="block font-medium text-emerald-600 dark:text-emerald-400">
                生效新记录 (Active Content):
              </span>
              <p className="mt-1 font-medium text-foreground">
                {activeMutation.new_content || '(已撤回清除，置为空)'}
              </p>
              {activeMutation.new_memory_id && (
                <span className="mt-1 block font-mono text-[10px] text-emerald-600/70 dark:text-emerald-400/70">
                  ID: {activeMutation.new_memory_id}
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Active candidates list in memory pool */}
      <div className="space-y-2">
        <div className="text-xs font-medium text-muted-foreground">
          内存池候选节点 ({candidates.length} 条可用候选):
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {candidates.map((cand) => {
            const isTargeted = cand.memory_id === targetId;
            return (
              <div
                key={cand.memory_id}
                className={`rounded-lg border p-3 text-xs transition ${
                  isTargeted
                    ? 'border-primary bg-primary/10 shadow-sm'
                    : 'border-border/60 bg-background/50 hover:border-border'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px] font-semibold text-primary">
                    {cand.memory_id}
                  </span>
                  <div className="flex items-center gap-1.5">
                    {cand.cube_id && (
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        {cand.cube_id}
                      </span>
                    )}
                    {isTargeted && (
                      <span className="inline-flex items-center gap-1 rounded bg-primary/20 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                        <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                        定位命中
                      </span>
                    )}
                  </div>
                </div>
                <p className="mt-1.5 line-clamp-2 text-foreground">{cand.content}</p>
                {cand.attributes && Object.keys(cand.attributes).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1 text-[10px] text-muted-foreground">
                    {Object.entries(cand.attributes).map(([k, v]) => (
                      <span key={k} className="rounded bg-muted/60 px-1 py-0.5">
                        {k}: {v}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
