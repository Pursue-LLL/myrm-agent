import React from 'react';
import { ArbitrationStrategy, ArbitrationVerdictItem, StagingProposalItem } from './types';

export interface ProposalsViewProps {
  proposals: StagingProposalItem[];
  strategy: ArbitrationStrategy;
  onChangeStrategy: (st: ArbitrationStrategy) => void;
  verdict: ArbitrationVerdictItem | null;
  isProcessing: boolean;
  onArbitrate: () => void;
  onAcceptProposal: (propId: string) => void;
  onRejectProposal: (propId: string) => void;
}

export const ProposalsView: React.FC<ProposalsViewProps> = ({
  proposals,
  strategy,
  onChangeStrategy,
  verdict,
  isProcessing,
  onArbitrate,
  onAcceptProposal,
  onRejectProposal,
}) => {
  return (
    <div className="space-y-3">
      <div className="p-3 rounded-lg border border-border bg-muted/20 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <label htmlFor="arbitration-strategy-select" className="text-xs font-medium text-muted-foreground">
            Strategy:
          </label>
          <select
            id="arbitration-strategy-select"
            value={strategy}
            onChange={(e) => onChangeStrategy(e.target.value as ArbitrationStrategy)}
            className="text-xs px-2 py-1 rounded bg-background border border-border"
          >
            <option value="human_priority">Human Priority</option>
            <option value="isolated_staging_proposal">Isolated Staging Proposal</option>
            <option value="timestamp_lww">Timestamp LWW</option>
          </select>
        </div>
        <button
          type="button"
          disabled={isProcessing}
          onClick={onArbitrate}
          className="px-3 py-1 text-xs font-medium text-white bg-indigo-600 rounded hover:bg-indigo-700 disabled:opacity-50"
        >
          Simulate Conflict Arbitration
        </button>
      </div>

      {verdict && (
        <div className="p-2.5 rounded-lg border border-indigo-500/30 bg-indigo-500/5 text-xs text-foreground space-y-1">
          <span className="font-semibold text-indigo-600 dark:text-indigo-400">Arbitration Verdict:</span>
          <p className="text-[11px] text-muted-foreground">{verdict.summary}</p>
        </div>
      )}

      <div className="space-y-2">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Pending Proposals</h4>
        {proposals.length === 0 ? (
          <p className="text-xs text-muted-foreground italic">No staging proposals pending review.</p>
        ) : (
          proposals.map((p) => (
            <div key={p.proposalId} className="p-2.5 rounded-lg border border-border bg-background space-y-1.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-mono font-medium text-primary">{p.proposalId}</span>
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold ${
                    p.status === 'pending'
                      ? 'bg-amber-500/10 text-amber-600'
                      : p.status === 'accepted'
                      ? 'bg-emerald-500/10 text-emerald-600'
                      : 'bg-red-500/10 text-red-600'
                  }`}
                >
                  {p.status}
                </span>
              </div>
              <p className="text-muted-foreground text-[11px]">
                Target: <code className="text-foreground">{p.blockId}</code> | By: {p.authorId}
              </p>
              <p className="text-foreground font-mono bg-muted/30 p-1.5 rounded text-[11px]">{p.content}</p>
              <p className="text-[10px] text-muted-foreground italic">Intent: {p.intentReason}</p>
              {p.status === 'pending' && (
                <div className="flex gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => onAcceptProposal(p.proposalId)}
                    className="px-2 py-0.5 text-[11px] font-medium bg-emerald-600 text-white rounded hover:bg-emerald-700"
                  >
                    Accept & Merge
                  </button>
                  <button
                    type="button"
                    onClick={() => onRejectProposal(p.proposalId)}
                    className="px-2 py-0.5 text-[11px] font-medium bg-muted text-muted-foreground rounded hover:bg-muted/80"
                  >
                    Reject
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
