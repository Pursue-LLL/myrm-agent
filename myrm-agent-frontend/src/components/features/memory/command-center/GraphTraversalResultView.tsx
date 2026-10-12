/**
 * [INPUT]
 * - @/services/memory/graphRrf: GraphTraverseResponse
 * - @/components/primitives/badge: Badge
 *
 * [OUTPUT]
 * - GraphTraversalResultView: Sub-component rendering BFS traversal nodes, edges, and multi-hop paths.
 *
 * [POS]
 * Sub-component for GraphRRFRetrievalCard under command-center.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React from 'react';
import { ArrowRight, Network, Share2 } from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import type { GraphTraverseResponse } from '@/services/memory/graphRrf';

interface GraphTraversalResultViewProps {
  traversal: GraphTraverseResponse | null;
}

export function GraphTraversalResultView({ traversal }: GraphTraversalResultViewProps) {
  if (!traversal || (traversal.nodes.length === 0 && traversal.paths.length === 0)) {
    return (
      <div className="rounded border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
        暂无拓扑遍历结果，请指定种子实体触发多跳拓扑探索
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Discovered Entity Nodes */}
      <div>
        <div className="mb-1 text-[11px] font-medium text-muted-foreground">
          遍历触达实体节点 ({traversal.nodes.length})
        </div>
        <div className="flex flex-wrap gap-1.5">
          {traversal.nodes.map((node) => (
            <div
              key={node.id}
              className="inline-flex items-center gap-1 rounded border border-border/60 bg-accent/20 px-2 py-0.5 text-xs font-mono"
            >
              <Network className="h-3 w-3 text-cyan-500" />
              <span className="font-semibold text-foreground">{node.name}</span>
              <span className="text-[10px] text-muted-foreground">[{node.entity_type}]</span>
            </div>
          ))}
        </div>
      </div>

      {/* Traversal Paths */}
      {traversal.paths.length > 0 && (
        <div>
          <div className="mb-1 text-[11px] font-medium text-muted-foreground">
            多跳关系路径 ({traversal.paths.length})
          </div>
          <div className="max-h-36 space-y-1 overflow-y-auto pr-1">
            {traversal.paths.map((p, idx) => (
              <div
                key={`${p.source_id}-${p.target_id}-${idx}`}
                className="flex items-center gap-1.5 rounded border border-border/40 bg-card px-2 py-1 text-xs font-mono"
              >
                <Share2 className="h-3 w-3 text-amber-500 shrink-0" />
                <span className="text-foreground">{p.source_id}</span>
                <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
                <Badge variant="outline" className="px-1 py-0 text-[10px] text-primary">
                  {p.relation_type}
                </Badge>
                <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
                <span className="text-foreground">{p.target_id}</span>
                <span className="ml-auto text-[10px] text-muted-foreground">深度 {p.depth}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Linked Memories */}
      {traversal.associated_memory_ids.length > 0 && (
        <div className="pt-1 text-[11px] text-muted-foreground">
          拓扑关联记忆: <strong className="text-foreground">{traversal.associated_memory_ids.length}</strong> 条 (
          {traversal.associated_memory_ids.slice(0, 3).join(', ')}
          {traversal.associated_memory_ids.length > 3 ? '...' : ''})
        </div>
      )}
    </div>
  );
}
