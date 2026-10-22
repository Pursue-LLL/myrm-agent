/**
 * [INPUT]: RateLimitSourceSplitHUDProps containing partitioned metrics, totals, and event records.
 * [OUTPUT]: RateLimitSourceSplitHUD React component visualizing myrm vs upstream 429 splits, provider failure attribution, and totals consistency.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/RateLimitSourceSplitHUD.tsx
 */

import React, { useState } from 'react';
import {
  FailureEventItem,
  RateLimitEventItem,
  RateLimitSourceSplitHUDProps,
} from './rateLimitSplitTypes';

export const RateLimitSourceSplitHUD: React.FC<RateLimitSourceSplitHUDProps> = ({
  data,
  onRefresh,
  onReset,
  isRefreshing = false,
}) => {
  const [isResetting, setIsResetting] = useState<boolean>(false);
  const [selectedTab, setSelectedTab] = useState<'events' | 'failures'>('events');

  const myrmCount = data.rate_limited_by_source['myrm'] || 0;
  const upstreamCount = data.rate_limited_by_source['upstream'] || 0;
  const totalRateLimited = data.total_rate_limited || 0;

  const myrmPct = totalRateLimited > 0 ? ((myrmCount / totalRateLimited) * 100).toFixed(1) : '0.0';
  const upstreamPct =
    totalRateLimited > 0 ? ((upstreamCount / totalRateLimited) * 100).toFixed(1) : '0.0';

  const handleReset = async () => {
    if (!onReset) return;
    setIsResetting(true);
    try {
      await onReset();
    } finally {
      setIsResetting(false);
    }
  };

  const providerFailureEntries = Object.entries(data.failed_by_provider || {});

  return (
    <div className="flex flex-col space-y-6 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
      {/* 头部导航与操作 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xl font-bold tracking-tight text-white">
              限流来源拆分与失败归因 HUD (Rate Limit Source Split)
            </span>
            <span className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 font-mono text-xs font-medium text-amber-400">
              429 归因防扯皮
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            细分内部治理限流 (myrm) 与上游服务商配额拒绝 (upstream)，按厂商归因错误，未打标总数严格对齐防口径漂移
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={isRefreshing}
              className="inline-flex items-center rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-200 transition-colors hover:bg-zinc-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            >
              {isRefreshing ? '正在刷新...' : '刷新指标'}
            </button>
          )}

          {onReset && (
            <button
              type="button"
              onClick={handleReset}
              disabled={isResetting}
              className="inline-flex items-center rounded-lg border border-rose-800/40 bg-rose-950/20 px-3 py-1.5 text-xs font-medium text-rose-300 transition-colors hover:bg-rose-900/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            >
              {isResetting ? '重置中...' : '重置计数器'}
            </button>
          )}
        </div>
      </div>

      {/* 核心指标统计卡片 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/60 p-4">
          <span className="text-xs font-medium text-zinc-400">请求总数 (Requests)</span>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-mono text-2xl font-bold text-white">{data.total_requests}</span>
            <span className="text-xs text-zinc-500">已完成: {data.total_completed}</span>
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/60 p-4">
          <span className="text-xs font-medium text-amber-400">429 限流总数 (Rate Limited)</span>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-mono text-2xl font-bold text-amber-300">
              {data.total_rate_limited}
            </span>
            <span className="font-mono text-xs text-amber-500/80">未打标口径不变</span>
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/60 p-4">
          <span className="text-xs font-medium text-rose-400">失败总数 (Requests Failed)</span>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-mono text-2xl font-bold text-rose-300">{data.total_failed}</span>
            <span className="font-mono text-xs text-rose-500/80">非 429 报错</span>
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/60 p-4">
          <span className="text-xs font-medium text-emerald-400">
            总数对齐校验 (Totals Consistency)
          </span>
          <div className="mt-2 flex items-center justify-between">
            <span
              className={`inline-flex items-center rounded px-2 py-0.5 font-mono text-xs font-semibold ${
                data.totals_consistent
                  ? 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
                  : 'border border-rose-500/30 bg-rose-500/10 text-rose-400'
              }`}
            >
              {data.totals_consistent ? '100% 对齐严格一致' : '⚠️ 检测到口径漂移'}
            </span>
            <span className="text-xs text-zinc-500">防 Prometheus 误差</span>
          </div>
        </div>
      </div>

      {/* 429 来源双规拆分对比 & 提供商失败分布 */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* 429 来源拆分 */}
        <div className="flex flex-col rounded-lg border border-zinc-800 bg-zinc-900/40 p-5">
          <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
            <span className="text-sm font-semibold text-white">429 来源拆分 (By Source)</span>
            <span className="text-xs text-zinc-400">myrm vs upstream</span>
          </div>

          <div className="mt-4 space-y-4">
            <div>
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center space-x-2 text-cyan-300">
                  <span className="h-2 w-2 rounded-full bg-cyan-400" />
                  <span>Myrm 本地治理限流 (myrm)</span>
                </span>
                <span className="font-mono font-bold text-zinc-200">
                  {myrmCount} 次 ({myrmPct}%)
                </span>
              </div>
              <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-zinc-800">
                <div
                  className="h-full bg-cyan-500 transition-all duration-300"
                  style={{ width: `${myrmPct}%` }}
                />
              </div>
              <p className="mt-1 text-[11px] text-zinc-500">
                触发本地客户端并发保护阀或 Token 燃速阶梯限流，建议调大客户端最大并发或微调等待时延
              </p>
            </div>

            <div>
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center space-x-2 text-amber-300">
                  <span className="h-2 w-2 rounded-full bg-amber-400" />
                  <span>上游厂商拒绝 (upstream)</span>
                </span>
                <span className="font-mono font-bold text-zinc-200">
                  {upstreamCount} 次 ({upstreamPct}%)
                </span>
              </div>
              <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-zinc-800">
                <div
                  className="h-full bg-amber-500 transition-all duration-300"
                  style={{ width: `${upstreamPct}%` }}
                />
              </div>
              <p className="mt-1 text-[11px] text-zinc-500">
                外部提供商官方 API 返回 HTTP 429，属于账号层额度不足或 TPM 触顶，建议配置多 Provider 故障转移
              </p>
            </div>
          </div>
        </div>

        {/* 提供商失败归因 */}
        <div className="flex flex-col rounded-lg border border-zinc-800 bg-zinc-900/40 p-5">
          <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
            <span className="text-sm font-semibold text-white">
              非 429 报错提供商归因 (Failed By Provider)
            </span>
            <span className="text-xs text-zinc-400">含预置 unknown 桶</span>
          </div>

          <div className="mt-4 flex-1 space-y-3 overflow-y-auto max-h-[160px]">
            {providerFailureEntries.length === 0 ? (
              <div className="flex h-24 items-center justify-center text-xs text-zinc-500">
                暂无服务商报错记录
              </div>
            ) : (
              providerFailureEntries.map(([provider, count]) => (
                <div
                  key={provider}
                  className="flex items-center justify-between rounded-md border border-zinc-800/50 bg-zinc-950/60 px-3 py-2 text-xs"
                >
                  <span className="font-mono text-zinc-300">{provider}</span>
                  <div className="flex items-center space-x-2">
                    <span className="font-mono font-bold text-rose-400">{count} 失败</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* 审计流水抽屉 / Tab 页 */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
        <div className="flex items-center space-x-4 border-b border-zinc-800 pb-3 text-xs">
          <button
            type="button"
            onClick={() => setSelectedTab('events')}
            className={`font-semibold pb-1 transition-colors ${
              selectedTab === 'events'
                ? 'border-b-2 border-amber-400 text-amber-300'
                : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            最近 429 限流记录 ({data.recent_rate_limit_events?.length || 0})
          </button>
          <button
            type="button"
            onClick={() => setSelectedTab('failures')}
            className={`font-semibold pb-1 transition-colors ${
              selectedTab === 'failures'
                ? 'border-b-2 border-rose-400 text-rose-300'
                : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            最近请求报错记录 ({data.recent_failure_events?.length || 0})
          </button>
        </div>

        <div className="mt-3 max-h-56 overflow-y-auto space-y-2">
          {selectedTab === 'events' ? (
            data.recent_rate_limit_events && data.recent_rate_limit_events.length > 0 ? (
              data.recent_rate_limit_events.map((event: RateLimitEventItem, idx: number) => (
                <div
                  key={`${event.timestamp_ms}-${idx}`}
                  className="flex flex-wrap items-center justify-between rounded border border-zinc-800/80 bg-zinc-950/60 p-2 text-xs"
                >
                  <div className="flex items-center space-x-2">
                    <span
                      className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-bold ${
                        event.source === 'myrm'
                          ? 'border border-cyan-500/30 bg-cyan-500/10 text-cyan-300'
                          : 'border border-amber-500/30 bg-amber-500/10 text-amber-300'
                      }`}
                    >
                      {event.source.toUpperCase()}
                    </span>
                    <span className="font-mono text-zinc-300">{event.provider}</span>
                    <span className="font-mono text-zinc-500">{event.model}</span>
                  </div>
                  <span className="text-[11px] text-zinc-400">{event.reason || '无详情'}</span>
                </div>
              ))
            ) : (
              <div className="py-4 text-center text-xs text-zinc-500">暂无 429 限流记录</div>
            )
          ) : data.recent_failure_events && data.recent_failure_events.length > 0 ? (
            data.recent_failure_events.map((fail: FailureEventItem, idx: number) => (
              <div
                key={`${fail.timestamp_ms}-${idx}`}
                className="flex flex-wrap items-center justify-between rounded border border-zinc-800/80 bg-zinc-950/60 p-2 text-xs"
              >
                <div className="flex items-center space-x-2">
                  <span className="rounded border border-rose-500/30 bg-rose-500/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-rose-300">
                    {fail.error_code}
                  </span>
                  <span className="font-mono text-zinc-300">{fail.provider}</span>
                  <span className="font-mono text-zinc-500">{fail.model}</span>
                </div>
                <span className="text-[11px] text-zinc-400">{fail.reason || '无详情'}</span>
              </div>
            ))
          ) : (
            <div className="py-4 text-center text-xs text-zinc-500">暂无错误报错记录</div>
          )}
        </div>
      </div>
    </div>
  );
};
