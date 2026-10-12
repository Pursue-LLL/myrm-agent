'use client';

/**
 * [INPUT]
 * @/services/memory/temporalGraph::TemporalFactEdgeDTO, SaveFactEdgeRequestDTO
 *
 * [OUTPUT]
 * TemporalGraphEvolutionTimelineView: Subview component rendering temporal relationship evolution timeline,
 * active vs superseded fact contrast, lineage tracking, and conflict reconciliation insertion form.
 *
 * [POS]
 * Subcomponent for Item 93 (Temporal Knowledge Graph Decay and Entity Fact Conflict Resolution Suite).
 * Strict typing applied: No `any` types allowed. Single responsibility maintained.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { GitCommit, ArrowRight, History, Plus, AlertTriangle, ShieldCheck } from 'lucide-react';
import type {
  TemporalFactEdgeDTO,
  SaveFactEdgeRequestDTO,
} from '@/services/memory/temporalGraph';

interface TemporalGraphEvolutionTimelineViewProps {
  edges: TemporalFactEdgeDTO[];
  lineageChain: TemporalFactEdgeDTO[];
  selectedEdgeId: string | null;
  onSelectEdge: (edgeId: string) => void;
  onSaveEdge: (request: SaveFactEdgeRequestDTO) => Promise<void>;
}

export function TemporalGraphEvolutionTimelineView({
  edges,
  lineageChain,
  selectedEdgeId,
  onSelectEdge,
  onSaveEdge,
}: TemporalGraphEvolutionTimelineViewProps): React.JSX.Element {
  const [showAddForm, setShowAddForm] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Form states
  const [sourceId, setSourceId] = useState<string>('user_alice');
  const [targetId, setTargetId] = useState<string>('comp_techcorp');
  const [predicate, setPredicate] = useState<string>('works_at');
  const [confidence, setConfidence] = useState<number>(0.98);

  const activeEdges = edges.filter((e) => !e.is_superseded);
  const supersededEdges = edges.filter((e) => e.is_superseded);
  const selectedEdge = edges.find((e) => e.edge_id === selectedEdgeId) ?? activeEdges[0] ?? null;

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceId.trim() || !targetId.trim() || !predicate.trim()) {
      return;
    }
    setIsSubmitting(true);
    try {
      await onSaveEdge({
        source_id: sourceId.trim(),
        target_id: targetId.trim(),
        predicate: predicate.trim().toLowerCase(),
        confidence_score: confidence,
      });
      setShowAddForm(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="temporal-graph-evolution-timeline-view">
      {/* Action Bar */}
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          时序演变图谱：互斥事实（如就职单位、居住地、主用架构）自动平滑取代，保留历史演进谱系，杜绝死锁与物理删除
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <Plus className="w-3.5 h-3.5" />
          {showAddForm ? '收起表单' : '录入新时序事实'}
        </Button>
      </div>

      {/* Quick Add Form */}
      {showAddForm && (
        <form
          onSubmit={handleCreateSubmit}
          className="rounded-lg border border-primary/20 bg-primary/5 p-3 space-y-2 text-xs"
          data-testid="add-fact-edge-form"
        >
          <div className="font-medium text-foreground flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
            录入关系边（若为互斥谓词如 works_at，系统将自动标记旧事实为 superseded 并构建演化谱系）
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div>
              <label htmlFor="edge-source-id" className="block text-muted-foreground mb-1">
                主体实体 (Source ID)
              </label>
              <input
                id="edge-source-id"
                type="text"
                value={sourceId}
                onChange={(e) => setSourceId(e.target.value)}
                className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                required
              />
            </div>
            <div>
              <label htmlFor="edge-predicate" className="block text-muted-foreground mb-1">
                关系谓词 (Predicate)
              </label>
              <input
                id="edge-predicate"
                type="text"
                value={predicate}
                onChange={(e) => setPredicate(e.target.value)}
                placeholder="works_at, residence_city"
                className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                required
              />
            </div>
            <div>
              <label htmlFor="edge-target-id" className="block text-muted-foreground mb-1">
                客体实体 (Target ID)
              </label>
              <input
                id="edge-target-id"
                type="text"
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                required
              />
            </div>
            <div>
              <label htmlFor="edge-confidence" className="block text-muted-foreground mb-1">
                置信度 (Confidence)
              </label>
              <input
                id="edge-confidence"
                type="number"
                step="0.01"
                min="0.1"
                max="1.0"
                value={confidence}
                onChange={(e) => setConfidence(Number(e.target.value))}
                className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>
          <div className="flex justify-end pt-1">
            <Button
              type="submit"
              size="sm"
              disabled={isSubmitting || !sourceId.trim() || !targetId.trim()}
              className="text-xs focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {isSubmitting ? '消解写入中...' : '提交并自动消解冲突'}
            </Button>
          </div>
        </form>
      )}

      {/* Main Grid: Active Edges & Lineage Inspector */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Left: Facts List (Active & Superseded) */}
        <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
          <div className="text-[11px] font-semibold text-foreground flex items-center gap-1">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
            当前生效事实 ({activeEdges.length})
          </div>

          {activeEdges.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border/70 p-4 text-center text-xs text-muted-foreground">
              暂无生效关系事实
            </div>
          ) : (
            activeEdges.map((edge) => {
              const isSelected = selectedEdge?.edge_id === edge.edge_id;
              return (
                <button
                  type="button"
                  key={edge.edge_id}
                  onClick={() => onSelectEdge(edge.edge_id)}
                  aria-label={`选择时序关系事实 ${edge.source_id} ${edge.predicate} ${edge.target_id}`}
                  className={`w-full text-left rounded-lg border p-2.5 transition-colors text-xs focus:outline-none focus:ring-2 focus:ring-primary ${
                    isSelected
                      ? 'border-primary bg-primary/10'
                      : 'border-border/60 bg-accent/20 hover:bg-accent/40'
                  }`}
                  data-testid={`edge-card-${edge.edge_id}`}
                >
                  <div className="flex items-center justify-between">
                    <div className="font-semibold text-foreground flex items-center gap-1.5 font-mono text-[11px]">
                      <span>{edge.source_id}</span>
                      <ArrowRight className="w-3 h-3 text-primary" />
                      <span className="text-primary font-bold">[{edge.predicate}]</span>
                      <ArrowRight className="w-3 h-3 text-primary" />
                      <span>{edge.target_id}</span>
                    </div>
                    <Badge variant="outline" className="text-[10px] bg-emerald-500/10 text-emerald-600 border-emerald-500/30">
                      ACTIVE
                    </Badge>
                  </div>
                  <div className="mt-1 flex items-center justify-between text-[10px] text-muted-foreground">
                    <span>生效期: {edge.valid_from.slice(0, 10)} 起</span>
                    <span>置信度: {(edge.confidence_score * 100).toFixed(0)}%</span>
                  </div>
                </button>
              );
            })
          )}

          {supersededEdges.length > 0 && (
            <div className="pt-2 space-y-1.5">
              <div className="text-[11px] font-semibold text-muted-foreground flex items-center gap-1">
                <History className="w-3.5 h-3.5 text-amber-500" />
                已平滑取代的历史演进事实 ({supersededEdges.length})
              </div>
              {supersededEdges.map((edge) => (
                <button
                  type="button"
                  key={edge.edge_id}
                  onClick={() => onSelectEdge(edge.edge_id)}
                  aria-label={`选择已取代时序事实 ${edge.source_id} ${edge.predicate} ${edge.target_id}`}
                  className="w-full text-left rounded-lg border border-border/40 bg-accent/10 p-2 text-xs opacity-75 hover:opacity-100 transition-opacity focus:outline-none focus:ring-2 focus:ring-primary"
                  data-testid={`superseded-edge-card-${edge.edge_id}`}
                >
                  <div className="flex items-center justify-between">
                    <div className="text-muted-foreground flex items-center gap-1 font-mono text-[11px] line-through">
                      <span>{edge.source_id}</span>
                      <span>[{edge.predicate}]</span>
                      <span>{edge.target_id}</span>
                    </div>
                    <Badge variant="secondary" className="text-[10px] text-amber-600">
                      SUPERSEDED
                    </Badge>
                  </div>
                  <div className="mt-0.5 text-[10px] text-muted-foreground">
                    已被取代，截止于: {edge.valid_until ? edge.valid_until.slice(0, 10) : '近期'}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right: Evolution Lineage Inspector */}
        <div className="rounded-lg border border-border/60 bg-accent/15 p-3 space-y-3">
          <div className="flex items-center justify-between border-b border-border/40 pb-2">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <GitCommit className="w-4 h-4 text-primary" />
              历史演进脉络追溯 (Lineage Chain)
            </span>
            {selectedEdge && (
              <span className="font-mono text-[10px] text-muted-foreground">{selectedEdge.edge_id}</span>
            )}
          </div>

          {selectedEdge ? (
            <div className="space-y-3 text-xs" data-testid="lineage-detail-box">
              <div className="rounded border border-border/50 bg-background/70 p-2.5 space-y-1">
                <div className="text-muted-foreground text-[11px] font-medium">当前选中事实：</div>
                <div className="font-mono text-sm text-foreground flex items-center gap-1.5 flex-wrap">
                  <span className="font-bold">{selectedEdge.source_id}</span>
                  <span className="text-primary font-semibold">[{selectedEdge.predicate}]</span>
                  <span className="font-bold">{selectedEdge.target_id}</span>
                </div>
                <div className="text-[11px] text-muted-foreground pt-1 flex items-center gap-3">
                  <span>状态: {selectedEdge.is_superseded ? '已取代 (Superseded)' : '生效中 (Active)'}</span>
                  <span>访问热度: {selectedEdge.access_count} 次</span>
                </div>
              </div>

              {/* Backward Lineage Chain */}
              <div className="space-y-2">
                <div className="text-[11px] font-medium text-foreground">
                  回溯历史变迁链 ({lineageChain.length} 个版本节点):
                </div>
                {lineageChain.length === 0 ? (
                  <div className="rounded bg-accent/30 p-3 text-center text-[11px] text-muted-foreground">
                    该事实为初始原始事实，前序暂无被取代的历史版本。
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    {lineageChain.map((item, idx) => (
                      <div
                        key={item.edge_id}
                        className={`rounded border p-2 text-[11px] font-mono flex items-center justify-between ${
                          idx === 0
                            ? 'border-primary/50 bg-primary/10 text-primary'
                            : 'border-border/40 bg-background/50 text-muted-foreground'
                        }`}
                        data-testid={`lineage-node-${item.edge_id}`}
                      >
                        <div className="flex items-center gap-1.5">
                          <span className="rounded-full bg-primary/20 w-4 h-4 flex items-center justify-center text-[10px]">
                            {idx + 1}
                          </span>
                          <span>
                            {item.source_id} -&gt; {item.predicate} -&gt; {item.target_id}
                          </span>
                        </div>
                        <Badge variant="outline" className="text-[10px]">
                          {item.is_superseded ? '已过时' : '最新'}
                        </Badge>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="py-12 text-center text-xs text-muted-foreground">
              请从左侧选择一条关系事实以查看时序演变链条
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
