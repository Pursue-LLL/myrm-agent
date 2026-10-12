/**
 * [INPUT]
 * Props: peers, activePeerId, cards, onSelectPeer, onUpdateCard, onRecordInteraction, onGenerateProjection, projection
 *
 * [OUTPUT]
 * PeerPersonaCardStudioView: Curated standing persona card inspector, role alignment, and prompt projection generator.
 *
 * [POS]
 * Secondary interactive view in PeerCognitionStudioCard for Item 110.
 * Eliminates unowned memory drift by maintaining lightweight, self-evolving standing Peer Cards (<150 words).
 * Strict typing applied: No `any` types allowed. Accessible form with htmlFor bindings. Single file < 380 lines.
 */

import React, { useState } from 'react';
import {
  IdCard,
  Sparkles,
  Sliders,
  CheckCircle2,
  XCircle,
  Copy,
  Terminal,
  Activity,
  Send,
} from 'lucide-react';
import type {
  PeerCognitionProjectionDTO,
  PeerIdentityDTO,
  PeerPersonaCardDTO,
  RecordInteractionRequest,
  UpdatePersonaCardRequest,
} from '@/services/memory/peerCognition';

export interface PeerPersonaCardStudioViewProps {
  peers: PeerIdentityDTO[];
  activePeerId: string;
  cards: Record<string, PeerPersonaCardDTO>;
  onSelectPeer: (peerId: string) => void;
  onUpdateCard: (peerId: string, req: UpdatePersonaCardRequest) => Promise<void>;
  onRecordInteraction: (peerId: string, req: RecordInteractionRequest) => Promise<void>;
  onGenerateProjection: (peerIds: string[]) => Promise<void>;
  projection: PeerCognitionProjectionDTO | null;
}

