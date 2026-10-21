/**
 * [INPUT]: Itemized metric cardinality statistics, cap configuration callbacks, and overflow statuses.
 * [OUTPUT]: High-performance dashboard HUD visualizing Prometheus label cardinality utilization, overflow diversion, and memory safety.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/MetricCardinalityCapHUD.tsx
 */

import React, { useState } from 'react';
import {
  MetricCardinalityCapHUDProps,
  MetricCardinalityStatItem,
} from './metricCardinalityTypes';

export const MetricCardinalityCapHUD: React.FC<MetricCardinalityCapHUDProps> = ({
  stats,
  onConfigureCap,
  onRefresh,
  onReset,
  isRefreshing = false,
}) => {
  const [selectedMetric, setSelectedMetric] = useState<string | null>(
    stats.length > 0 ? stats[0].metric_name : null
  );
  const [editingCap, setEditingCap] = useState<Record<string, number>>({});
  const [updatingMetric, setUpdatingMetric] = useState<string | null>(null);

  const activeStat = stats.find((s) => s.metric_name === selectedMetric) || stats[0] || null;

  const totalOverflow = stats.reduce((acc, s) => acc + s.overflow_count, 0);
  const hasOverflow = totalOverflow > 0;

  const handleCapInputChange = (metricName: string, val: number) => {
    setEditingCap((prev) => ({ ...prev, [metricName]: Math.max(1, val) }));
  };

  const handleSaveCap = async (metricName: string) => {
    const newCap = editingCap[metricName];
    if (!newCap || !onConfigureCap) return;
    try {
      setUpdatingMetric(metricName);
      await onConfigureCap(metricName, newCap);
    } finally {
      setUpdatingMetric(null);
    }
  };

  return (
    <div
      data-testid="metric-cardinality-cap-hud"
      className="p-5 bg-neutral-900 border border-neutral-800 rounded-xl text-neutral-100 shadow-xl space-y-6"
    >
      {/* 顶部控制栏 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-neutral-800 pb-4">
        <div>
          <div className="flex items-center gap-3">
            <span className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              <span className="text-emerald-400">🛡️</span> 热点路径指标基数封顶与溢出守卫
            </span>
            <span
              className={`px-2.5 py-0.5 text-xs font-semibold rounded-full border ${
                hasOverflow
                  ? 'bg-rose-950/80 text-rose-300 border-rose-700/60'
                  : 'bg-emerald-950/80 text-emerald-300 border-emerald-700/60'
              }`}
            >
              {hasOverflow ? `⚠️ 发现 ${totalOverflow} 次溢出归并` : '✓ 全指标基数受控'}
            </span>
          </div>
          <p className="text-xs text-neutral-400 mt-1">
            动态 URL 规范化 · 单指标基数硬上限约束 · 溢出桶 _overflow_ 归并 · 杜绝 Prometheus 内存泄漏
          </p>
        </div>

        <div className="flex items-center gap-3">
          {onReset && (
            <button
              type="button"
              data-testid="btn-reset-governor"
              onClick={onReset}
              className="px-3 py-1.5 text-xs bg-neutral-800 hover:bg-neutral-700 text-neutral-300 border border-neutral-700 rounded-lg transition"
            >
              复位
            </button>
          )}
          {onRefresh && (
            <button
              type="button"
              data-testid="btn-refresh-stats"
              onClick={onRefresh}
              disabled={isRefreshing}
              className="px-3 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-medium transition"
            >
              {isRefreshing ? '刷新中...' : '刷新'}
            </button>
          )}
        </div>
      </div>

      {/* KPI 卡片网格 */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-neutral-800/70 p-4 rounded-xl border border-neutral-700/60">
          <div className="text-xs text-neutral-400">受治理热点指标</div>
          <div className="text-2xl font-bold text-white mt-1">{stats.length} 个</div>
          <div className="text-xs text-neutral-400 mt-1">覆盖入站路由与回退事件</div>
        </div>

        <div className="bg-neutral-800/70 p-4 rounded-xl border border-neutral-700/60">
          <div className="text-xs text-neutral-400">已处理总采样样本</div>
          <div className="text-2xl font-bold text-indigo-400 mt-1">
            {stats.reduce((acc, s) => acc + s.total_samples, 0).toLocaleString()} 次
          </div>
          <div className="text-xs text-neutral-400 mt-1">毫秒级入站路径规整</div>
        </div>

        <div className="bg-neutral-800/70 p-4 rounded-xl border border-neutral-700/60">
          <div className="text-xs text-neutral-400">溢出归并保护次数</div>
          <div
            className={`text-2xl font-bold mt-1 ${
              totalOverflow > 0 ? 'text-amber-400' : 'text-emerald-400'
            }`}
          >
            {totalOverflow} 次
          </div>
          <div className="text-xs text-neutral-400 mt-1">安全收敛至 _overflow_ 桶</div>
        </div>
      </div>

      {/* 主视图：指标列表与详情下钻 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 左侧：指标列表 */}
        <div className="space-y-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
            📊 受控指标基数水位
          </h4>
          <div className="space-y-2">
            {stats.length === 0 ? (
              <div className="p-4 bg-neutral-800/40 rounded-xl text-xs text-neutral-500 text-center">
                暂无监控指标
              </div>
            ) : (
              stats.map((s) => {
                const isSelected = selectedMetric === s.metric_name;
                const statusColor: Record<string, string> = {
                  healthy: 'text-emerald-400 bg-emerald-950/60 border-emerald-800/60',
                  approaching_cap: 'text-amber-400 bg-amber-950/60 border-amber-800/60',
                  overflowing: 'text-rose-400 bg-rose-950/60 border-rose-800/60',
                };
                return (
                  <button
                    key={s.metric_name}
                    type="button"
                    data-testid={`metric-card-${s.metric_name}`}
                    onClick={() => setSelectedMetric(s.metric_name)}
                    className={`w-full text-left p-3.5 rounded-xl border transition space-y-2 ${
                      isSelected
                        ? 'bg-neutral-800 border-indigo-500/80 shadow-md'
                        : 'bg-neutral-800/50 border-neutral-700/50 hover:bg-neutral-800'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-xs text-white truncate max-w-[180px]">
                        {s.metric_name}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${
                          statusColor[s.status] || 'text-neutral-400'
                        }`}
                      >
                        {s.status === 'overflowing'
                          ? '溢出'
                          : s.status === 'approaching_cap'
                          ? '预警'
                          : '正常'}
                      </span>
                    </div>

                    <div className="space-y-1">
                      <div className="flex justify-between text-[11px] text-neutral-400">
                        <span>基数占用: {s.tracked_cardinality} / {s.cap_limit}</span>
                        <span>{s.utilization_pct}%</span>
                      </div>
                      <div className="w-full bg-neutral-700 rounded-full h-1.5 overflow-hidden">
                        <div
                          className={`h-1.5 rounded-full transition-all ${
                            s.utilization_pct >= 95
                              ? 'bg-rose-500'
                              : s.utilization_pct >= 80
                              ? 'bg-amber-500'
                              : 'bg-emerald-500'
                          }`}
                          style={{ width: `${Math.min(s.utilization_pct, 100)}%` }}
                        ></div>
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* 右侧：当前选中指标的标签分布与动态限额配置 */}
        {activeStat && (
          <div className="lg:col-span-2 space-y-5 bg-neutral-800/40 p-4 rounded-xl border border-neutral-700/60">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-700/60 pb-3">
              <div>
                <h3 className="font-bold text-sm text-white">{activeStat.metric_name}</h3>
                <span className="text-xs text-neutral-400">
                  当前上限: {activeStat.cap_limit} · 活跃标签: {activeStat.tracked_cardinality} · 溢出: {activeStat.overflow_count}
                </span>
              </div>

              {/* 动态微调上限 */}
              {onConfigureCap && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-neutral-400">调节上限:</span>
                  <input
                    type="number"
                    data-testid={`input-cap-${activeStat.metric_name}`}
                    value={
                      editingCap[activeStat.metric_name] !== undefined
                        ? editingCap[activeStat.metric_name]
                        : activeStat.cap_limit
                    }
                    onChange={(e) =>
                      handleCapInputChange(activeStat.metric_name, Number(e.target.value))
                    }
                    className="w-20 px-2 py-1 bg-neutral-800 border border-neutral-700 rounded text-xs text-white"
                  />
                  <button
                    type="button"
                    data-testid={`btn-save-cap-${activeStat.metric_name}`}
                    onClick={() => handleSaveCap(activeStat.metric_name)}
                    disabled={updatingMetric === activeStat.metric_name}
                    className="px-2.5 py-1 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded font-medium transition"
                  >
                    {updatingMetric === activeStat.metric_name ? '保存中...' : '保存'}
                  </button>
                </div>
              )}
            </div>

            {/* Top 活跃标签分布 */}
            <div className="space-y-3">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                🏷️ 前列追踪标签与命中计数
              </h4>
              <div className="space-y-2">
                {activeStat.top_tracked_labels.length === 0 ? (
                  <div className="text-xs text-neutral-500 py-3">该指标暂无活跃标签</div>
                ) : (
                  activeStat.top_tracked_labels.map((lbl) => {
                    const hits = activeStat.label_hits[lbl] || 0;
                    const isSentinel = lbl === '_overflow_';
                    return (
                      <div
                        key={lbl}
                        className={`flex items-center justify-between p-2.5 rounded-lg border text-xs ${
                          isSentinel
                            ? 'bg-rose-950/40 border-rose-800/60 text-rose-300'
                            : 'bg-neutral-800/70 border-neutral-700/60 text-neutral-200'
                        }`}
                      >
                        <span className="font-mono flex items-center gap-2 truncate max-w-[320px]">
                          {isSentinel ? '⚠️ 溢出哨兵桶' : '📌'} {lbl}
                        </span>
                        <span className="font-semibold text-neutral-400">
                          {hits.toLocaleString()} 次命中
                        </span>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
