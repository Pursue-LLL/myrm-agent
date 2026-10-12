/**
 * [INPUT]
 * Props: totalPeers, totalEdges, totalInteractions, avgTokenCost, refreshing, onRefresh, onToggleNewPeer
 *
 * [OUTPUT]
 * PeerCognitionHudBar React component presenting 4-dimensional telemetry metrics for Item 110.
 *
 * [POS]
 * HUD metric bar inside PeerCognitionStudioCard.
 * Strict typing applied: No `any` types allowed. Accessible buttons with focus rings. Single file < 200 lines.
 */

import React from 'react';
import {
  Users,
  GitFork,
  Activity,
  Cpu,
  RefreshCw,
  UserPlus,
} from 'lucide-react';

export interface PeerCognitionHudBarProps {
  totalPeers: number;
  totalEdges: number;
  totalInteractions: number;
  avgTokenCost: number;
  refreshing: boolean;
  onRefresh: () => void;
  onToggleNewPeer: () => void;
}

export const PeerCognitionHudBar: React.FC<PeerCognitionHudBarProps> = ({
  totalPeers,
  totalEdges,
  totalInteractions,
  avgTokenCost,
  refreshing,
  onRefresh,
  onToggleNewPeer,
}) => {
  return (
    <aside
      aria-label="社会认知实体遥测指标状态栏"
      className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-muted/40 p-3 rounded-lg border border-border"
    >
      {/* 1. 注册参与者实体总数 */}
      <div className="flex items-center gap-3 bg-card/60 p-2.5 rounded-md border border-border/50">
        <div className="p-2 rounded bg-primary/10 text-primary">
          <Users className="w-4 h-4" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground font-medium">常驻参与者 Peer</div>
          <div className="text-sm font-semibold tracking-tight text-foreground">
            {totalPeers} <span className="text-xs font-normal text-muted-foreground">位实体</span>
          </div>
        </div>
      </div>

      {/* 2. 跨实体语义关系边数 */}
      <div className="flex items-center gap-3 bg-card/60 p-2.5 rounded-md border border-border/50">
        <div className="p-2 rounded bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
          <GitFork className="w-4 h-4" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground font-medium">社会认知关联拓扑</div>
          <div className="text-sm font-semibold tracking-tight text-foreground">
            {totalEdges} <span className="text-xs font-normal text-muted-foreground">条语义边</span>
          </div>
        </div>
      </div>

      {/* 3. 累计协作交互频次 */}
      <div className="flex items-center gap-3 bg-card/60 p-2.5 rounded-md border border-border/50">
        <div className="p-2 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
          <Activity className="w-4 h-4" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground font-medium">自演化交互反馈</div>
          <div className="text-sm font-semibold tracking-tight text-foreground">
            {totalInteractions}{' '}
            <span className="text-xs font-normal text-muted-foreground">次协作积累</span>
          </div>
        </div>
      </div>

      {/* 4. 上下文投影平均 Token 开销与操作区 */}
      <div className="flex items-center justify-between bg-card/60 p-2.5 rounded-md border border-border/50">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400">
            <Cpu className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs text-muted-foreground font-medium">Prompt 上下文投影</div>
            <div className="text-sm font-semibold tracking-tight text-foreground">
              ~{avgTokenCost} <span className="text-xs font-normal text-muted-foreground">Tokens</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
            title="刷新 Peer 实体图谱与画像卡"
            aria-label="刷新 Peer 实体图谱"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={onToggleNewPeer}
            className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
            title="登记新参与者 Peer 实体"
            aria-label="登记新参与者 Peer 实体"
          >
            <UserPlus className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
};
