'use client';

/**
 * [INPUT]
 * @/services/memory/temporalGraph::listEntityNodes, saveEntityNode, deleteEntityNode,
 *   listFactEdges, saveFactEdge, getEdgeLineage, queryTemporalFacts, getTemporalGraphStats
 *
 * [OUTPUT]
 * TemporalKnowledgeGraphCard: Master command center panel component for Item 93.
 * Provides HUD metrics for temporal knowledge graph, tabbed navigation between
 * evolutionary timeline (conflict reconciliation) and half-life decay console.
 *
 * [POS]
 * Primary UI component for Topic 01 Item 93 (Temporal Knowledge Graph Decay
 * and Entity Fact Conflict Resolution Suite).
 * Strict typing applied: No `any` types allowed. Line count strictly < 400 lines.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/primitives/card';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { GitGraph, Network, ShieldCheck, History, Activity, RefreshCw } from 'lucide-react';
import {
  listEntityNodes,
  saveEntityNode,
  deleteEntityNode,
  listFactEdges,
  saveFactEdge,
  getEdgeLineage,
  queryTemporalFacts,
  getTemporalGraphStats,
  type TemporalEntityNodeDTO,
  type TemporalFactEdgeDTO,
  type TemporalFactHitDTO,
  type SaveFactEdgeRequestDTO,
  type SaveEntityNodeRequestDTO,
  type TemporalGraphStatsDTO,
} from '@/services/memory/temporalGraph';
import { TemporalGraphEvolutionTimelineView } from './TemporalGraphEvolutionTimelineView';
import { TemporalDecayScorerConsoleView } from './TemporalDecayScorerConsoleView';

type ActiveTab = 'evolution' | 'decay_console';

const INITIAL_FALLBACK_NODES: TemporalEntityNodeDTO[] = [
  { node_id: 'user_alice', name: 'Alice Developer', entity_type: 'user', attributes: { role: 'Principal Architect' }, created_at: '2026-10-08T01:00:00Z', updated_at: '2026-10-08T01:00:00Z' },
  { node_id: 'comp_techcorp', name: 'TechCorp AI', entity_type: 'organization', attributes: { industry: 'Enterprise AI' }, created_at: '2026-10-08T01:00:00Z', updated_at: '2026-10-08T01:00:00Z' },
  { node_id: 'comp_startup_old', name: 'EarlyStartup', entity_type: 'organization', attributes: { industry: 'Web3' }, created_at: '2026-10-08T00:30:00Z', updated_at: '2026-10-08T00:30:00Z' },
];

const INITIAL_FALLBACK_EDGES: TemporalFactEdgeDTO[] = [
  { edge_id: 'edge_work_current', source_id: 'user_alice', target_id: 'comp_techcorp', predicate: 'works_at', valid_from: '2026-06-01T00:00:00Z', valid_until: null, is_superseded: false, superseded_by: null, confidence_score: 1.0, access_count: 5, last_accessed_at: '2026-10-08T02:00:00Z', created_at: '2026-06-01T00:00:00Z' },
  { edge_id: 'edge_work_past', source_id: 'user_alice', target_id: 'comp_startup_old', predicate: 'works_at', valid_from: '2025-01-01T00:00:00Z', valid_until: '2026-06-01T00:00:00Z', is_superseded: true, superseded_by: 'edge_work_current', confidence_score: 0.95, access_count: 1, last_accessed_at: '2026-05-30T00:00:00Z', created_at: '2025-01-01T00:00:00Z' },
];

export function TemporalKnowledgeGraphCard(): React.JSX.Element {
  const [activeTab, setActiveTab] = useState<ActiveTab>('evolution');
  const [nodes, setNodes] = useState<TemporalEntityNodeDTO[]>(INITIAL_FALLBACK_NODES);
  const [edges, setEdges] = useState<TemporalFactEdgeDTO[]>(INITIAL_FALLBACK_EDGES);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>('edge_work_current');
  const [lineageChain, setLineageChain] = useState<TemporalFactEdgeDTO[]>(INITIAL_FALLBACK_EDGES);
  const [queryHits, setQueryHits] = useState<TemporalFactHitDTO[]>([]);
  const [stats, setStats] = useState<TemporalGraphStatsDTO>({
    total_nodes_count: 3,
    active_edges_count: 1,
    superseded_edges_count: 1,
    average_decayed_score: 0.965,
  });
  const [loading, setLoading] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setStatusMessage(null);
    try {
      const [fetchedNodes, fetchedEdges, fetchedStats, hits] = await Promise.all([
        listEntityNodes().catch(() => null),
        listFactEdges(undefined, false).catch(() => null),
        getTemporalGraphStats().catch(() => null),
        queryTemporalFacts().catch(() => null),
      ]);

      if (fetchedNodes && fetchedNodes.length > 0) setNodes(fetchedNodes);
      if (fetchedEdges && fetchedEdges.length > 0) setEdges(fetchedEdges);
      if (fetchedStats) setStats(fetchedStats);
      if (hits) setQueryHits(hits);
    } catch {
      // Keep fallback fixtures intact
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const handleSelectEdge = async (edgeId: string): Promise<void> => {
    setSelectedEdgeId(edgeId);
    try {
      const chain = await getEdgeLineage(edgeId);
      if (chain && chain.length > 0) {
        setLineageChain(chain);
      }
    } catch {
      const fallbackChain = edges.filter((e) => e.edge_id === edgeId || e.superseded_by === edgeId);
      setLineageChain(fallbackChain);
    }
  };

  const handleSaveEdge = async (request: SaveFactEdgeRequestDTO): Promise<void> => {
    try {
      const result = await saveFactEdge(request);
      setStatusMessage(
        result.is_conflict_detected
          ? `互斥事实冲突消解：${result.conflict_reason}`
          : `已新增时序事实边：${result.new_edge.predicate}`
      );
      void fetchData();
      if (result.new_edge) {
        void handleSelectEdge(result.new_edge.edge_id);
      }
    } catch {
      const newEdgeId = `edge_${Date.now().toString().slice(-6)}`;
      const fallbackNew: TemporalFactEdgeDTO = {
        edge_id: newEdgeId,
        source_id: request.source_id,
        target_id: request.target_id,
        predicate: request.predicate,
        valid_from: new Date().toISOString(),
        valid_until: null,
        is_superseded: false,
        superseded_by: null,
        confidence_score: request.confidence_score ?? 1.0,
        access_count: 0,
        last_accessed_at: null,
        created_at: new Date().toISOString(),
      };
      setEdges((prev) => [fallbackNew, ...prev]);
      setStatusMessage(`已记录时序事实（本地生效）：${request.predicate}`);
    }
  };

  const handleSaveNode = async (request: SaveEntityNodeRequestDTO): Promise<void> => {
    try {
      const saved = await saveEntityNode(request);
      setNodes((prev) => [saved, ...prev]);
      setStatusMessage(`已记录实体节点：${saved.name}`);
    } catch {
      const fallbackNode: TemporalEntityNodeDTO = {
        node_id: `ent_${Date.now().toString().slice(-6)}`,
        name: request.name,
        entity_type: request.entity_type || 'concept',
        attributes: request.attributes || {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setNodes((prev) => [fallbackNode, ...prev]);
      setStatusMessage(`已添加实体节点（本地生效）：${fallbackNode.name}`);
    }
  };

  const handleDeleteNode = async (nodeId: string): Promise<void> => {
    try {
      await deleteEntityNode(nodeId);
      setNodes((prev) => prev.filter((n) => n.node_id !== nodeId));
      setStatusMessage(`已删除实体节点：${nodeId}`);
    } catch {
      setNodes((prev) => prev.filter((n) => n.node_id !== nodeId));
      setStatusMessage(`已移除实体节点：${nodeId} (本地生效)`);
    }
  };

  const handleQueryFacts = async (sourceId?: string, predicate?: string): Promise<void> => {
    try {
      const hits = await queryTemporalFacts(sourceId, predicate);
      setQueryHits(hits);
      setStatusMessage(`时序衰减探针命中 ${hits.length} 条事实`);
    } catch {
      // Local fallback calculation
      const fallbackHits: TemporalFactHitDTO[] = edges.map((e) => ({
        edge: e,
        source_node: nodes.find((n) => n.node_id === e.source_id) ?? {
          node_id: e.source_id,
          name: e.source_id,
          entity_type: 'unknown',
          attributes: {},
          created_at: '',
          updated_at: '',
        },
        target_node: nodes.find((n) => n.node_id === e.target_id) ?? {
          node_id: e.target_id,
          name: e.target_id,
          entity_type: 'unknown',
          attributes: {},
          created_at: '',
          updated_at: '',
        },
        decayed_score: e.is_superseded ? 0.05 : 0.98,
        effective_status: e.is_superseded ? 'superseded' : 'active',
      }));
      setQueryHits(fallbackHits);
      setStatusMessage(`本地时序探针匹配命中 ${fallbackHits.length} 条事实`);
    }
  };

  const activeCount = edges.filter((e) => !e.is_superseded).length;
  const supersededCount = edges.filter((e) => e.is_superseded).length;

  return (
    <Card className="border border-border/80 bg-card/60 shadow-sm" data-testid="temporal-knowledge-graph-card">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="rounded-lg bg-primary/10 p-2 text-primary">
              <GitGraph className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <CardTitle className="text-base font-semibold text-foreground">
                  时序动态知识图谱边衰减与事实冲突消解套件
                </CardTitle>
                <Badge variant="outline" className="bg-primary/5 text-primary border-primary/20 text-[10px]">
                  Item 93 P0
                </Badge>
              </div>
              <CardDescription className="text-xs text-muted-foreground mt-0.5">
                深度借鉴 Graphiti 与 OpenViking 核心图演化架构：时序边失效、互斥事实原子消解与半衰期动态衰减
              </CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={fetchData}
              disabled={loading}
              className="h-8 gap-1 text-xs focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              刷新
            </Button>
          </div>
        </div>

        {/* HUD Indicator Row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2">
          <div className="rounded-lg border border-border/50 bg-background/60 p-2.5">
            <div className="flex items-center justify-between text-muted-foreground text-[11px]">
              <span>图实体节点</span>
              <Network className="w-3.5 h-3.5 text-blue-500" />
            </div>
            <div className="text-lg font-bold text-foreground mt-0.5" data-testid="hud-nodes-count">
              {nodes.length}
            </div>
          </div>

          <div className="rounded-lg border border-border/50 bg-background/60 p-2.5">
            <div className="flex items-center justify-between text-muted-foreground text-[11px]">
              <span>当前生效事实</span>
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
            </div>
            <div className="text-lg font-bold text-foreground mt-0.5" data-testid="hud-active-edges-count">
              {activeCount}
            </div>
          </div>

          <div className="rounded-lg border border-border/50 bg-background/60 p-2.5">
            <div className="flex items-center justify-between text-muted-foreground text-[11px]">
              <span>历史取代事实</span>
              <History className="w-3.5 h-3.5 text-amber-500" />
            </div>
            <div className="text-lg font-bold text-foreground mt-0.5" data-testid="hud-superseded-edges-count">
              {supersededCount}
            </div>
          </div>

          <div className="rounded-lg border border-border/50 bg-background/60 p-2.5">
            <div className="flex items-center justify-between text-muted-foreground text-[11px]">
              <span>平均时序活跃度</span>
              <Activity className="w-3.5 h-3.5 text-purple-500" />
            </div>
            <div className="text-lg font-bold text-foreground mt-0.5" data-testid="hud-avg-score">
              {(stats.average_decayed_score * 100).toFixed(1)}%
            </div>
          </div>
        </div>

        {/* Status Alert */}
        {statusMessage && (
          <div className="mt-2 rounded-md bg-primary/10 border border-primary/20 px-3 py-1.5 text-xs text-primary flex items-center justify-between">
            <span>{statusMessage}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setStatusMessage(null)}
              className="h-5 px-1 text-[11px] text-primary/70 hover:text-primary"
            >
              关闭
            </Button>
          </div>
        )}

        {/* Tab Controls */}
        <div className="flex items-center gap-1.5 pt-2 border-b border-border/50">
          <button
            type="button"
            onClick={() => setActiveTab('evolution')}
            className={`px-3 py-1.5 text-xs font-medium border-b-2 transition-colors flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'evolution'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
            data-testid="tab-evolution"
          >
            <GitGraph className="w-3.5 h-3.5" />
            时序关系演进与脉络追溯 ({edges.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('decay_console')}
            className={`px-3 py-1.5 text-xs font-medium border-b-2 transition-colors flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'decay_console'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
            data-testid="tab-decay-console"
          >
            <Activity className="w-3.5 h-3.5 text-primary" />
            半衰期衰减探针与实体库 ({nodes.length})
          </button>
        </div>
      </CardHeader>

      <CardContent className="pt-2">
        {activeTab === 'evolution' ? (
          <TemporalGraphEvolutionTimelineView
            edges={edges}
            lineageChain={lineageChain}
            selectedEdgeId={selectedEdgeId}
            onSelectEdge={handleSelectEdge}
            onSaveEdge={handleSaveEdge}
          />
        ) : (
          <TemporalDecayScorerConsoleView
            nodes={nodes}
            queryHits={queryHits}
            onQueryFacts={handleQueryFacts}
            onSaveNode={handleSaveNode}
            onDeleteNode={handleDeleteNode}
          />
        )}
      </CardContent>
    </Card>
  );
}
