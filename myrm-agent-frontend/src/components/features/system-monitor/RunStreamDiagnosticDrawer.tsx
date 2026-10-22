/**
 * [INPUT]: RunStreamDiagnosticDrawerProps with event list, statistics, severity filters, and close handler.
 * [OUTPUT]: RunStreamDiagnosticDrawer component rendering dual-track decoupled diagnostic events without polluting chat messages.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/RunStreamDiagnosticDrawer.tsx
 */

import React, { useState } from 'react';
import {
  DiagnosticCategory,
  DiagnosticEventItem,
  DiagnosticSeverity,
  RunStreamDiagnosticDrawerProps,
} from './diagnosticStreamTypes';

const SEVERITY_COLORS: Record<DiagnosticSeverity, { badge: string; border: string }> = {
  CRITICAL: {
    badge: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
    border: 'border-l-rose-500',
  },
  ERROR: {
    badge: 'bg-red-500/20 text-red-300 border-red-500/40',
    border: 'border-l-red-500',
  },
  WARNING: {
    badge: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
    border: 'border-l-amber-500',
  },
  INFO: {
    badge: 'bg-sky-500/20 text-sky-300 border-sky-500/40',
    border: 'border-l-sky-500',
  },
  DEBUG: {
    badge: 'bg-zinc-500/20 text-zinc-300 border-zinc-500/40',
    border: 'border-l-zinc-500',
  },
};

const CATEGORY_NAMES: Record<DiagnosticCategory, string> = {
  RETRY: '请求重试 (Retry)',
  CONTEXT_TRUNCATION: '上下文截断 (Truncation)',
  MCP_LATENCY: 'MCP工具延迟 (MCP Latency)',
  SANDBOX_PRESSURE: '沙箱资源承压 (Pressure)',
  MODEL_DEGRADE: '模型降级 (Degrade)',
  CUSTOM: '自定义诊断 (Custom)',
};

