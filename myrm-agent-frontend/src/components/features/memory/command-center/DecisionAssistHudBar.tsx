/**
 * Proactive Past-Pitfall Alert 4-Dimensional Telemetry HUD Bar.
 * Visualizes live protection health, seeded failure postmortems, session mutes, and sub-millisecond latency.
 */

import React from 'react';
import { ShieldCheck, Database, BellOff, Zap } from 'lucide-react';
import { PitfallAlertStatusResponse } from '@/services/memory/decisionAssist';

interface DecisionAssistHudBarProps {
  status: PitfallAlertStatusResponse;
  lastLatencyMs?: number;
  activeSessionId: string;
}

export const DecisionAssistHudBar: React.FC<DecisionAssistHudBarProps> = ({
  status,
  lastLatencyMs,
  activeSessionId,
}) => {
  return (
    <header className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-card/60 border border-border/80 rounded-xl p-3.5 backdrop-blur-sm shadow-xs">
      {/* Metric 1: Protection Sentinel Status */}
      <div className="flex items-center gap-2.5 p-2 rounded-lg bg-background/50 border border-border/40">
        <div className="p-2 rounded-md bg-emerald-500/10 text-emerald-500">
          <ShieldCheck className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-muted-foreground">决策防护哨兵</div>
          <output aria-live="polite" className="text-sm font-semibold tracking-tight text-foreground block">
            {status.active ? '全天候实时守护' : '已暂停'}
          </output>
        </div>
      </div>

      {/* Metric 2: Seeded Failure Postmortems */}
      <div className="flex items-center gap-2.5 p-2 rounded-lg bg-background/50 border border-border/40">
        <div className="p-2 rounded-md bg-amber-500/10 text-amber-500">
          <Database className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-muted-foreground">已录入踩坑教训</div>
          <output aria-live="polite" className="text-sm font-semibold tracking-tight text-foreground block">
            {status.seeded_triads_count} 条因果三元组
          </output>
        </div>
      </div>

      {/* Metric 3: Session Mute Counter */}
      <div className="flex items-center gap-2.5 p-2 rounded-lg bg-background/50 border border-border/40">
        <div className="p-2 rounded-md bg-sky-500/10 text-sky-500">
          <BellOff className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-muted-foreground">会话静音范围</div>
          <output aria-live="polite" className="text-sm font-semibold tracking-tight text-foreground block">
            {status.muted_sessions_count > 0 ? `${status.muted_sessions_count} 项静音白名单` : '0 打扰拦截'}
          </output>
        </div>
      </div>

      {/* Metric 4: Sniffing Latency */}
      <div className="flex items-center gap-2.5 p-2 rounded-lg bg-background/50 border border-border/40">
        <div className="p-2 rounded-md bg-indigo-500/10 text-indigo-500">
          <Zap className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-muted-foreground">影子嗅探延迟</div>
          <output aria-live="polite" className="text-sm font-semibold tracking-tight text-foreground block">
            {lastLatencyMs !== undefined ? `${lastLatencyMs.toFixed(2)} ms` : '< 0.50 ms'}
          </output>
        </div>
      </div>
    </header>
  );
};
