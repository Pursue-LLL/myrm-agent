/**
 * [INPUT]
 * - @/services/memory/graphRrf: searchDualChannelRRF, traverseKnowledgeGraph, createEntityNode
 * - @/services/memory/graphRrf: DualChannelSearchResponse, GraphTraverseResponse, FusedMemoryHitResponse
 * - @/components/primitives: Card, Button, Badge, Input
 * - ./GraphTraversalResultView: GraphTraversalResultView
 *
 * [OUTPUT]
 * - GraphRRFRetrievalCard: React card rendering knowledge graph and dense vector dual-channel RRF retrieval console.
 *
 * [POS]
 * Personal Brain Command Center UnderstandSection card for hybrid graph-vector reciprocal rank fusion memory.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle,
  Database,
  Layers,
  Network,
  PlusCircle,
  Search,
  Share2,
  Sparkles,
} from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import { cn } from '@/lib/utils/classnameUtils';
import {
  createEntityNode,
  type DualChannelSearchResponse,
  type GraphTraverseResponse,
  searchDualChannelRRF,
  traverseKnowledgeGraph,
} from '@/services/memory/graphRrf';
import { GraphTraversalResultView } from './GraphTraversalResultView';

interface GraphRRFRetrievalCardProps {
  className?: string;
}

export function GraphRRFRetrievalCard({ className }: GraphRRFRetrievalCardProps) {
  const [query, setQuery] = useState('Titan authorization architecture');
  const [seedEntities, setSeedEntities] = useState('Alice, Project Titan');
  const [topK, setTopK] = useState('5');
  const [isSearching, setIsSearching] = useState(false);
  const [isTraversing, setIsTraversing] = useState(false);
  const [isCreatingNode, setIsCreatingNode] = useState(false);

  const [searchResponse, setSearchResponse] = useState<DualChannelSearchResponse | null>(null);
  const [traverseResponse, setTraverseResponse] = useState<GraphTraverseResponse | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Quick entity creation form state
  const [newEntityId, setNewEntityId] = useState('');
  const [newEntityName, setNewEntityName] = useState('');
  const [newEntityType, setNewEntityType] = useState('CONCEPT');

  const handleDualSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    setStatusMessage(null);
    try {
      const parsedSeeds = seedEntities
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      const res = await searchDualChannelRRF({
        query: query.trim(),
        seed_entity_names: parsedSeeds.length > 0 ? parsedSeeds : undefined,
        top_k: parseInt(topK, 10) || 5,
      });
      setSearchResponse(res);
      setStatusMessage(`双通道 RRF 检索完成：共融合召回 ${res.total_hits} 条记忆项`);
    } catch {
      setStatusMessage('双通道 RRF 混合检索执行失败');
    } finally {
      setIsSearching(false);
    }
  };

  const handleTraverse = async () => {
    const parsedSeeds = seedEntities
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);

    if (parsedSeeds.length === 0) {
      setStatusMessage('请先在种子实体输入框中输入至少一个实体名称或 ID');
      return;
    }

    setIsTraversing(true);
    setStatusMessage(null);
    try {
      const res = await traverseKnowledgeGraph({
        seed_entity_ids: parsedSeeds,
        max_hops: 2,
      });
      setTraverseResponse(res);
      setStatusMessage(`BFS 拓扑遍历完成：触达 ${res.nodes.length} 个节点，发现 ${res.paths.length} 条多跳路径`);
    } catch {
      setStatusMessage('知识图谱拓扑遍历执行失败');
    } finally {
      setIsTraversing(false);
    }
  };

  const handleCreateEntity = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEntityId.trim() || !newEntityName.trim()) return;

    setIsCreatingNode(true);
    setStatusMessage(null);
    try {
      const created = await createEntityNode({
        id: newEntityId.trim(),
        name: newEntityName.trim(),
        entity_type: newEntityType.trim(),
      });
      setStatusMessage(`实体节点 [${created.name}] (${created.id}) 创建成功`);
      setNewEntityId('');
      setNewEntityName('');
    } catch {
      setStatusMessage('创建实体节点失败');
    } finally {
      setIsCreatingNode(false);
    }
  };

  return (
    <Card className={cn('border-border/60 bg-card shadow-sm', className)}>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Share2 className="h-5 w-5 text-cyan-500" />
            <CardTitle className="text-base font-semibold">
              知识图谱与语义向量双路检索 RRF 融合引擎 (Graph-Vector RRF)
            </CardTitle>
          </div>
          <div className="flex items-center gap-1.5">
            <Badge variant="outline" className="border-cyan-500/40 text-cyan-600 dark:text-cyan-400">
              gbrain 架构演进
            </Badge>
            <Badge variant="outline" className="border-border/70 text-muted-foreground">
              RRF 倒数排名融合
            </Badge>
          </div>
        </div>
        <CardDescription className="text-xs">
          对标 gbrain commit 5cfb84f1：打破单一向量检索在多跳实体因果链条上的召回盲区，
          通过本地 SQLite 实体关系图谱拓扑展开与语义向量双路协同召回，并以无参数 RRF 公式融合评分。
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 pt-1">
        {/* Search Console Form */}
        <form onSubmit={handleDualSearch} className="space-y-2 rounded-lg border border-border/70 bg-card p-3 shadow-xs">
          <div className="flex flex-wrap items-center gap-2">
            <div className="min-w-[240px] flex-1">
              <label
                htmlFor="graph-rrf-query"
                className="mb-1 block text-[11px] font-medium text-muted-foreground"
              >
                自然语言检索词 (Query)
              </label>
              <Input
                id="graph-rrf-query"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="例如: Titan authorization architecture"
                className="h-8 text-xs"
              />
            </div>
            <div className="min-w-[180px] flex-1">
              <label
                htmlFor="graph-rrf-seeds"
                className="mb-1 block text-[11px] font-medium text-muted-foreground"
              >
                锚定种子实体 (逗号分隔)
              </label>
              <Input
                id="graph-rrf-seeds"
                value={seedEntities}
                onChange={(e) => setSeedEntities(e.target.value)}
                placeholder="例如: Alice, Project Titan"
                className="h-8 text-xs"
              />
            </div>
            <div className="w-20">
              <label
                htmlFor="graph-rrf-topk"
                className="mb-1 block text-[11px] font-medium text-muted-foreground"
              >
                Top-K
              </label>
              <Input
                id="graph-rrf-topk"
                type="number"
                min="1"
                max="20"
                value={topK}
                onChange={(e) => setTopK(e.target.value)}
                className="h-8 text-xs"
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
            <div className="flex items-center gap-2">
              <Button
                type="submit"
                size="sm"
                disabled={isSearching || !query.trim()}
                className="h-8 gap-1 text-xs"
              >
                <Search className={cn('h-3.5 w-3.5', isSearching && 'animate-spin')} />
                双通道 RRF 混合检索
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleTraverse}
                disabled={isTraversing}
                className="h-8 gap-1 text-xs"
              >
                <Network className={cn('h-3.5 w-3.5', isTraversing && 'animate-spin')} />
                拓扑关系展开 (BFS)
              </Button>
            </div>
          </div>
        </form>

        {/* Fused Memory Hits Results */}
        {searchResponse && (
          <div className="rounded-lg border border-border/70 bg-card p-3 shadow-xs">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                <Sparkles className="h-4 w-4 text-cyan-500" />
                <span>RRF 融合召回记忆清单 ({searchResponse.results.length})</span>
              </div>
              <span className="text-[11px] text-muted-foreground">
                查询: &quot;{searchResponse.query}&quot;
              </span>
            </div>

            {searchResponse.results.length === 0 ? (
              <div className="rounded border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
                未检索到匹配的图谱或向量记忆
              </div>
            ) : (
              <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
                {searchResponse.results.map((hit) => (
                  <div
                    key={hit.memory_id}
                    className="rounded border border-border/50 bg-accent/15 p-2.5 text-xs transition hover:bg-accent/25"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <Database className="h-3.5 w-3.5 text-cyan-400" />
                          <span className="font-mono text-[11px] font-semibold text-foreground">
                            {hit.memory_id}
                          </span>
                          {hit.hit_sources.map((src) => (
                            <Badge
                              key={src}
                              variant="outline"
                              className={cn(
                                'px-1.5 py-0 text-[9px]',
                                src === 'vector'
                                  ? 'border-indigo-400 text-indigo-500'
                                  : 'border-cyan-400 text-cyan-500',
                              )}
                            >
                              {src}
                            </Badge>
                          ))}
                        </div>
                        <p className="mt-1 line-clamp-2 text-muted-foreground">
                          {hit.content}
                        </p>
                      </div>
                      <div className="shrink-0 text-right text-[10px] text-muted-foreground">
                        <div>
                          融合分: <strong className="text-cyan-600 dark:text-cyan-400">{hit.fused_score.toFixed(4)}</strong>
                        </div>
                        <div>
                          向量排名: {hit.vector_rank ? `#${hit.vector_rank}` : '未召回'} | 图谱排名: {hit.graph_rank ? `#${hit.graph_rank}` : '未召回'}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Traversal Explorer Result View */}
        {traverseResponse && (
          <div className="rounded-lg border border-border/70 bg-card p-3 shadow-xs">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <Network className="h-4 w-4 text-cyan-500" />
              <span>知识图谱拓扑探索视野</span>
            </div>
            <GraphTraversalResultView traversal={traverseResponse} />
          </div>
        )}

        {/* Quick Entity Creation Panel */}
        <details className="rounded-lg border border-border/50 bg-muted/20 p-2 text-xs">
          <summary className="cursor-pointer font-medium text-muted-foreground hover:text-foreground">
            + 快速登记知识图谱实体节点
          </summary>
          <form onSubmit={handleCreateEntity} className="mt-2.5 flex flex-wrap items-center gap-2">
            <Input
              value={newEntityId}
              onChange={(e) => setNewEntityId(e.target.value)}
              placeholder="实体 ID (例如 person:alice)"
              className="h-8 min-w-[140px] flex-1 text-xs"
            />
            <Input
              value={newEntityName}
              onChange={(e) => setNewEntityName(e.target.value)}
              placeholder="实体名称 (例如 Alice)"
              className="h-8 min-w-[140px] flex-1 text-xs"
            />
            <Input
              value={newEntityType}
              onChange={(e) => setNewEntityType(e.target.value)}
              placeholder="类型 (PERSON/PROJECT/MODULE)"
              className="h-8 w-36 text-xs"
            />
            <Button
              type="submit"
              size="sm"
              disabled={isCreatingNode || !newEntityId.trim() || !newEntityName.trim()}
              className="h-8 gap-1 text-xs"
            >
              <PlusCircle className={cn('h-3.5 w-3.5', isCreatingNode && 'animate-spin')} />
              注册节点
            </Button>
          </form>
        </details>

        {/* Status Notification */}
        {statusMessage && (
          <div className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            {statusMessage.includes('失败') ? (
              <AlertTriangle className="h-4 w-4 text-destructive" />
            ) : (
              <CheckCircle className="h-4 w-4 text-cyan-500" />
            )}
            <span>{statusMessage}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