export const RunStreamDiagnosticDrawer: React.FC<RunStreamDiagnosticDrawerProps> = ({
  isOpen,
  onClose,
  sessionId,
  runId,
  events,
  stats,
  onRefresh,
  onFilterSeverity,
  onFilterCategory,
}) => {
  const [selectedSeverity, setSelectedSeverity] = useState<DiagnosticSeverity | 'ALL'>('ALL');
  const [selectedCategory, setSelectedCategory] = useState<DiagnosticCategory | 'ALL'>('ALL');

  if (!isOpen) {
    return null;
  }

  const handleSeverityChange = (sev: DiagnosticSeverity | 'ALL') => {
    setSelectedSeverity(sev);
    if (onFilterSeverity) {
      onFilterSeverity(sev);
    }
  };

  const handleCategoryChange = (cat: DiagnosticCategory | 'ALL') => {
    setSelectedCategory(cat);
    if (onFilterCategory) {
      onFilterCategory(cat);
    }
  };

  const filteredEvents = events.filter((ev) => {
    if (selectedSeverity !== 'ALL' && ev.severity !== selectedSeverity) return false;
    if (selectedCategory !== 'ALL' && ev.category !== selectedCategory) return false;
    return true;
  });

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="运行诊断事件流抽屉"
      className="fixed inset-y-0 right-0 z-50 flex w-full max-w-2xl flex-col border-l border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-2xl backdrop-blur"
    >
      {/* 头部标题与关闭 */}
      <div className="flex items-center justify-between border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-lg font-bold text-white tracking-wide">
              运行流式诊断抽屉 (RunStream Diagnostics)
            </span>
            <span className="rounded bg-sky-950 border border-sky-800/60 px-2 py-0.5 text-xs font-mono text-sky-300">
              双轨解耦通道
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            物理隔离诊断事件流，杜绝内部重试、滑窗丢弃与沙箱压力混入普通聊天气泡。
          </p>
        </div>
        <div className="flex items-center space-x-2">
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 transition"
            >
              刷新
            </button>
          )}
          <button
            onClick={onClose}
            aria-label="关闭诊断抽屉"
            className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 hover:text-white transition"
          >
            关闭
          </button>
        </div>
      </div>

      {/* 会话与运行态信息 */}
      {(sessionId || runId) && (
        <div className="mt-3 flex flex-wrap gap-4 rounded-lg border border-zinc-800/80 bg-zinc-900/60 px-3 py-2 text-xs font-mono text-zinc-400">
          {sessionId && <div>Session: <span className="text-zinc-200">{sessionId}</span></div>}
          {runId && <div>RunId: <span className="text-zinc-200">{runId}</span></div>}
        </div>
      )}

      {/* 统计指标卡片 */}
      {stats && (
        <div className="mt-4 grid grid-cols-4 gap-2 text-center text-xs">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-2">
            <div className="text-zinc-400">诊断事件总量</div>
            <div className="mt-1 text-lg font-bold text-white font-mono">{stats.total_events}</div>
          </div>
          <div className="rounded-lg border border-rose-900/30 bg-rose-950/20 p-2">
            <div className="text-rose-400">致命严重 (Critical)</div>
            <div className="mt-1 text-lg font-bold text-rose-300 font-mono">
              {stats.by_severity.CRITICAL || 0}
            </div>
          </div>
          <div className="rounded-lg border border-amber-900/30 bg-amber-950/20 p-2">
            <div className="text-amber-400">警告告警 (Warning)</div>
            <div className="mt-1 text-lg font-bold text-amber-300 font-mono">
              {stats.by_severity.WARNING || 0}
            </div>
          </div>
          <div className="rounded-lg border border-sky-900/30 bg-sky-950/20 p-2">
            <div className="text-sky-400">重试事件 (Retry)</div>
            <div className="mt-1 text-lg font-bold text-sky-300 font-mono">
              {stats.by_category.RETRY || 0}
            </div>
          </div>
        </div>
      )}

      {/* 严重度过滤 Tab */}
      <div className="mt-4 flex flex-wrap gap-1.5 border-b border-zinc-800/60 pb-3">
        {(['ALL', 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'] as const).map((sev) => (
          <button
            key={sev}
            onClick={() => handleSeverityChange(sev)}
            className={`rounded px-2.5 py-1 text-xs font-medium transition ${
              selectedSeverity === sev
                ? 'bg-zinc-200 text-zinc-950 font-semibold'
                : 'bg-zinc-900 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
            }`}
          >
            {sev}
          </button>
        ))}
      </div>

      {/* 类别过滤标签 */}
      <div className="mt-2 flex flex-wrap gap-1.5 pb-2">
        {(
          [
            'ALL',
            'RETRY',
            'CONTEXT_TRUNCATION',
            'MCP_LATENCY',
            'SANDBOX_PRESSURE',
            'MODEL_DEGRADE',
            'CUSTOM',
          ] as const
        ).map((cat) => (
          <button
            key={cat}
            onClick={() => handleCategoryChange(cat)}
            className={`rounded px-2 py-0.5 text-xs transition ${
              selectedCategory === cat
                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40 font-medium'
                : 'bg-zinc-900/60 text-zinc-400 hover:bg-zinc-800'
            }`}
          >
            {cat === 'ALL' ? '全部类别' : CATEGORY_NAMES[cat]}
          </button>
        ))}
      </div>

      {/* 诊断事件列表 */}
      <div className="mt-3 flex-1 space-y-3 overflow-y-auto pr-1">
        {filteredEvents.length === 0 ? (
          <div className="flex h-48 flex-col items-center justify-center rounded-lg border border-dashed border-zinc-800 text-zinc-500">
            <p className="text-sm">暂无匹配的诊断流事件</p>
            <p className="mt-1 text-xs text-zinc-600">
              运行流与文本流安全解耦，内部告警仅在异常触发时上报
            </p>
          </div>
        ) : (
          filteredEvents.map((ev) => {
            const colorCfg = SEVERITY_COLORS[ev.severity] || SEVERITY_COLORS.INFO;
            return (
              <div
                key={ev.event_id}
                className={`rounded-lg border border-zinc-800 bg-zinc-900/60 p-3.5 shadow-sm border-l-4 ${colorCfg.border}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center space-x-2">
                    <span
                      className={`rounded border px-2 py-0.5 font-mono text-[11px] font-semibold ${colorCfg.badge}`}
                    >
                      {ev.severity}
                    </span>
                    <span className="rounded bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-300">
                      {CATEGORY_NAMES[ev.category] || ev.category}
                    </span>
                    <span className="font-mono text-xs font-semibold text-zinc-200">
                      {ev.code}
                    </span>
                  </div>
                  <span className="font-mono text-[11px] text-zinc-500">
                    {new Date(ev.timestamp).toLocaleTimeString()}
                  </span>
                </div>

                <div className="mt-2 text-xs text-zinc-200 leading-relaxed">
                  {ev.message}
                </div>

                {ev.details && Object.keys(ev.details).length > 0 && (
                  <div className="mt-2.5 rounded bg-zinc-950/70 p-2 font-mono text-[11px] text-zinc-400">
                    <div className="mb-1 text-[10px] uppercase tracking-wider text-zinc-500">
                      诊断元数据 (Details):
                    </div>
                    {Object.entries(ev.details).map(([k, v]) => (
                      <div key={k} className="flex gap-2">
                        <span className="text-zinc-500">{k}:</span>
                        <span className="text-zinc-300">{v}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* 底部隔离防污染承诺 */}
      <div className="mt-4 rounded-lg border border-emerald-900/30 bg-emerald-950/20 px-3.5 py-2.5 text-xs text-emerald-400">
        <span className="font-semibold">双轨流保障：</span>
        诊断事件通过独立的 <code className="font-mono text-emerald-300">/diagnostic-stream</code> 通道推拉，绝不伪装为用户消息，避免混淆用户认知或污染渲染流。
      </div>
    </div>
  );
};