export const PeerPersonaCardStudioView: React.FC<PeerPersonaCardStudioViewProps> = ({
  peers,
  activePeerId,
  cards,
  onSelectPeer,
  onUpdateCard,
  onRecordInteraction,
  onGenerateProjection,
  projection,
}) => {
  const [evolving, setEvolving] = useState<boolean>(false);
  const [projecting, setProjecting] = useState<boolean>(false);
  const [copiedProjection, setCopiedProjection] = useState<boolean>(false);
  const [newPreferenceK, setNewPreferenceK] = useState<string>('');
  const [newPreferenceV, setNewPreferenceV] = useState<string>('');

  const currentCard = cards[activePeerId] || {
    peer_id: activePeerId,
    peer_type: 'user_peer',
    display_name: activePeerId,
    core_responsibilities: ['通用任务协同'],
    decision_style: 'balanced',
    standing_preferences: {},
    interaction_count: 0,
    success_rate: 1.0,
    trust_score: 1.0,
    summary_digest: '暂无常驻摘要',
    updated_at: new Date().toISOString(),
  };

  const handleSimulateInteraction = async (success: boolean) => {
    setEvolving(true);
    try {
      await onRecordInteraction(activePeerId, {
        success,
        preference_deltas:
          newPreferenceK && newPreferenceV
            ? { [newPreferenceK.trim()]: newPreferenceV.trim() }
            : undefined,
      });
      setNewPreferenceK('');
      setNewPreferenceV('');
    } finally {
      setEvolving(false);
    }
  };

  const handleAddPreference = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPreferenceK.trim() || !newPreferenceV.trim()) return;

    const updatedPrefs = {
      ...currentCard.standing_preferences,
      [newPreferenceK.trim()]: newPreferenceV.trim(),
    };
    await onUpdateCard(activePeerId, {
      standing_preferences: updatedPrefs,
    });
    setNewPreferenceK('');
    setNewPreferenceV('');
  };

  const handleGenerateProjection = async () => {
    setProjecting(true);
    try {
      await onGenerateProjection(peers.map((p) => p.peer_id));
    } finally {
      setProjecting(false);
    }
  };

  const handleCopyProjection = () => {
    if (!projection?.formatted_prompt_block) return;
    navigator.clipboard.writeText(projection.formatted_prompt_block);
    setCopiedProjection(true);
    setTimeout(() => setCopiedProjection(false), 2000);
  };

  return (
    <div className="space-y-4">
      {/* 顶部 Peer 选择器 */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-card/60 rounded-lg border border-border">
        <div className="flex items-center gap-2">
          <IdCard className="w-3.5 h-3.5 text-primary" />
          <span className="text-xs font-medium text-foreground">切换查看参与者 Peer Card:</span>
          <div className="flex flex-wrap items-center gap-1.5">
            {peers.map((p) => (
              <button
                key={p.peer_id}
                type="button"
                onClick={() => onSelectPeer(p.peer_id)}
                className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                  activePeerId === p.peer_id
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground hover:text-foreground'
                }`}
              >
                {p.display_name}
              </button>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={handleGenerateProjection}
          disabled={projecting}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
        >
          <Sparkles className={`w-3.5 h-3.5 ${projecting ? 'animate-spin' : ''}`} />
          <span>{projecting ? '编译中...' : '生成低Token上下文投影'}</span>
        </button>
      </div>

      {/* Peer Card 主检视面板 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 左侧：精选画像卡详情 */}
        <div className="lg:col-span-2 space-y-4">
          <div className="p-4 bg-card rounded-lg border border-border space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold text-foreground">
                    {currentCard.display_name}
                  </h3>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground border border-border">
                    @{currentCard.peer_id}
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] bg-primary/10 text-primary border border-primary/20">
                    {currentCard.peer_type}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  更新时间: {currentCard.updated_at.slice(0, 19).replace('T', ' ')}
                </p>
              </div>

              <div className="flex items-center gap-3 text-xs">
                <div>
                  <span className="text-muted-foreground">信任度: </span>
                  <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                    {Math.round(currentCard.trust_score * 100)}%
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">协作胜率: </span>
                  <span className="font-semibold text-foreground">
                    {Math.round(currentCard.success_rate * 100)}%
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">交互: </span>
                  <span className="font-semibold text-foreground font-mono">
                    {currentCard.interaction_count} 次
                  </span>
                </div>
              </div>
            </div>

            {/* 核心职责明确化 */}
            <div className="space-y-1.5">
              <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5 text-primary" />
                <span>明确职责边界 (Role Alignment)</span>
              </div>
              <ul className="space-y-1 text-xs text-muted-foreground">
                {currentCard.core_responsibilities.map((resp) => (
                  <li key={resp} className="flex items-start gap-1.5">
                    <span className="text-primary font-bold">•</span>
                    <span>{resp}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* 决策风格 */}
            <div className="space-y-1">
              <div className="text-xs font-semibold text-foreground">决策风格与容差偏好</div>
              <p className="text-xs font-mono text-muted-foreground bg-muted/40 p-2 rounded">
                {currentCard.decision_style}
              </p>
            </div>

            {/* 常驻偏好字典 */}
            <div className="space-y-2">
              <div className="text-xs font-semibold text-foreground flex items-center justify-between">
                <span>常驻偏好字典 (Standing Preferences)</span>
                <span className="text-[11px] text-muted-foreground">持久化事实键值对</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {Object.entries(currentCard.standing_preferences).map(([k, v]) => (
                  <div
                    key={k}
                    className="p-2 rounded bg-muted/40 border border-border/50 text-xs space-y-0.5"
                  >
                    <div className="font-mono text-primary font-medium">{k}</div>
                    <div className="text-muted-foreground text-[11px] line-clamp-2">{v}</div>
                  </div>
                ))}
              </div>

              {/* 快速添加偏好表单 */}
              <form onSubmit={handleAddPreference} className="flex items-center gap-2 pt-1">
                <label htmlFor="pref-key-input" className="sr-only">
                  偏好项名
                </label>
                <input
                  id="pref-key-input"
                  type="text"
                  placeholder="偏好名 (如 type_hints)"
                  value={newPreferenceK}
                  onChange={(e) => setNewPreferenceK(e.target.value)}
                  className="px-2.5 py-1 text-xs bg-background rounded border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground"
                />
                <label htmlFor="pref-val-input" className="sr-only">
                  偏好设定值
                </label>
                <input
                  id="pref-val-input"
                  type="text"
                  placeholder="偏好内容 (如 严禁 Any)"
                  value={newPreferenceV}
                  onChange={(e) => setNewPreferenceV(e.target.value)}
                  className="flex-1 px-2.5 py-1 text-xs bg-background rounded border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground"
                />
                <button
                  type="submit"
                  disabled={!newPreferenceK.trim() || !newPreferenceV.trim()}
                  className="px-3 py-1 rounded text-xs font-medium bg-muted hover:bg-muted/80 text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
                >
                  添加
                </button>
              </form>
            </div>

            {/* 自然语言精要摘要 */}
            <div className="space-y-1">
              <div className="text-xs font-semibold text-foreground">
                自然语言浓缩摘要 (Digest &lt;150 words)
              </div>
              <p className="text-xs text-muted-foreground italic bg-muted/20 p-2.5 rounded border border-border/40 leading-relaxed">
                {currentCard.summary_digest}
              </p>
            </div>
          </div>
        </div>

        {/* 右侧：交互自演化模拟与 Prompt 投影 */}
        <div className="space-y-4">
          {/* 1. 交互自演化模拟器 */}
          <div className="p-4 bg-card rounded-lg border border-border space-y-3">
            <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-emerald-500" />
              <span>协同交互自演化反馈</span>
            </div>
            <p className="text-xs text-muted-foreground">
              模拟协作任务执行结果，动态自演化该 Peer 的信任度与胜率加权指标：
            </p>

            <div className="flex items-center gap-2 pt-1">
              <button
                type="button"
                disabled={evolving}
                onClick={() => handleSimulateInteraction(true)}
                className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-medium bg-emerald-600 text-white hover:bg-emerald-700 transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>协作成功 (+胜率)</span>
              </button>

              <button
                type="button"
                disabled={evolving}
                onClick={() => handleSimulateInteraction(false)}
                className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-medium bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
              >
                <XCircle className="w-3.5 h-3.5" />
                <span>协作偏差 (-信任)</span>
              </button>
            </div>
          </div>

          {/* 2. 低 Token 上下文投影 */}
          <div className="p-4 bg-card rounded-lg border border-border space-y-3">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <Terminal className="w-3.5 h-3.5 text-primary" />
                <span>Prompt 上下文投影预览</span>
              </div>
              {projection && (
                <span className="text-[11px] font-mono text-emerald-600 dark:text-emerald-400">
                  ~{projection.token_cost_estimate} Tokens
                </span>
              )}
            </div>

            {projection?.formatted_prompt_block ? (
              <div className="space-y-2">
                <div className="relative group">
                  <pre className="p-2.5 rounded bg-background border border-border text-xs font-mono text-muted-foreground overflow-x-auto max-h-56 leading-relaxed">
                    <code>{projection.formatted_prompt_block}</code>
                  </pre>
                  <button
                    type="button"
                    onClick={handleCopyProjection}
                    className="absolute top-2 right-2 p-1.5 rounded bg-muted/80 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
                    title="复制提示词投影"
                    aria-label="复制提示词投影"
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                </div>

                {copiedProjection && (
                  <div className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium">
                    已复制投影提示词至剪贴板
                  </div>
                )}
              </div>
            ) : (
              <div className="p-6 text-center text-xs text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
                点击上方“生成低Token上下文投影”查看当前所有 Peer 的常驻认知注入切片
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
