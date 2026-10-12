'use client';

/**
 * [INPUT]
 * @/services/memory/temporalGraph::TemporalEntityNodeDTO, TemporalFactHitDTO, SaveEntityNodeRequestDTO
 *
 * [OUTPUT]
 * TemporalDecayScorerConsoleView: Subview component rendering half-life decay score calculations,
 * dynamic recency-ranked fact queries, and entity node management.
 *
 * [POS]
 * Subcomponent for Item 93 (Temporal Knowledge Graph Decay and Entity Fact Conflict Resolution Suite).
 * Strict typing applied: No `any` types allowed. Single responsibility maintained.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Clock, Plus, Search, UserCheck, Activity, Layers } from 'lucide-react';
import type {
  TemporalEntityNodeDTO,
  TemporalFactHitDTO,
  SaveEntityNodeRequestDTO,
} from '@/services/memory/temporalGraph';

interface TemporalDecayScorerConsoleViewProps {
  nodes: TemporalEntityNodeDTO[];
  queryHits: TemporalFactHitDTO[];
  onQueryFacts: (sourceId?: string, predicate?: string) => Promise<void>;
  onSaveNode: (request: SaveEntityNodeRequestDTO) => Promise<void>;
  onDeleteNode: (nodeId: string) => Promise<void>;
}

export function TemporalDecayScorerConsoleView({
  nodes,
  queryHits,
  onQueryFacts,
  onSaveNode,
  onDeleteNode,
}: TemporalDecayScorerConsoleViewProps): React.JSX.Element {
  const [querySource, setQuerySource] = useState<string>('');
  const [queryPredicate, setQueryPredicate] = useState<string>('');
  const [isQuerying, setIsQuerying] = useState<boolean>(false);

  // New Node form states
  const [showAddNode, setShowAddNode] = useState<boolean>(false);
  const [nodeName, setNodeName] = useState<string>('');
  const [nodeType, setNodeType] = useState<string>('technology');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const handleQuerySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsQuerying(true);
    try {
      await onQueryFacts(querySource.trim() || undefined, queryPredicate.trim() || undefined);
    } finally {
      setIsQuerying(false);
    }
  };

  const handleCreateNodeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!nodeName.trim()) return;
    setIsSubmitting(true);
    try {
      await onSaveNode({
        name: nodeName.trim(),
        entity_type: nodeType,
      });
      setNodeName('');
      setShowAddNode(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="temporal-decay-scorer-console-view">
      {/* Top Grid: Half-Life Decay Query & Entity Management */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Left: Dynamic Half-life Decay Query */}
        <div className="rounded-lg border border-border/60 bg-accent/15 p-3.5 space-y-3">
          <div className="flex items-center gap-2 font-semibold text-xs text-foreground">
            <Activity className="w-4 h-4 text-primary" />
            时序半衰期动态衰减检索 (Half-Life Recency Query)
          </div>
          <p className="text-[11px] text-muted-foreground">
            根据 30 天指数半衰期公式：新鲜事实维持近 1.0 得分；历史事实平滑衰减，被取代事实降低至 0.05 惩罚分值。
          </p>

          <form onSubmit={handleQuerySubmit} className="space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label htmlFor="query-source-input" className="sr-only">
                  主体实体 ID
                </label>
                <input
                  id="query-source-input"
                  type="text"
                  value={querySource}
                  onChange={(e) => setQuerySource(e.target.value)}
                  placeholder="主体，例如：user_alice"
                  className="w-full rounded border border-border bg-background px-2.5 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label htmlFor="query-predicate-input" className="sr-only">
                  关系谓词
                </label>
                <input
                  id="query-predicate-input"
                  type="text"
                  value={queryPredicate}
                  onChange={(e) => setQueryPredicate(e.target.value)}
                  placeholder="谓词，例如：works_at"
                  className="w-full rounded border border-border bg-background px-2.5 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>
            <div className="flex justify-end">
              <Button
                type="submit"
                size="sm"
                disabled={isQuerying}
                className="text-xs focus:outline-none focus:ring-2 focus:ring-primary"
                data-testid="query-facts-button"
              >
                <Search className="w-3.5 h-3.5 mr-1" />
                {isQuerying ? '计算中...' : '发起时序探针查询'}
              </Button>
            </div>
          </form>

          {/* Hits list */}
          <div className="space-y-2 max-h-60 overflow-y-auto pr-1" data-testid="decay-query-hits-box">
            {queryHits.length === 0 ? (
              <div className="rounded border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
                暂无事实检索命中，可调整条件或重新查询
              </div>
            ) : (
              queryHits.map((hit) => (
                <div
                  key={hit.edge.edge_id}
                  className="rounded border border-border/50 bg-background/60 p-2.5 text-xs space-y-1"
                  data-testid={`decay-hit-${hit.edge.edge_id}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-foreground font-mono text-[11px]">
                      {hit.source_node.name} [{hit.edge.predicate}] {hit.target_node.name}
                    </span>
                    <div className="flex items-center gap-1.5">
                      <Badge
                        variant={hit.effective_status === 'active' ? 'default' : 'secondary'}
                        className="text-[10px]"
                      >
                        {hit.effective_status}
                      </Badge>
                      <span className="font-mono text-[11px] font-bold text-primary">
                        Score: {hit.decayed_score.toFixed(3)}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                    <span>生效时间: {hit.edge.valid_from.slice(0, 10)}</span>
                    <span>访问增益: +{(hit.edge.access_count * 0.05).toFixed(2)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right: Entity Nodes Pool */}
        <div className="rounded-lg border border-border/60 bg-accent/15 p-3.5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 font-semibold text-xs text-foreground">
              <Layers className="w-4 h-4 text-primary" />
              实体节点池 (Entity Pool - {nodes.length})
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowAddNode(!showAddNode)}
              className="text-xs h-7 gap-1 focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <Plus className="w-3 h-3" />
              {showAddNode ? '收起' : '新建实体'}
            </Button>
          </div>

          {showAddNode && (
            <form
              onSubmit={handleCreateNodeSubmit}
              className="rounded border border-primary/20 bg-background/60 p-2.5 space-y-2 text-xs"
              data-testid="add-entity-node-form"
            >
              <div>
                <label htmlFor="node-name-input" className="block text-muted-foreground mb-0.5">
                  实体名称 / 标识
                </label>
                <input
                  id="node-name-input"
                  type="text"
                  value={nodeName}
                  onChange={(e) => setNodeName(e.target.value)}
                  placeholder="例如：PostgreSQL, Rust, Beijing"
                  className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                  required
                />
              </div>
              <div className="flex items-center justify-between gap-2">
                <select
                  aria-label="实体分类类型"
                  value={nodeType}
                  onChange={(e) => setNodeType(e.target.value)}
                  className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="user">用户 (User)</option>
                  <option value="organization">企业/组织 (Organization)</option>
                  <option value="technology">技术/工具 (Technology)</option>
                  <option value="location">地理位置 (Location)</option>
                  <option value="project">项目代码仓 (Project)</option>
                </select>
                <Button
                  type="submit"
                  size="sm"
                  disabled={isSubmitting || !nodeName.trim()}
                  className="text-xs focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  {isSubmitting ? '保存中...' : '录入节点'}
                </Button>
              </div>
            </form>
          )}

          {/* Nodes list */}
          <div className="space-y-1.5 max-h-60 overflow-y-auto pr-1">
            {nodes.length === 0 ? (
              <div className="rounded border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
                暂无实体节点
              </div>
            ) : (
              nodes.map((node) => (
                <div
                  key={node.node_id}
                  className="rounded border border-border/40 bg-background/50 p-2 text-xs flex items-center justify-between"
                  data-testid={`entity-node-item-${node.node_id}`}
                >
                  <div className="flex items-center gap-2">
                    <UserCheck className="w-3.5 h-3.5 text-primary" />
                    <span className="font-medium text-foreground">{node.name}</span>
                    <Badge variant="outline" className="text-[10px]">
                      {node.entity_type}
                    </Badge>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => onDeleteNode(node.node_id)}
                    className="h-6 px-1.5 text-[11px] text-muted-foreground hover:text-destructive focus:outline-none focus:ring-2 focus:ring-destructive"
                  >
                    删除
                  </Button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
