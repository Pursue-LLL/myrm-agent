/**
 * [INPUT]
 * @/services/memory::(RerankedMemoryHitDTO, ReasonerDecisionKindEnum)
 * lucide-react::(Award, ArrowUpRight, ShieldAlert, Check, HelpCircle, ChevronDown, ChevronUp)
 *
 * [OUTPUT]
 * Component: ReasonerHarmonizerCard
 *
 * [POS]
 * Auditable card for individual memory item post-recall reasoner reranking.
 * Displays rank, channels hit, decision kind, harmonized score, and collapsible rationale.
 * A11y compliant: Native buttons, visible focus rings, zero div role="button", zero unescaped chevrons.
 * Strict typing: Zero `any`. Single file < 200 lines.
 */

import React, { useState } from 'react';
import { Award, ArrowUpRight, ShieldAlert, Check, HelpCircle, ChevronDown, ChevronUp } from 'lucide-react';
import type { RerankedMemoryHitDTO, ReasonerDecisionKindEnum } from '@/services/memory';

interface ReasonerHarmonizerCardProps {
  hit: RerankedMemoryHitDTO;
}

function getDecisionBadge(decision: ReasonerDecisionKindEnum) {
  switch (decision) {
    case 'boost':
      return {
        label: '意图强化 (Boost)',
        className: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
        icon: ArrowUpRight,
      };
    case 'penalize_stale':
      return {
        label: '过时抑制 (Stale Penalty)',
        className: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
        icon: ShieldAlert,
      };
    case 'suppress':
      return {
        label: '低置信度抑制',
        className: 'bg-muted/60 text-muted-foreground border-border/60',
        icon: HelpCircle,
      };
    case 'keep':
    default:
      return {
        label: '多路共识保留',
        className: 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30',
        icon: Check,
      };
  }
}

export const ReasonerHarmonizerCard: React.FC<ReasonerHarmonizerCardProps> = ({ hit }) => {
  const [isRationaleExpanded, setIsRationaleExpanded] = useState<boolean>(false);
  const badgeInfo = getDecisionBadge(hit.reasoner_decision);
  const DecisionIcon = badgeInfo.icon;

  return (
    <article
      aria-label={`检索命中第 ${hit.final_rank} 位: ${hit.memory_id}`}
      className="p-3.5 rounded-lg border border-border/80 bg-card hover:border-primary/40 transition-colors space-y-2.5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary/10 text-primary font-mono text-xs font-bold border border-primary/20">
            #{hit.final_rank}
          </span>
          <span className="font-mono text-xs font-medium text-foreground">
            {hit.memory_id}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${badgeInfo.className}`}
          >
            <DecisionIcon className="w-3 h-3" aria-hidden="true" />
            {badgeInfo.label}
          </span>

          <span className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono font-semibold bg-muted/60 text-foreground border border-border/60">
            <Award className="w-3 h-3 text-amber-500" aria-hidden="true" />
            得分: {hit.final_score.toFixed(2)}
          </span>
        </div>
      </div>

      <p className="text-xs text-foreground/90 leading-relaxed bg-muted/20 p-2.5 rounded border border-border/40 font-sans">
        {hit.content}
      </p>

      <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-border/40">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-muted-foreground font-medium">命中通道:</span>
          {hit.channels_hit.map((ch) => (
            <span
              key={ch}
              className="px-1.5 py-0.5 rounded bg-muted/70 text-muted-foreground font-mono text-[10px] uppercase border border-border/50"
            >
              {ch}
            </span>
          ))}
        </div>

        <button
          type="button"
          onClick={() => setIsRationaleExpanded((prev) => !prev)}
          aria-expanded={isRationaleExpanded}
          aria-label={`${isRationaleExpanded ? '收起' : '展开'} Reasoner 审计推导原因`}
          className="inline-flex items-center gap-1 text-[11px] text-primary hover:text-primary/80 font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary rounded px-1.5 py-0.5"
        >
          {isRationaleExpanded ? '收起审计推导' : '查看审计推导'}
          {isRationaleExpanded ? (
            <ChevronUp className="w-3 h-3" aria-hidden="true" />
          ) : (
            <ChevronDown className="w-3 h-3" aria-hidden="true" />
          )}
        </button>
      </div>

      {isRationaleExpanded && (
        <section
          aria-label="Reasoner 审计理由说明"
          className="p-2.5 rounded bg-muted/50 border border-border/60 text-xs font-mono text-muted-foreground leading-normal"
        >
          <span className="font-semibold text-foreground">审计归因: </span>
          {hit.rationale}
        </section>
      )}
    </article>
  );
};
