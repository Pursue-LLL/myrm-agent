/**
 * [INPUT]
 * @/services/memory::(MemoryGraphNodeDTO, MemoryGraphEdgeDTO)
 * lucide-react::(GitBranch, Clock, ArrowRight, ShieldCheck, Tag, Info)
 *
 * [OUTPUT]
 * Component: LineageDagGraphView
 *
 * [POS]
 * Interactive visual representation of Memory Lineage DAG and multi-relational edges.
 * Displays nodes with version tags, lifecycle statuses, and relational edge bindings.
 * A11y compliant: Semantic section, native buttons, visible focus rings, zero raw chevron characters.
 * Strict typing: Zero `any`. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { GitBranch, Clock, ArrowRight, ShieldCheck, Tag, Info } from 'lucide-react';
import type { MemoryGraphNodeDTO, MemoryGraphEdgeDTO } from '@/services/memory';

interface LineageDagGraphViewProps {
  nodes: MemoryGraphNodeDTO[];
  edges: MemoryGraphEdgeDTO[];
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
  onTraceLineage: (nodeId: string) => void;
}

export const LineageDagGraphView: React.FC<LineageDagGraphViewProps> = ({
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
  onTraceLineage,
}) => {
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'superseded'>('all');

  const filteredNodes = nodes.filter((node) => {
    if (statusFilter === 'active') return node.status === 'active';
    if (statusFilter === 'superseded') return node.status === 'superseded';
    return true;
  });

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
            Active
          </span>
        );
      case 'superseded':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-amber-500/15 text-amber-600 dark:text-amber-400">
            Superseded
          </span>
        );
      case 'reverted':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-rose-500/15 text-rose-600 dark:text-rose-400">
            Reverted
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-muted text-muted-foreground">
            {status}
          </span>
        );
    }
  };

  const getRelationBadge = (relationType: string) => {
    switch (relationType) {
      case 'supersedes':
        return 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30';
      case 'subsumption':
        return 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30';
      case 'temporal_sequence':
        return 'bg-purple-500/15 text-purple-600 dark:text-purple-400 border-purple-500/30';
      case 'deduction':
        return 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30';
      case 'contradiction':
        return 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30';
      default:
        return 'bg-muted text-muted-foreground border-border';
    }
  };

  return (
    <section className="flex flex-col gap-4 p-4 rounded-lg border border-border/70 bg-card/40">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
            <GitBranch className="w-4 h-4 text-primary" aria-hidden="true" />
            Knowledge Graph Topology &amp; Lineage DAG
          </h4>
          <p className="text-xs text-muted-foreground">
            Multi-relational graph edges preventing amnesia and tracking historical derivations.
          </p>
        </div>

        <div className="flex items-center gap-1.5 bg-muted/60 p-1 rounded-md text-xs">
          <button
            type="button"
            onClick={() => setStatusFilter('all')}
            className={`px-2.5 py-1 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
              statusFilter === 'all'
                ? 'bg-background shadow-xs font-semibold text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            All ({nodes.length})
          </button>
          <button
            type="button"
            onClick={() => setStatusFilter('active')}
            className={`px-2.5 py-1 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
              statusFilter === 'active'
                ? 'bg-background shadow-xs font-semibold text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Active ({nodes.filter((n) => n.status === 'active').length})
          </button>
          <button
            type="button"
            onClick={() => setStatusFilter('superseded')}
            className={`px-2.5 py-1 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
              statusFilter === 'superseded'
                ? 'bg-background shadow-xs font-semibold text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Superseded ({nodes.filter((n) => n.status === 'superseded').length})
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Nodes Column */}
        <div className="flex flex-col gap-2.5">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Memory Nodes ({filteredNodes.length})
          </span>
          <div className="flex flex-col gap-2 max-h-[380px] overflow-y-auto pr-1">
            {filteredNodes.length === 0 ? (
              <div className="p-4 text-center text-xs text-muted-foreground rounded border border-dashed border-border">
                No memory nodes match current filter.
              </div>
            ) : (
              filteredNodes.map((node) => {
                const isSelected = selectedNodeId === node.node_id;
                return (
                  <article
                    key={node.node_id}
                    className={`p-3 rounded-md border text-xs transition-all ${
                      isSelected
                        ? 'border-primary/80 bg-primary/5 shadow-xs'
                        : 'border-border/70 bg-background/60 hover:border-border'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-1.5">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-semibold text-foreground">
                          {node.subject}
                        </span>
                        <span className="text-muted-foreground font-mono text-[10px]">
                          [{node.predicate}]
                        </span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">
                          v{node.version}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {getStatusBadge(node.status)}
                      </div>
                    </div>

                    <p className="text-foreground/90 line-clamp-2 mb-2 font-normal">
                      {node.content}
                    </p>

                    <div className="flex items-center justify-between gap-2 pt-2 border-t border-border/50 text-[11px] text-muted-foreground">
                      <div className="flex items-center gap-2">
                        <span className="flex items-center gap-1">
                          <Tag className="w-3 h-3" aria-hidden="true" />
                          {node.object_value}
                        </span>
                        <span className="flex items-center gap-1">
                          <ShieldCheck className="w-3 h-3 text-emerald-500" aria-hidden="true" />
                          {(node.confidence * 100).toFixed(0)}%
                        </span>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => onSelectNode(node.node_id)}
                          className="px-2 py-0.5 rounded border border-border bg-background hover:bg-accent text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
                        >
                          Details
                        </button>
                        <button
                          type="button"
                          onClick={() => onTraceLineage(node.node_id)}
                          className="px-2 py-0.5 rounded bg-primary/10 text-primary hover:bg-primary/20 font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
                        >
                          Trace
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })
            )}
          </div>
        </div>

        {/* Edges Column */}
        <div className="flex flex-col gap-2.5">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Multi-Relational Graph Edges ({edges.length})
          </span>
          <div className="flex flex-col gap-2 max-h-[380px] overflow-y-auto pr-1">
            {edges.length === 0 ? (
              <div className="p-4 text-center text-xs text-muted-foreground rounded border border-dashed border-border">
                No relational edges synthesized yet. Run Reorganizer to infer relationships.
              </div>
            ) : (
              edges.map((edge) => {
                const srcNode = nodes.find((n) => n.node_id === edge.source_node_id);
                const tgtNode = nodes.find((n) => n.node_id === edge.target_node_id);
                return (
                  <article
                    key={edge.edge_id}
                    className="p-3 rounded-md border border-border/70 bg-background/60 text-xs flex flex-col gap-1.5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-medium text-foreground truncate max-w-[120px]">
                          {srcNode?.subject || edge.source_node_id}
                        </span>
                        <ArrowRight className="w-3 h-3 text-muted-foreground" aria-hidden="true" />
                        <span className="font-medium text-foreground truncate max-w-[120px]">
                          {tgtNode?.subject || edge.target_node_id}
                        </span>
                      </div>

                      <span
                        className={`px-2 py-0.5 rounded border text-[10px] font-semibold uppercase tracking-wider ${getRelationBadge(
                          edge.relation_type
                        )}`}
                      >
                        {edge.relation_type}
                      </span>
                    </div>

                    {edge.rationale && (
                      <p className="text-[11px] text-muted-foreground flex items-start gap-1">
                        <Info className="w-3.5 h-3.5 shrink-0 mt-0.5 text-primary/70" aria-hidden="true" />
                        <span>{edge.rationale}</span>
                      </p>
                    )}

                    <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-1 border-t border-border/40">
                      <span>Weight: {(edge.weight * 100).toFixed(0)}%</span>
                      <span className="flex items-center gap-1 font-mono">
                        <Clock className="w-2.5 h-2.5" aria-hidden="true" />
                        {new Date(edge.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </article>
                );
              })
            )}
          </div>
        </div>
      </div>
    </section>
  );
};
