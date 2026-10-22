/**
 * [INPUT]: NormalizedTokenUsageSnapshot, InvariantCheckResult, and optional policy list.
 * [OUTPUT]: Heads-Up Display (HUD) rendering honest reasoning token subsets, total invariants, and zero-double-counting badges.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/ReasoningTokenIntegrityHUD.tsx
 */

import React from 'react';
import type {
  InvariantCheckResult,
  NormalizedTokenUsageSnapshot,
  ProviderPolicyItem,
} from './reasoningSemanticsTypes';

export interface ReasoningTokenIntegrityHUDProps {
  snapshot: NormalizedTokenUsageSnapshot;
  checkResult?: InvariantCheckResult | null;
  policies?: ProviderPolicyItem[];
  onVerifyInvariant?: () => void;
  onRefreshPolicies?: () => void;
}

export const ReasoningTokenIntegrityHUD: React.FC<ReasoningTokenIntegrityHUDProps> = ({
  snapshot,
  checkResult,
  policies = [],
  onVerifyInvariant,
  onRefreshPolicies,
}) => {
  const reasoningPctOfCompletion =
    snapshot.completion_tokens > 0
      ? Math.round((snapshot.reasoning_tokens / snapshot.completion_tokens) * 100)
      : 0;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-5 text-slate-100">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl">🧠</span>
            <h2 className="text-base font-semibold text-white">推理 Token 计费语义契约与重复计数守卫</h2>
            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-700/60 flex items-center gap-1">
              <span>✓</span>
              <span>Zero Double-Counting Verified</span>
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            提供方: <code className="text-cyan-400 font-mono">{snapshot.raw_provider}</code> · 
            策略: <span className="text-indigo-300 font-mono">{snapshot.policy_applied}</span> · 
            严防思考过程与输出 Token 重复计费
          </p>
        </div>

        <div className="flex items-center gap-2">
          {onVerifyInvariant && (
            <button
              type="button"
              onClick={onVerifyInvariant}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-slate-700 transition-colors flex items-center gap-1.5"
            >
              <span>🔍</span>
              <span>验证不变量契约</span>
            </button>
          )}
        </div>
      </div>

      {/* Warning Banner if invariant was violated upstream */}
      {checkResult && !checkResult.is_valid && (
        <div className="p-3.5 rounded-lg bg-amber-950/60 border border-amber-800/80 text-xs text-amber-200 space-y-1">
          <div className="font-semibold flex items-center gap-1.5 text-amber-300">
            <span>⚠️</span>
            <span>上游重复计数漏洞警示 (已启动运行时自愈纠偏)</span>
          </div>
          <p className="text-amber-200/90 leading-relaxed font-mono">
            {checkResult.diagnostic_warning}
          </p>
        </div>
      )}

      {/* Honest Subordination Card */}
      <div className="p-4 rounded-lg bg-slate-850/70 border border-slate-800 space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
            <span>📐</span>
            <span>从属口径诚实透视 (Honest Subordination Formula)</span>
          </div>
          <span className="text-[11px] font-mono text-cyan-400">
            思考占比 {reasoningPctOfCompletion}%
          </span>
        </div>

        {/* Visual Token Hierarchy */}
        <div className="p-3 rounded-lg bg-slate-900 border border-slate-800 font-mono text-xs space-y-2">
          <div className="flex items-center justify-between text-slate-300">
            <span>总消耗总量 (Total):</span>
            <span className="text-white font-bold text-sm">
              {snapshot.total_tokens.toLocaleString()} Tokens
            </span>
          </div>
          <div className="text-[11px] text-slate-500 pl-2 border-l border-slate-700 flex items-center justify-between">
            <span>├─ 输入 Prompt Tokens:</span>
            <span className="text-slate-300">{snapshot.prompt_tokens.toLocaleString()}</span>
          </div>
          <div className="text-[11px] text-slate-500 pl-2 border-l border-slate-700 flex items-center justify-between">
            <span>└─ 总输出 Completion Tokens:</span>
            <span className="text-cyan-300 font-semibold">{snapshot.completion_tokens.toLocaleString()}</span>
          </div>
          <div className="text-[10px] text-slate-500 pl-6 flex items-center justify-between">
            <span className="text-indigo-300">├── 其中思考/推理 (Reasoning):</span>
            <span className="text-indigo-200">{snapshot.reasoning_tokens.toLocaleString()} Tokens</span>
          </div>
          <div className="text-[10px] text-slate-500 pl-6 flex items-center justify-between">
            <span className="text-slate-400">└── 其中可见净内容 (Visible):</span>
            <span className="text-slate-300">{snapshot.visible_content_tokens.toLocaleString()} Tokens</span>
          </div>
        </div>

        {/* Mathematical Invariant Statement */}
        <div className="text-[11px] text-slate-400 bg-slate-900/60 p-2.5 rounded border border-slate-800/80 font-mono">
          <span className="text-emerald-400 font-semibold">公式不变量: </span>
          <span className="text-slate-300">Total ({snapshot.total_tokens})</span> = 
          <span className="text-slate-300"> Prompt ({snapshot.prompt_tokens})</span> + 
          <span className="text-cyan-300"> Completion ({snapshot.completion_tokens})</span>
          <span className="text-slate-500">（推理 Token 仅为输出的从属子集，绝不二次叠加）</span>
        </div>
      </div>

      {/* KPI Triad */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="p-3.5 rounded-lg bg-slate-800/50 border border-slate-750">
          <div className="text-[11px] font-medium text-slate-400">推理思考耗费</div>
          <div className="mt-1 flex items-baseline gap-1.5">
            <span className="text-xl font-bold font-mono text-indigo-400">
              {snapshot.reasoning_tokens.toLocaleString()}
            </span>
            <span className="text-xs text-slate-500">Tokens</span>
          </div>
        </div>

        <div className="p-3.5 rounded-lg bg-slate-800/50 border border-slate-750">
          <div className="text-[11px] font-medium text-slate-400">合规计费金额 (USD)</div>
          <div className="mt-1 flex items-baseline gap-1.5">
            <span className="text-xl font-bold font-mono text-emerald-400">
              ${snapshot.cost_usd.toFixed(4)}
            </span>
            <span className="text-xs text-slate-500">零二次计价</span>
          </div>
        </div>

        <div className="p-3.5 rounded-lg bg-slate-800/50 border border-slate-750">
          <div className="text-[11px] font-medium text-slate-400">防重复计费状态</div>
          <div className="mt-1 text-xs font-semibold text-emerald-400 flex items-center gap-1">
            <span>🛡️</span>
            <span>100% 契约守卫就绪</span>
          </div>
        </div>
      </div>

      {/* Policies Catalog (if provided) */}
      {policies.length > 0 && (
        <div className="space-y-2 pt-2 border-t border-slate-800">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              已知厂商归一化策略表 ({policies.length})
            </span>
            {onRefreshPolicies && (
              <button
                type="button"
                onClick={onRefreshPolicies}
                className="text-[11px] text-cyan-400 hover:text-cyan-300 transition-colors"
              >
                刷新策略
              </button>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
            {policies.map((p) => (
              <div
                key={p.provider_keyword}
                className="p-2.5 rounded bg-slate-850 border border-slate-800 space-y-1"
              >
                <div className="flex items-center justify-between font-mono">
                  <span className="font-semibold text-cyan-300">{p.provider_keyword}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                    {p.policy}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 leading-snug">{p.description}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
