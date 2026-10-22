'use client';

/**
 * [INPUT]: matrix (TradeoffMatrixData), onAdopt, onDismiss, className
 * [OUTPUT]: DebateTradeoffMatrixCard: 分层辩论决策权衡对比矩阵与单一最优推荐方案卡片
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/DebateTradeoffMatrixCard.tsx
 */

import React, { useState } from 'react';
import {
  Scale,
  Award,
  ThumbsUp,
  ThumbsDown,
  ChevronDown,
  ChevronUp,
  X,
  Sparkles,
  BarChart2,
  CheckCircle,
} from 'lucide-react';

export interface TradeoffProposalItem {
  proposal_id: string;
  title: string;
  author_role: 'leader_coordinator' | 'research_analyst' | 'feasibility_auditor';
  author_agent_id: string;
  summary: string;
  pros: string[];
  cons: string[];
  dimension_scores: Record<string, number>;
  is_recommended?: boolean;
}

export interface TradeoffMatrixData {
  matrix_id: string;
  workflow_id: string;
  topic?: string;
  dimensions: string[];
  dimension_weights?: Record<string, number>;
  proposals: TradeoffProposalItem[];
  winner_proposal_id?: string | null;
  recommendation_rationale: string;
  created_at?: number;
}

interface DebateTradeoffMatrixCardProps {
  matrix: TradeoffMatrixData;
  onAdopt?: (winnerProposalId: string) => void;
  onDismiss?: () => void;
  className?: string;
}

export function DebateTradeoffMatrixCard({
  matrix,
  onAdopt,
  onDismiss,
  className = '',
}: DebateTradeoffMatrixCardProps): React.ReactElement {
  const [isExpanded, setIsExpanded] = useState(true);
  const [activeProposalId, setActiveProposalId] = useState<string>(
    matrix.winner_proposal_id || (matrix.proposals.length > 0 ? matrix.proposals[0].proposal_id : '')
  );

  const activeProposal =
    matrix.proposals.find((p) => p.proposal_id === activeProposalId) || matrix.proposals[0];

  const handleAdopt = () => {
    if (matrix.winner_proposal_id && onAdopt) {
      onAdopt(matrix.winner_proposal_id);
    }
  };

  const formatRoleLabel = (role: string) => {
    switch (role) {
      case 'research_analyst':
        return 'Research Analyst';
      case 'feasibility_auditor':
        return 'Feasibility Auditor';
      case 'leader_coordinator':
        return 'Leader Coordinator';
      default:
        return role;
    }
  };

  const formatDimensionName = (dim: string) => {
    return dim.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  };

  return (
    <section
      aria-label="Debate Trade-off Matrix & Final Synthesis"
      className={`rounded-xl border border-border/70 bg-card text-card-foreground shadow-lg overflow-hidden transition-all ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-muted/40 border-b border-border/40">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <Scale className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold tracking-tight">Decision Trade-off Matrix</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium border border-primary/20">
                {matrix.proposals.length} Proposals Evaluated
              </span>
            </div>
            {matrix.topic && (
              <p className="text-xs text-muted-foreground truncate max-w-sm">{matrix.topic}</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 rounded-md text-muted-foreground hover:bg-muted transition-colors"
            aria-label={isExpanded ? 'Collapse matrix' : 'Expand matrix'}
          >
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="p-1 rounded-md text-muted-foreground hover:bg-muted transition-colors"
              aria-label="Close matrix card"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* Leader Recommendation Rationale Bar */}
          <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 text-xs text-emerald-700 dark:text-emerald-300 space-y-1.5">
            <div className="flex items-center justify-between font-semibold">
              <span className="flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-emerald-500" />
                Leader Consensus Recommendation
              </span>
              {matrix.winner_proposal_id && onAdopt && (
                <button
                  type="button"
                  onClick={handleAdopt}
                  className="px-2.5 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700 transition-colors font-medium flex items-center gap-1 text-[11px]"
                >
                  <CheckCircle className="w-3 h-3" /> Adopt Solution
                </button>
              )}
            </div>
            <p className="leading-relaxed opacity-90">{matrix.recommendation_rationale}</p>
          </div>

          {/* Proposals Selector Tabs */}
          <div className="grid grid-cols-2 gap-2">
            {matrix.proposals.map((proposal) => {
              const isWinner = proposal.proposal_id === matrix.winner_proposal_id || proposal.is_recommended;
              const isSelected = proposal.proposal_id === activeProposalId;

              return (
                <button
                  key={proposal.proposal_id}
                  type="button"
                  onClick={() => setActiveProposalId(proposal.proposal_id)}
                  className={`text-left p-3 rounded-lg border transition-all relative ${
                    isSelected
                      ? 'border-primary ring-1 ring-primary bg-primary/5'
                      : 'border-border/60 hover:bg-muted/30'
                  } ${isWinner ? 'border-emerald-500/50' : ''}`}
                >
                  {isWinner && (
                    <span className="absolute top-2 right-2 flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-500 text-white">
                      <Award className="w-3 h-3" /> Winner
                    </span>
                  )}
                  <div className="text-xs font-semibold text-foreground truncate pr-14">
                    {proposal.title}
                  </div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">
                    {formatRoleLabel(proposal.author_role)}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Active Proposal Deep Dive */}
          {activeProposal && (
            <div className="rounded-lg border border-border/60 bg-muted/10 p-3 space-y-3">
              <div>
                <div className="text-xs font-medium text-foreground">{activeProposal.summary}</div>
              </div>

              {/* Multi-Dimensional Scoring Bars */}
              <div className="space-y-1.5 pt-1">
                <div className="flex items-center gap-1 text-[11px] font-semibold text-muted-foreground">
                  <BarChart2 className="w-3 h-3" /> Dimension Evaluation Scores
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {matrix.dimensions.map((dim) => {
                    const score = activeProposal.dimension_scores[dim] ?? 0.5;
                    const pct = Math.round(score * 100);

                    return (
                      <div key={dim} className="space-y-0.5">
                        <div className="flex justify-between text-[10px] text-muted-foreground">
                          <span>{formatDimensionName(dim)}</span>
                          <span className="font-mono font-medium text-foreground">{pct}%</span>
                        </div>
                        <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              score >= 0.8
                                ? 'bg-emerald-500'
                                : score >= 0.6
                                ? 'bg-primary'
                                : 'bg-amber-500'
                            }`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Pros & Cons comparison */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-border/40">
                {/* Pros */}
                <div className="space-y-1">
                  <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                    <ThumbsUp className="w-3 h-3" /> Key Advantages
                  </span>
                  <ul className="space-y-1">
                    {activeProposal.pros.map((pro) => (
                      <li
                        key={pro}
                        className="text-[11px] text-muted-foreground flex items-start gap-1"
                      >
                        <span className="text-emerald-500">•</span>
                        <span>{pro}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Cons */}
                <div className="space-y-1">
                  <span className="flex items-center gap-1 text-[11px] font-semibold text-red-500">
                    <ThumbsDown className="w-3 h-3" /> Known Trade-offs / Risks
                  </span>
                  <ul className="space-y-1">
                    {activeProposal.cons.map((con) => (
                      <li
                        key={con}
                        className="text-[11px] text-muted-foreground flex items-start gap-1"
                      >
                        <span className="text-red-500">•</span>
                        <span>{con}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default DebateTradeoffMatrixCard;
