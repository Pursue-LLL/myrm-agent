import React from 'react';
import {
  TrendingUp,
  Flame,
  CheckCircle2,
  ShieldCheck,
  RefreshCw,
  GitMerge,
} from 'lucide-react';
import { useFleetObserverStore } from './useFleetObserverStore';

export interface FleetDeliberationGaugesProps {
  className?: string;
}

export function FleetDeliberationGauges({ className = '' }: FleetDeliberationGaugesProps) {
  const metrics = useFleetObserverStore((s) => s.metrics);
  const nodes = useFleetObserverStore((s) => s.nodes);

  const totalCurrentBurnRate = nodes.reduce((sum, n) => sum + n.tokenBurnRate, 0);

  return (
    <section
      aria-label="反闲聊会商收敛度与Token燃烧速率仪表盘"
      className={`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 select-none ${className}`}
    >
      {/* 卡片 1: 会商收敛度 */}
      <div className="p-4 rounded-xl border border-border bg-card shadow-xs space-y-2">
        <div className="flex items-center justify-between text-muted-foreground text-xs">
          <span className="font-semibold">会商收敛度指数</span>
          <GitMerge className="w-4 h-4 text-primary" />
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold tracking-tight text-foreground font-mono">
            {metrics.convergenceScore}%
          </span>
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
              metrics.status === 'converged'
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                : 'bg-primary/10 text-primary'
            }`}
          >
            {metrics.status === 'converged' ? '达成共识' : '多方收敛中'}
          </span>
        </div>
        <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
          <div
            className="bg-primary h-full transition-all duration-500"
            style={{ width: `${metrics.convergenceScore}%` }}
          />
        </div>
      </div>

      {/* 卡片 2: 反闲聊冗余度量 */}
      <div className="p-4 rounded-xl border border-border bg-card shadow-xs space-y-2">
        <div className="flex items-center justify-between text-muted-foreground text-xs">
          <span className="font-semibold">反闲聊冗余比率</span>
          <ShieldCheck className="w-4 h-4 text-emerald-500" />
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold tracking-tight text-foreground font-mono">
            {(metrics.redundancyRatio * 100).toFixed(1)}%
          </span>
          <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">
            极低噪音 (已阻断闲聊)
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-snug">
          各节点交互均由工单与形式化契约约束，拒绝无休止发散。
        </p>
      </div>

      {/* 卡片 3: 实时 Token 燃烧速率 */}
      <div className="p-4 rounded-xl border border-border bg-card shadow-xs space-y-2">
        <div className="flex items-center justify-between text-muted-foreground text-xs">
          <span className="font-semibold">Token 实时燃烧速率</span>
          <Flame className="w-4 h-4 text-amber-500" />
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold tracking-tight text-foreground font-mono">
            {totalCurrentBurnRate}
          </span>
          <span className="text-xs text-muted-foreground font-mono">tok/s</span>
        </div>
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span>累计消耗:</span>
          <span className="font-mono font-medium text-foreground">
            {metrics.totalTokenBurn.toLocaleString()} tok
          </span>
        </div>
      </div>

      {/* 卡片 4: 协同轮次与节奏 */}
      <div className="p-4 rounded-xl border border-border bg-card shadow-xs space-y-2">
        <div className="flex items-center justify-between text-muted-foreground text-xs">
          <span className="font-semibold">协同交互轮次</span>
          <RefreshCw className="w-4 h-4 text-sky-500" />
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold tracking-tight text-foreground font-mono">
            Round {metrics.activeRounds}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
          <span>契约驱动自主步进中</span>
        </div>
      </div>
    </section>
  );
}
