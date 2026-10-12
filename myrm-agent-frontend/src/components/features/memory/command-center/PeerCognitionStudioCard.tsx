/**
 * [INPUT]
 * @/services/memory/peerCognition (Client functions and DTOs)
 * ./PeerCognitionHudBar
 * ./PeerEntityGraphExplorerView
 * ./PeerPersonaCardStudioView
 * ./peerCognitionFallbacks
 *
 * [OUTPUT]
 * PeerCognitionStudioCard: Main command-center panel for Item 110.
 *
 * [POS]
 * Command-center card for Peer-Centric Entity Graph and Agent Persona Card Suite.
 * Strict typing applied: No `any` types allowed. Accessible markup. Single file < 380 lines.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Users,
  GitFork,
  IdCard,
  UserPlus,
  AlertCircle,
} from 'lucide-react';
import {
  listPeerIdentities,
  getPersonaCard,
  registerPeerIdentity,
  addRelationEdge,
  updatePersonaCard,
  recordInteractionEvent,
  getEdgesForPeer,
  generatePromptProjection,
  type AddRelationEdgeRequest,
  type GenerateProjectionRequest,
  type PeerCognitionProjectionDTO,
  type PeerIdentityDTO,
  type PeerPersonaCardDTO,
  type PeerRelationEdgeDTO,
  type PeerType,
  type RecordInteractionRequest,
  type RegisterPeerRequest,
  type UpdatePersonaCardRequest,
} from '@/services/memory/peerCognition';
import { PeerCognitionHudBar } from './PeerCognitionHudBar';
import { PeerEntityGraphExplorerView } from './PeerEntityGraphExplorerView';
import { PeerPersonaCardStudioView } from './PeerPersonaCardStudioView';
import { RegisterPeerFormView } from './RegisterPeerFormView';
import {
  FALLBACK_PEERS,
  FALLBACK_CARDS,
  FALLBACK_EDGES,
  FALLBACK_PROJECTION,
} from './peerCognitionFallbacks';

type ActiveTab = 'graph' | 'persona' | 'register';

export const PeerCognitionStudioCard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('graph');
  const [peers, setPeers] = useState<PeerIdentityDTO[]>(FALLBACK_PEERS);
  const [activePeerId, setActivePeerId] = useState<string>(FALLBACK_PEERS[0].peer_id);
  const [cards, setCards] = useState<Record<string, PeerPersonaCardDTO>>(FALLBACK_CARDS);
  const [edges, setEdges] = useState<PeerRelationEdgeDTO[]>(FALLBACK_EDGES);
  const [projection, setProjection] = useState<PeerCognitionProjectionDTO | null>(FALLBACK_PROJECTION);
  const [loading, setLoading] = useState<boolean>(false);
  const [bannerMessage, setBannerMessage] = useState<string | null>(null);
  const [registering, setRegistering] = useState<boolean>(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const fetchedPeers = await listPeerIdentities();
      if (fetchedPeers && fetchedPeers.length > 0) {
        setPeers(fetchedPeers);
        // Load cards and edges for first peer
        const firstId = fetchedPeers[0].peer_id;
        setActivePeerId(firstId);
        const [card, peerEdges] = await Promise.all([
          getPersonaCard(firstId),
          getEdgesForPeer(firstId),
        ]);
        if (card) {
          setCards((prev) => ({ ...prev, [firstId]: card }));
        }
        if (peerEdges && peerEdges.length > 0) {
          setEdges(peerEdges);
        }
      }
    } catch {
      // 离线平滑降级
      setPeers(FALLBACK_PEERS);
      setCards(FALLBACK_CARDS);
      setEdges(FALLBACK_EDGES);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSelectPeer = async (peerId: string) => {
    setActivePeerId(peerId);
    try {
      const [card, peerEdges] = await Promise.all([
        getPersonaCard(peerId),
        getEdgesForPeer(peerId),
      ]);
      if (card) {
        setCards((prev) => ({ ...prev, [peerId]: card }));
      }
      if (peerEdges && peerEdges.length > 0) {
        setEdges(peerEdges);
      }
    } catch {
      // 保持本地已加载状态
    }
  };

  const handleAddEdge = async (req: AddRelationEdgeRequest) => {
    try {
      const newEdge = await addRelationEdge(req);
      setEdges((prev) => [newEdge, ...prev]);
      setBannerMessage(`关系边 ${newEdge.edge_id} 已成功写入社会认知图谱`);
      setTimeout(() => setBannerMessage(null), 3000);
    } catch {
      const fallbackEdge: PeerRelationEdgeDTO = {
        edge_id: req.edge_id,
        source_peer_id: req.source_peer_id,
        target_entity_id: req.target_entity_id,
        target_is_peer: req.target_is_peer || false,
        relation_kind: req.relation_kind || 'asserts',
        context_note: req.context_note || '',
        weight: req.weight || 1.0,
        created_at: new Date().toISOString(),
      };
      setEdges((prev) => [fallbackEdge, ...prev]);
      setBannerMessage('已本地更新认知关系边');
      setTimeout(() => setBannerMessage(null), 3000);
    }
  };

  const handleUpdateCard = async (peerId: string, req: UpdatePersonaCardRequest) => {
    try {
      const updated = await updatePersonaCard(peerId, req);
      setCards((prev) => ({ ...prev, [peerId]: updated }));
      setBannerMessage(`Peer ${peerId} 画像卡已更新`);
      setTimeout(() => setBannerMessage(null), 3000);
    } catch {
      setCards((prev) => {
        const cur = prev[peerId] || FALLBACK_CARDS[peerId];
        return {
          ...prev,
          [peerId]: {
            ...cur,
            ...req,
            core_responsibilities: req.core_responsibilities || cur.core_responsibilities,
            standing_preferences: req.standing_preferences || cur.standing_preferences,
            updated_at: new Date().toISOString(),
          },
        };
      });
      setBannerMessage('已本地保存画像卡变更');
      setTimeout(() => setBannerMessage(null), 3000);
    }
  };

  const handleRecordInteraction = async (peerId: string, req: RecordInteractionRequest) => {
    try {
      const evolved = await recordInteractionEvent(peerId, req);
      setCards((prev) => ({ ...prev, [peerId]: evolved }));
      setBannerMessage(`Peer ${peerId} 交互反馈已演化 (信任度: ${Math.round(evolved.trust_score * 100)}%)`);
      setTimeout(() => setBannerMessage(null), 3000);
    } catch {
      setCards((prev) => {
        const cur = prev[peerId] || FALLBACK_CARDS[peerId];
        const nextInteractions = cur.interaction_count + 1;
        const nextSuccessRate = req.success
          ? cur.success_rate * 0.9 + 0.1
          : cur.success_rate * 0.8;
        return {
          ...prev,
          [peerId]: {
            ...cur,
            interaction_count: nextInteractions,
            success_rate: nextSuccessRate,
            trust_score: Math.min(1.0, nextSuccessRate * 0.9 + 0.1),
            updated_at: new Date().toISOString(),
          },
        };
      });
      setBannerMessage('已在本地模拟交互演化');
      setTimeout(() => setBannerMessage(null), 3000);
    }
  };

  const handleGenerateProjection = async (peerIds: string[]) => {
    try {
      const proj = await generatePromptProjection({ peer_ids: peerIds });
      setProjection(proj);
      setBannerMessage(`成功生成 ${proj.targeted_peers.length} 位 Peer 上下文投影 (~${proj.token_cost_estimate} Tokens)`);
      setTimeout(() => setBannerMessage(null), 3000);
    } catch {
      setProjection(FALLBACK_PROJECTION);
      setBannerMessage('已使用基线数据编译低Token上下文投影');
      setTimeout(() => setBannerMessage(null), 3000);
    }
  };

  const handleRegisterPeer = async (req: RegisterPeerRequest) => {
    setRegistering(true);
    try {
      const newPeer = await registerPeerIdentity(req);
      setPeers((prev) => [...prev, newPeer]);
      setBannerMessage(`成功登记新参与者 Peer: ${newPeer.display_name}`);
      setActiveTab('persona');
      setActivePeerId(newPeer.peer_id);
    } catch {
      const fallbackPeer: PeerIdentityDTO = {
        peer_id: req.peer_id,
        peer_type: req.peer_type,
        display_name: req.display_name,
        role_title: req.role_title || '',
        avatar_or_icon: 'user',
        created_at: new Date().toISOString(),
        last_seen_at: new Date().toISOString(),
      };
      setPeers((prev) => [...prev, fallbackPeer]);
      setBannerMessage('已在本地记录新参与者 Peer');
      setActiveTab('persona');
      setActivePeerId(fallbackPeer.peer_id);
    } finally {
      setRegistering(false);
    }
  };

  const totalInteractions = Object.values(cards).reduce(
    (acc, c) => acc + c.interaction_count,
    0,
  );
  const avgTokenCost = projection ? projection.token_cost_estimate : 78;

  return (
    <div
      aria-label="社会认知实体图谱与常驻画像卡控制台"
      className="rounded-xl border border-border bg-card p-5 space-y-4 shadow-sm"
    >
      {/* 头部标题区 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <Users className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-foreground tracking-tight">
                社会认知实体图谱与常驻画像卡中枢
              </h2>
              <span className="px-2 py-0.5 text-[11px] font-medium rounded-full bg-primary/10 text-primary border border-primary/20">
                Item 110 · P0
              </span>
              <span className="px-2 py-0.5 text-[11px] font-medium rounded-full bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
                对标 Hermes+Honcho · 参与者社会认知
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              记忆以 Peer 参与者为中心组织，绑定结论提出者与审阅归属，常驻紧凑画像卡自演化与多智能体角色对齐
            </p>
          </div>
        </div>

        {/* 顶部 Tab 导航 */}
        <nav
          aria-label="社会认知视图选项卡"
          className="flex items-center gap-1 bg-muted p-1 rounded-lg text-xs"
        >
          <button
            type="button"
            aria-label="切换至实体图谱拓扑"
            onClick={() => setActiveTab('graph')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'graph'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <GitFork className="w-3.5 h-3.5" />
            <span>实体图谱拓扑 ({edges.length})</span>
          </button>
          <button
            type="button"
            aria-label="切换至常驻画像卡管理"
            onClick={() => setActiveTab('persona')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'persona'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <IdCard className="w-3.5 h-3.5" />
            <span>常驻画像卡与角色对齐 ({peers.length})</span>
          </button>
          <button
            type="button"
            aria-label="切换至登记新参与者"
            onClick={() => setActiveTab('register')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'register'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <UserPlus className="w-3.5 h-3.5" />
            <span>登记新参与者</span>
          </button>
        </nav>
      </div>

      {/* 4 维 HUD 遥测监控条 */}
      <PeerCognitionHudBar
        totalPeers={peers.length}
        totalEdges={edges.length}
        totalInteractions={totalInteractions}
        avgTokenCost={avgTokenCost}
        refreshing={loading}
        onRefresh={loadData}
        onToggleNewPeer={() => setActiveTab('register')}
      />

      {/* 状态通知条 */}
      {bannerMessage && (
        <div className="flex items-center gap-2 p-2.5 rounded-md bg-primary/10 border border-primary/20 text-xs text-primary">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          <span>{bannerMessage}</span>
        </div>
      )}

      {/* 视图分发 */}
      {activeTab === 'graph' && (
        <PeerEntityGraphExplorerView
          peers={peers}
          edges={edges}
          onAddEdge={handleAddEdge}
          onSelectPeer={(pid) => {
            handleSelectPeer(pid);
            setActiveTab('persona');
          }}
        />
      )}

      {activeTab === 'persona' && (
        <PeerPersonaCardStudioView
          peers={peers}
          activePeerId={activePeerId}
          cards={cards}
          onSelectPeer={handleSelectPeer}
          onUpdateCard={handleUpdateCard}
          onRecordInteraction={handleRecordInteraction}
          onGenerateProjection={handleGenerateProjection}
          projection={projection}
        />
      )}

      {activeTab === 'register' && (
        <RegisterPeerFormView
          onRegister={handleRegisterPeer}
          registering={registering}
        />
      )}
    </div>
  );
};
