/**
 * [INPUT]
 * @/services/memory::ReorganizationBatchResponse
 * lucide-react::(Sparkles, CheckCircle2, Sliders, Play, Layers)
 *
 * [OUTPUT]
 * Component: GraphReorganizationConsoleView
 *
 * [POS]
 * Console view for graph memory reorganization execution and batch audit reporting.
 * Allows adjusting confidence thresholds and displays newly inferred multi-relational edges.
 * A11y compliant: Native elements, label htmlFor binding, visible focus rings, zero bare chevrons.
 * Strict typing: Zero `any`. Single file < 250 lines.
 */

import React, { useState } from 'react';
import { Sparkles, CheckCircle2, Sliders, Play, Layers } from 'lucide-react';
import type { ReorganizationBatchResponse } from '@/services/memory';

interface GraphReorganizationConsoleViewProps {
  lastReport: ReorganizationBatchResponse | null;
  isReorganizing: boolean;
  onExecuteReorganization: (minConfidence: number) => void;
}

export const GraphReorganizationConsoleView: React.FC<GraphReorganizationConsoleViewProps> = ({
  lastReport,
  isReorganizing,
  onExecuteReorganization,
}) => {
  const [minConfidence, setMinConfidence] = useState<number>(0.8);

  return (
    <section className="flex flex-col gap-4 p-4 rounded-lg border border-border/70 bg-card/40">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
            <Sparkles className="w-4 h-4 text-primary" aria-hidden="true" />
            Automated Graph Reorganization Console
          </h4>
          <p className="text-xs text-muted-foreground">
            Infer subsumptions, temporal sequences, deductions, and detect factual contradictions.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs">
            <label htmlFor="min-confidence-slider" className="text-muted-foreground flex items-center gap-1">
              <Sliders className="w-3.5 h-3.5" aria-hidden="true" />
              Min Confidence:
            </label>
            <span className="font-mono font-semibold text-foreground w-8 text-right">
              {(minConfidence * 100).toFixed(0)}%
            </span>
            <input
              id="min-confidence-slider"
              type="range"
              min="0.5"
              max="0.95"
              step="0.05"
              value={minConfidence}
              onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
              disabled={isReorganizing}
              className="w-24 accent-primary cursor-pointer disabled:opacity-50"
            />
          </div>

          <button
            type="button"
            onClick={() => onExecuteReorganization(minConfidence)}
            disabled={isReorganizing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
            aria-label="Execute graph reorganization pass"
          >
            <Play className={`w-3.5 h-3.5 ${isReorganizing ? 'animate-spin' : ''}`} aria-hidden="true" />
            <span>{isReorganizing ? 'Synthesizing...' : 'Execute Pass'}</span>
          </button>
        </div>
      </div>

      {lastReport ? (
        <div className="p-3.5 rounded-md border border-border/80 bg-background/70 text-xs flex flex-col gap-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2">
            <span className="font-semibold text-foreground flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-500" aria-hidden="true" />
              Batch Execution Succeeded: {lastReport.batch_id}
            </span>
            <span className="text-[11px] font-mono text-muted-foreground">
              {new Date(lastReport.created_at).toLocaleTimeString()}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <div className="p-2 rounded bg-muted/40">
              <span className="text-muted-foreground block text-[10px] uppercase">Evaluated Nodes</span>
              <span className="font-semibold text-foreground">{lastReport.analyzed_nodes_count}</span>
            </div>
            <div className="p-2 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
              <span className="block text-[10px] uppercase">Synthesized Edges</span>
              <span className="font-semibold">{lastReport.created_edges_count}</span>
            </div>
            <div className="p-2 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400">
              <span className="block text-[10px] uppercase">Superseded</span>
              <span className="font-semibold">{lastReport.superseded_nodes_count}</span>
            </div>
            <div className="p-2 rounded bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
              <span className="block text-[10px] uppercase">Deductions</span>
              <span className="font-semibold">{lastReport.deductions_count}</span>
            </div>
          </div>

          {lastReport.edges.length > 0 && (
            <div className="flex flex-col gap-1.5 pt-1">
              <span className="text-[11px] font-semibold text-muted-foreground flex items-center gap-1">
                <Layers className="w-3 h-3" aria-hidden="true" />
                Newly Synthesized Edges in Batch:
              </span>
              <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
                {lastReport.edges.map((edge) => (
                  <div
                    key={edge.edge_id}
                    className="p-1.5 rounded bg-muted/30 border border-border/40 text-[11px] flex items-center justify-between gap-2"
                  >
                    <span className="text-foreground truncate">
                      {edge.source_node_id} → {edge.target_node_id} ({edge.relation_type})
                    </span>
                    <span className="text-muted-foreground text-[10px] shrink-0">
                      {(edge.weight * 100).toFixed(0)}% confidence
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="p-4 text-center text-xs text-muted-foreground rounded border border-dashed border-border">
          No reorganization pass executed in this session yet. Click &quot;Execute Pass&quot; to synthesize semantic edges.
        </div>
      )}
    </section>
  );
};
