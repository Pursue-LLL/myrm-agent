/**
 * [INPUT]: TurnBilledUsageDualCountHUDProps with summary data, refresh callback, and simulate round handler.
 * [OUTPUT]: TurnBilledUsageDualCountHUD React component visualizing billed cumulative vs freeze latest cache states.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/TurnBilledUsageDualCountHUD.tsx
 */

import React, { useState } from 'react';
import { TurnBilledUsageDualCountHUDProps } from './turnUsageTypes';

export const TurnBilledUsageDualCountHUD: React.FC<TurnBilledUsageDualCountHUDProps> = ({
  summary,
  onRefresh,
  onSimulateRound,
}) => {
  const [isSimulating, setIsSimulating] = useState<boolean>(false);

  const billed = summary.billed;
  const freeze = summary.freeze_usage;

  const billedTotal =
    (billed.input_tokens || 0) +
    (billed.output_tokens || 0) +
    (billed.cache_read || 0) +
    (billed.cache_write || 0);

  const freezeTotal =
    (freeze.input_tokens || 0) +
    (freeze.output_tokens || 0) +
    (freeze.cache_read || 0) +
    (freeze.cache_write || 0);

  const handleSimulateRetry = async () => {
    if (!onSimulateRound) return;
    setIsSimulating(true);
    try {
      await onSimulateRound({
        input_tokens: 150,
        output_tokens: 200,
        cache_read: 850,
        cache_write: 0,
      });
    } finally {
      setIsSimulating(false);
    }
  };

  return (
    <div className="flex flex-col space-y-6 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
      {/* 头部标题与控制 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xl font-bold tracking-tight text-white">
              回合级使用量双计数透视 HUD (Turn Billed Usage Dual Count)
            </span>
            <span className="rounded-md border border-sky-500/30 bg-sky-500/10 px-2.5 py-0.5 font-mono text-xs font-medium text-sky-400">
              Bill 与 Freeze 物理隔离
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            解决多轮对话与单轮内再驱动（re-drive / tool loops）下“成本必须绝对累加，但缓存冻结状态绝不能累加”的核心矛盾。
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:border-zinc-500 hover:bg-zinc-800 transition"
            >
              刷新数据
            </button>
          )}
          {onSimulateRound && (
            <button
              onClick={handleSimulateRetry}
              disabled={isSimulating}
              className="rounded-lg border border-amber-600 bg-amber-950/40 px-3 py-1.5 text-xs font-medium text-amber-300 hover:bg-amber-900/60 transition disabled:opacity-50"
            >
              {isSimulating ? '模拟注入中...' : '模拟单轮再驱动 (+Round)'}
            </button>
          )}
        </div>
      </div>

      {/* 会话与回合标识 */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-zinc-800/80 bg-zinc-900/50 px-4 py-2.5 text-xs font-mono text-zinc-400">
        <div className="flex space-x-4">
          <div>
            Session: <span className="text-zinc-200">{summary.session_id}</span>
          </div>
          <div>
            Turn: <span className="text-zinc-200">{summary.turn_id}</span>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <span>物理驱动次数 (Rounds):</span>
          <span className="rounded bg-sky-950 px-2 py-0.5 font-bold text-sky-300">
            {summary.rounds_count} 轮
          </span>
        </div>
      </div>

      {/* 双计数对比大盘 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* 左栏：Billed Usage 真实账单 */}
        <div className="rounded-xl border border-rose-900/30 bg-rose-950/10 p-5">
          <div className="flex items-center justify-between border-b border-rose-900/30 pb-3">
            <div>
              <div className="font-semibold text-rose-300">
                真实账单累计 (The Bill · summed_with)
              </div>
              <div className="text-[11px] text-zinc-400 mt-0.5">
                每轮物理调用绝对累加，用于向 LLM 厂商精准结算与成本归因
              </div>
            </div>
            <span className="font-mono text-lg font-bold text-rose-200">
              {billedTotal.toLocaleString()}
            </span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
            <div className="rounded-lg bg-zinc-900/60 p-3">
              <span className="text-zinc-400">输入 Tokens (Input)</span>
              <div className="mt-1 font-mono text-base font-semibold text-white">
                {(billed.input_tokens || 0).toLocaleString()}
              </div>
            </div>
            <div className="rounded-lg bg-zinc-900/60 p-3">
              <span className="text-zinc-400">输出 Tokens (Output)</span>
              <div className="mt-1 font-mono text-base font-semibold text-white">
                {(billed.output_tokens || 0).toLocaleString()}
              </div>
            </div>
            <div className="rounded-lg bg-zinc-900/60 p-3">
              <span className="text-zinc-400">累计缓存读 (Cache Read)</span>
              <div className="mt-1 font-mono text-base font-semibold text-rose-300">
                {(billed.cache_read || 0).toLocaleString()}
              </div>
            </div>
            <div className="rounded-lg bg-zinc-900/60 p-3">
              <span className="text-zinc-400">累计缓存写 (Cache Write)</span>
              <div className="mt-1 font-mono text-base font-semibold text-rose-300">
                {(billed.cache_write || 0).toLocaleString()}
              </div>
            </div>
          </div>
        </div>

        {/* 右栏：Freeze Usage 缓存冻结决策 */}
        <div className="rounded-xl border border-emerald-900/30 bg-emerald-950/10 p-5">
          <div className="flex items-center justify-between border-b border-emerald-900/30 pb-3">
            <div>
              <div className="font-semibold text-emerald-300">
                缓存冻结状态 (The Freeze · merged_with)
              </div>
              <div className="text-[11px] text-zinc-400 mt-0.5">
                仅保留最新一次调用的缓存视图，用于上下文冻结与前缀匹配决策
              </div>
            </div>
            <span className="font-mono text-lg font-bold text-emerald-200">
              {freezeTotal.toLocaleString()}
            </span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
            <div className="rounded-lg bg-zinc-900/60 p-3">
              <span className="text-zinc-400">有效输入 (Input)</span>
              <div className="mt-1 font-mono text-base font-semibold text-white">
                {(freeze.input_tokens || 0).toLocaleString()}
              </div>
            </div>
            <div className="rounded-lg bg-zinc-900/60 p-3">
              <span className="text-zinc-400">有效输出 (Output)</span>
              <div className="mt-1 font-mono text-base font-semibold text-white">
                {(freeze.output_tokens || 0).toLocaleString()}
              </div>
            </div>
            <div className="rounded-lg bg-zinc-900/60 p-3">
              <span className="text-zinc-400">有效缓存深度 (Cache Read)</span>
              <div className="mt-1 font-mono text-base font-semibold text-emerald-300">
                {(freeze.cache_read || 0).toLocaleString()}
              </div>
            </div>
            <div className="rounded-lg bg-zinc-900/60 p-3">
              <span className="text-zinc-400">有效缓存写入 (Cache Write)</span>
              <div className="mt-1 font-mono text-base font-semibold text-emerald-300">
                {(freeze.cache_write || 0).toLocaleString()}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 差异量告警与收益说明 */}
      <div className="rounded-xl border border-indigo-900/30 bg-indigo-950/20 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-indigo-400 animate-pulse" />
            <span className="text-sm font-semibold text-indigo-200">
              防膨胀隔离保护生效中 (Anti-Inflation Shield)
            </span>
          </div>
          <div className="font-mono text-xs text-indigo-300">
            缓存虚高隔离量：
            <span className="font-bold text-indigo-100 ml-1">
              {summary.cache_divergence_tokens.toLocaleString()} Tokens
            </span>
          </div>
        </div>
        <p className="mt-2 text-xs text-zinc-400 leading-relaxed">
          若系统未做 Bill 与 Freeze 双计数分离，重试过程中的历史缓存读写将被错误叠加到当前前缀缓存中，虚假膨胀缓存深度达{' '}
          <span className="font-mono text-indigo-300 font-semibold">
            {summary.cache_divergence_tokens}
          </span>{' '}
          Tokens，进而误导后续 prompt cache 冻结判断并引发上下文断层。
        </p>
      </div>

      {/* 底部网关自适应回写保障 */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 text-xs text-zinc-400 flex items-center justify-between">
        <div>
          <span className="text-zinc-200 font-medium">网关形状自适应回写：</span>
          支持 Anthropic (<code className="font-mono text-zinc-300">cache_read_input_tokens</code>) 与 OpenAI (
          <code className="font-mono text-zinc-300">prompt_tokens_details.cached_tokens</code>) 原生键名无损透传。
        </div>
        <span className="font-mono text-[11px] text-zinc-500">
          更新于: {new Date(summary.updated_at).toLocaleTimeString()}
        </span>
      </div>
    </div>
  );
};
