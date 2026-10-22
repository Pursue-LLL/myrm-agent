/**
 * [INPUT]: ContextUsageBreakdownHUDProps with snapshot data, refresh handler, and trigger compact callback.
 * [OUTPUT]: ContextUsageBreakdownHUD React component visualizing seven-category context distribution and 60%/90% alert lines.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/ContextUsageBreakdownHUD.tsx
 */

import React, { useState } from 'react';
import {
  ContextAlertLevel,
  ContextCategoryShareData,
  ContextUsageBreakdownHUDProps,
} from './contextBreakdownTypes';

const ALERT_CONFIG: Record<
  ContextAlertLevel,
  { label: string; badgeClass: string; barColor: string; desc: string }
> = {
  NORMAL: {
    label: '注意力集中区间 (Normal <60%)',
    badgeClass: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    barColor: 'bg-emerald-500',
    desc: '当前上下文处于最佳注意力区间，大模型推理逻辑敏捷、无长上下文信息遗忘。',
  },
  WARNING_60: {
    label: '跨越 60% 性能临界点 (Degradation Warning)',
    badgeClass: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
    barColor: 'bg-amber-500',
    desc: '已跨越 60% 黄金窗口，模型开始出现注意力衰减与中间段信息丢失，建议压缩上下文或新开任务。',
  },
  CRITICAL_90: {
    label: '达到 90% 极高风险线 (Critical Auto-Compact)',
    badgeClass: 'bg-rose-500/10 text-rose-300 border-rose-500/30',
    barColor: 'bg-rose-500',
    desc: '已触及 90% 熔断保护阈值，系统即将强制触发深度剪枝与历史摘要压缩。',
  },
};

export const ContextUsageBreakdownHUD: React.FC<ContextUsageBreakdownHUDProps> = ({
  data,
  onRefresh,
  onTriggerCompact,
  isCompacting = false,
}) => {
  const [loadingCompact, setLoadingCompact] = useState<boolean>(false);
  const alertMeta = ALERT_CONFIG[data.alert_level] || ALERT_CONFIG.NORMAL;

  const handleCompact = async () => {
    if (!onTriggerCompact) return;
    setLoadingCompact(true);
    try {
      await onTriggerCompact();
    } finally {
      setLoadingCompact(false);
    }
  };

  const categoriesList: ContextCategoryShareData[] = Object.values(data.categories);

  return (
    <div className="flex flex-col space-y-6 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
      {/* 头部标题与操作 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xl font-bold tracking-tight text-white">
              上下文用量七分类透视与警戒线 HUD (WorkBuddy Breakdown)
            </span>
            <span
              className={`rounded-md border px-2.5 py-0.5 font-mono text-xs font-semibold ${alertMeta.badgeClass}`}
            >
              {alertMeta.label}
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            {alertMeta.desc}
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:border-zinc-500 hover:bg-zinc-800 transition"
            >
              刷新用量
            </button>
          )}
          {onTriggerCompact && (
            <button
              onClick={handleCompact}
              disabled={loadingCompact || isCompacting}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                data.alert_level === 'NORMAL'
                  ? 'border border-zinc-700 bg-zinc-900 text-zinc-300 hover:bg-zinc-800'
                  : 'border border-amber-600 bg-amber-950/40 text-amber-300 hover:bg-amber-900/60 font-semibold'
              }`}
            >
              {loadingCompact || isCompacting ? '压缩执行中...' : '一键压缩上下文'}
            </button>
          )}
        </div>
      </div>

      {/* 进度条与 60%/90% 警戒线 */}
      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-4">
        <div className="flex justify-between items-center text-xs font-mono text-zinc-400 mb-2">
          <div>
            当前总用量：
            <span className="text-white font-bold text-sm ml-1">
              {data.provider_actual_tokens.toLocaleString()}
            </span>
            <span className="text-zinc-500 ml-1">/ {data.total_window_tokens.toLocaleString()} Tokens</span>
          </div>
          <div className="font-bold text-sm text-sky-400">
            {data.usage_ratio_pct}% 窗口占用
          </div>
        </div>

        {/* 综合进度槽 */}
        <div className="relative h-4 w-full rounded-full bg-zinc-800 overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ${alertMeta.barColor}`}
            style={{ width: `${Math.min(100, data.usage_ratio_pct)}%` }}
          />
          {/* 60% 警戒线指示器 */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-amber-400 z-10"
            style={{ left: '60%' }}
            title="60% 注意力衰减警戒线"
          />
          {/* 90% 熔断线指示器 */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-rose-500 z-10"
            style={{ left: '90%' }}
            title="90% 自动深度压缩线"
          />
        </div>

        {/* 标尺注释 */}
        <div className="relative mt-1.5 text-[10px] font-mono text-zinc-500 h-4">
          <span className="absolute left-0">0%</span>
          <span className="absolute left-[60%] -translate-x-1/2 text-amber-400 font-semibold">
            ▲ 60% 警戒线
          </span>
          <span className="absolute left-[90%] -translate-x-1/2 text-rose-400 font-semibold">
            ▲ 90% 熔断线
          </span>
          <span className="absolute right-0">100%</span>
        </div>
      </div>

      {/* 双口径并列对账：估算 vs 提供商实际上报 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="text-xs text-zinc-400">按分类真实估算总和 (≈ Estimated Sum)</div>
          <div className="mt-1 font-mono text-xl font-bold text-sky-300">
            {data.estimated_sum_tokens.toLocaleString()}{' '}
            <span className="text-xs font-normal text-zinc-500">Tokens</span>
          </div>
          <div className="mt-1 text-[11px] text-zinc-400">
            逐层扫描 System Prompt、记忆、工作区规则、技能与消息并剥离计量。
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="text-xs text-zinc-400">提供商实际上报总量 (Provider Exact)</div>
          <div className="mt-1 font-mono text-xl font-bold text-white">
            {data.provider_actual_tokens.toLocaleString()}{' '}
            <span className="text-xs font-normal text-zinc-500">Tokens</span>
          </div>
          <div className="mt-1 text-[11px] text-zinc-400">
            模型提供商端到端真实结算计费输入 Token 总和。
          </div>
        </div>
      </div>

      {/* 七分类细分卡片网格 */}
      <div>
        <div className="text-xs font-semibold text-zinc-300 mb-3">
          到底是谁在吃窗口？（七分类用量透视表）
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {categoriesList.map((cat) => (
            <div
              key={cat.category}
              className="rounded-lg border border-zinc-800/80 bg-zinc-900/60 p-3 flex flex-col justify-between"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-zinc-200">{cat.label_zh}</span>
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: cat.color_hex }}
                />
              </div>
              <div className="mt-2 flex items-baseline justify-between">
                <span className="font-mono text-sm font-bold text-white">
                  {cat.estimated_tokens.toLocaleString()}
                </span>
                <span className="font-mono text-xs text-zinc-400 font-medium">
                  {cat.percentage}%
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 底部架构说明 */}
      <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/30 p-3 text-xs text-zinc-400">
        <span className="font-semibold text-zinc-300">架构升级保障：</span>
        已修复旧版只认 <code className="font-mono text-zinc-300">&lt;system_prompt&gt;</code> 导致的 69% 记录余量为 0 缺陷，现已全面支持真实标记 <code className="font-mono text-zinc-300">&lt;user_memory_context</code> 与 <code className="font-mono text-zinc-300">&lt;workspace_context</code>。
      </div>
    </div>
  );
};
