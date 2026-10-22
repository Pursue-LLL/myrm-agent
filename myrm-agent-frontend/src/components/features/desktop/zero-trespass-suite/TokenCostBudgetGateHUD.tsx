import React from 'react';
import {
  AlertOctagon,
  CheckCircle2,
  Coins,
  Cpu,
  Key,
  Lock,
  ShieldAlert,
  ShieldCheck,
  Timer,
  Zap,
} from 'lucide-react';
import { useZeroTrespassStore } from './useZeroTrespassStore';

interface TokenCostBudgetGateHUDProps {
  className?: string;
}

export const TokenCostBudgetGateHUD: React.FC<TokenCostBudgetGateHUDProps> = ({
  className = '',
}) => {
  const {
    costBudget,
    physicalTelemetry,
    isByokActive,
    confirmBudgetGate,
    toggleByok,
  } = useZeroTrespassStore();

  const isHighCost = costBudget.estimatedCostUsd >= costBudget.thresholdUsd;
  const isBlockedByGate = isHighCost && !costBudget.isGateConfirmed;

  return (
    <section
      aria-label="Token成本预算沙盒与真实模型防降级遥测"
      className={`rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow-sm backdrop-blur ${className}`}
    >
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <Coins className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100">全链路 Token 成本预算与真实物理模型遥测</h3>
            <p className="text-[11px] text-slate-400">
              拒绝暗箱扣费与廉价模型暗降 · 超过 ${costBudget.thresholdUsd.toFixed(2)} 触发确认闸门
            </p>
          </div>
        </div>

        {/* BYOK 自带 Key 开关 */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">
            {isByokActive ? 'BYOK 自带 Key 零加价直通' : '平台标准通道'}
          </span>
          <button
            type="button"
            onClick={() => {
              toggleByok();
            }}
            className={`flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium border transition-colors ${
              isByokActive
                ? 'bg-indigo-600 text-white border-indigo-500'
                : 'bg-slate-800 text-slate-300 border-slate-700 hover:text-white'
            }`}
            aria-label="切换 BYOK 自带 Key 模式"
          >
            <Key className="w-3 h-3" />
            <span>{isByokActive ? 'BYOK 已启用' : '启用自带 Key'}</span>
          </button>
        </div>
      </div>

      {/* 预估与实耗成本指标 */}
      <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
          <div className="text-[11px] text-slate-400 mb-1">事前预估 Token</div>
          <div className="font-mono text-sm font-semibold text-slate-200">
            {costBudget.estimatedTokens.toLocaleString()} tokens
          </div>
        </div>

        <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
          <div className="text-[11px] text-slate-400 mb-1">事前预估成本</div>
          <div className="font-mono text-sm font-semibold text-emerald-400">
            ${costBudget.estimatedCostUsd.toFixed(4)} USD
          </div>
        </div>

        <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
          <div className="text-[11px] text-slate-400 mb-1">实际结算 Token</div>
          <div className="font-mono text-sm font-semibold text-slate-200">
            {costBudget.actualTokensUsed.toLocaleString()} tokens
          </div>
        </div>

        <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
          <div className="text-[11px] text-slate-400 mb-1">实际扣费</div>
          <div className="font-mono text-sm font-semibold text-sky-400">
            ${costBudget.actualCostUsd.toFixed(4)} USD
          </div>
        </div>
      </div>

      {/* 真实物理模型防降级遥测徽章 */}
      <div className="mt-3 p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2">
          <Cpu className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
          <span className="text-slate-400">真实物理模型 ID:</span>
          <span className="font-mono font-medium text-slate-200">
            {physicalTelemetry.physicalModelId}
          </span>
          <span className="text-[10px] text-slate-500 font-mono">
            ({physicalTelemetry.provider})
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 text-[11px] text-slate-400 font-mono">
            <Timer className="w-3 h-3 text-sky-400" />
            <span>{physicalTelemetry.latencyMs}ms</span>
          </div>

          {physicalTelemetry.isDowngradeDetected ? (
            <span className="flex items-center gap-1 rounded bg-rose-500/10 px-2 py-0.5 text-[11px] font-mono text-rose-400 border border-rose-500/20">
              <ShieldAlert className="w-3 h-3" />
              <span>检测到模型暗降告警！</span>
            </span>
          ) : (
            <span className="flex items-center gap-1 rounded bg-emerald-500/10 px-2 py-0.5 text-[11px] font-mono text-emerald-400 border border-emerald-500/20">
              <ShieldCheck className="w-3 h-3" />
              <span>物理模型验签一致 (无偷梁换柱)</span>
            </span>
          )}
        </div>
      </div>

      {/* 高消耗确认闸门触发时的交互卡片 */}
      {isBlockedByGate && (
        <div className="mt-3 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-amber-300">
            <AlertOctagon className="w-4 h-4 shrink-0 text-amber-400" />
            <span>
              本次长任务预估消耗 (${costBudget.estimatedCostUsd.toFixed(2)}) 超过预设闸门 (${costBudget.thresholdUsd.toFixed(2)})，需您确认后执行。
            </span>
          </div>

          <button
            type="button"
            onClick={() => {
              confirmBudgetGate();
            }}
            className="shrink-0 flex items-center gap-1 rounded-md bg-amber-600 hover:bg-amber-500 text-white px-3 py-1 text-xs font-semibold shadow-sm transition-colors"
            aria-label="确认高消耗预算并继续执行"
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>确认预算并放行</span>
          </button>
        </div>
      )}
    </section>
  );
};
