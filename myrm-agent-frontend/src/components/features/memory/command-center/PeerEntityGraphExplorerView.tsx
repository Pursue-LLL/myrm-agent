/**
 * [INPUT]
 * Props: peers, edges, onAddEdge, onSelectPeer
 *
 * [OUTPUT]
 * PeerEntityGraphExplorerView: Visual relationship topology and cognitive edges browser.
 *
 * [POS]
 * Primary interactive view in PeerCognitionStudioCard for Item 110.
 * Anchors facts and decisions to accountable peer participants instead of isolated tables.
 * Strict typing applied: No `any` types allowed. Accessible form with htmlFor bindings. Single file < 380 lines.
 */

import React, { useState } from 'react';
import {
  Share2,
  Plus,
  ShieldCheck,
  User,
  Bot,
  Box,
  ArrowRight,
  Filter,
} from 'lucide-react';
import type {
  AddRelationEdgeRequest,
  PeerIdentityDTO,
  PeerRelationEdgeDTO,
  PeerRelationKind,
  PeerType,
} from '@/services/memory/peerCognition';
import { AddRelationEdgeForm } from './AddRelationEdgeForm';

export interface PeerEntityGraphExplorerViewProps {
  peers: PeerIdentityDTO[];
  edges: PeerRelationEdgeDTO[];
  onAddEdge: (request: AddRelationEdgeRequest) => Promise<void>;
  onSelectPeer: (peerId: string) => void;
}

export const PeerEntityGraphExplorerView: React.FC<PeerEntityGraphExplorerViewProps> = ({
  peers,
  edges,
  onAddEdge,
  onSelectPeer,
}) => {
  const [filterType, setFilterType] = useState<string>('all');
  const [showAddForm, setShowAddForm] = useState<boolean>(false);

  const filteredPeers = peers.filter((p) => {
    if (filterType === 'all') return true;
    return p.peer_type === filterType;
  });

  const getPeerIcon = (type: PeerType) => {
    switch (type) {
      case 'user_peer':
        return <User className="w-3.5 h-3.5 text-primary" />;
      case 'agent_peer':
        return <Bot className="w-3.5 h-3.5 text-blue-500" />;
      case 'reviewer_peer':
        return <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />;
      case 'project_peer':
        return <Box className="w-3.5 h-3.5 text-amber-500" />;
    }
  };

  const getRelationBadgeClass = (kind: PeerRelationKind) => {
    switch (kind) {
      case 'asserts':
        return 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20';
      case 'approves':
        return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20';
      case 'collaborates_with':
        return 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20';
      case 'governs':
        return 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20';
      case 'depends_on':
        return 'bg-muted text-muted-foreground border-border';
    }
  };

  return (
    <div className="space-y-4">
      {/* 顶部操作与实体分类筛选 */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-card/60 rounded-lg border border-border">
        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-foreground">参与者分类:</span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setFilterType('all')}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                filterType === 'all'
                  ? 'bg-primary text-primary-foreground font-medium'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              全部 ({peers.length})
            </button>
            <button
              type="button"
              onClick={() => setFilterType('user_peer')}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                filterType === 'user_peer'
                  ? 'bg-primary text-primary-foreground font-medium'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              用户
            </button>
            <button
              type="button"
              onClick={() => setFilterType('agent_peer')}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                filterType === 'agent_peer'
                  ? 'bg-primary text-primary-foreground font-medium'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              智能体
            </button>
            <button
              type="button"
              onClick={() => setFilterType('reviewer_peer')}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                filterType === 'reviewer_peer'
                  ? 'bg-primary text-primary-foreground font-medium'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              审计者
            </button>
            <button
              type="button"
              onClick={() => setFilterType('project_peer')}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                filterType === 'project_peer'
                  ? 'bg-primary text-primary-foreground font-medium'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              项目实体
            </button>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-muted hover:bg-muted/80 text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>{showAddForm ? '收起关联表单' : '新增认知关系边'}</span>
        </button>
      </div>

      {/* 新增关系边抽屉表单 */}
      {showAddForm && (
        <AddRelationEdgeForm
          peers={peers}
          onAddEdge={async (req) => {
            await onAddEdge(req);
            setShowAddForm(false);
          }}
          onCancel={() => setShowAddForm(false)}
        />
      )}

      {/* 实体卡片列表与关联拓扑边浏览 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 左侧：参与者 Peer 实体库 */}
        <div className="space-y-2.5">
          <div className="text-xs font-semibold text-foreground flex items-center justify-between">
            <span>参与者实体库 ({filteredPeers.length})</span>
            <span className="text-[11px] text-muted-foreground font-normal">点击查看常驻画像卡</span>
          </div>

          <div className="space-y-2">
            {filteredPeers.map((peer) => (
              <button
                key={peer.peer_id}
                type="button"
                onClick={() => onSelectPeer(peer.peer_id)}
                className="w-full text-left p-3 rounded-lg border border-border bg-card/60 hover:border-primary/50 transition-all focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 rounded bg-muted/80">
                      {getPeerIcon(peer.peer_type)}
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-foreground">
                        {peer.display_name}
                      </div>
                      <div className="text-[11px] text-muted-foreground font-mono">
                        @{peer.peer_id}
                      </div>
                    </div>
                  </div>
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-muted text-muted-foreground border border-border">
                    {peer.peer_type}
                  </span>
                </div>

                {peer.role_title && (
                  <div className="mt-2 text-[11px] text-muted-foreground line-clamp-1">
                    职责: {peer.role_title}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* 右侧：社会认知语义边拓扑 */}
        <div className="lg:col-span-2 space-y-2.5">
          <div className="text-xs font-semibold text-foreground flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Share2 className="w-3.5 h-3.5 text-primary" />
              <span>当前社会认知拓扑边 ({edges.length})</span>
            </div>
            <span className="text-[11px] text-muted-foreground font-normal">
              记忆可追溯：谁主张、谁审批、谁协作、谁管辖
            </span>
          </div>

          <div className="space-y-2.5">
            {edges.length === 0 ? (
              <div className="p-8 text-center text-xs text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
                暂无社会认知关系边
              </div>
            ) : (
              edges.map((edge) => {
                const sourcePeer = peers.find((p) => p.peer_id === edge.source_peer_id);
                return (
                  <div
                    key={edge.edge_id}
                    className="p-3 rounded-lg border border-border bg-card/60 space-y-2 hover:border-border/80 transition-all"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-foreground">
                          {sourcePeer?.display_name || edge.source_peer_id}
                        </span>
                        <ArrowRight className="w-3 h-3 text-muted-foreground" />
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-medium border ${getRelationBadgeClass(
                            edge.relation_kind,
                          )}`}
                        >
                          {edge.relation_kind}
                        </span>
                        <ArrowRight className="w-3 h-3 text-muted-foreground" />
                        <span className="font-mono text-xs text-foreground bg-muted/50 px-1.5 py-0.5 rounded">
                          {edge.target_entity_id}
                        </span>
                      </div>

                      <span className="text-[11px] text-muted-foreground">
                        权重: {Math.round(edge.weight * 100)}%
                      </span>
                    </div>

                    {edge.context_note && (
                      <p className="text-xs text-muted-foreground bg-muted/30 p-2 rounded leading-relaxed">
                        {edge.context_note}
                      </p>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
