'use client';

/**
 * [INPUT]
 * - ./types::CausalTraceData, TraceSpanNode, SpanKind, SpanStatus (POS: 因果 Trace 契约)
 * - lucide-react::GitCommit, Clock, CheckCircle2, XCircle, AlertTriangle, ChevronRight, ChevronDown, Tag, Layers (POS: 视觉指示图标)
 *
 * [OUTPUT]
 * - CausalTraceWaterfallView: 单次任务请求因果 Trace 时序瀑布图视图组件
 *
 * [POS]
 * src/components/features/system-monitor/CausalTraceWaterfallView.tsx — 请求全链路因果时序与耗时分解瀑布图。
 */

import React, { useState } from 'react';
import {
  GitCommit,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ChevronRight,
  ChevronDown,
  Tag,
  Layers,
} from 'lucide-react';
import type { CausalTraceData, TraceSpanNode, SpanKind, SpanStatus } from './types';

const KIND_LABELS: Record<SpanKind, { label: string; color: string }> = {
  input: { label: '用户输入', color: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20' },
  context_stage: { label: '上下文装配', color: 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20' },
  llm_call: { label: '模型推理', color: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20' },
  approval_gate: { label: '审批门禁', color: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20' },
  tool_call: { label: '工具执行', color: 'bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/20' },
  output_delivery: { label: '通道投递', color: 'bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border-cyan-500/20' },
  internal: { label: '内部阶段', color: 'bg-muted text-muted-foreground border-border/40' },
};

const STATUS_ICONS: Record<SpanStatus, React.ReactNode> = {
  ok: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />,
  error: <XCircle className="w-3.5 h-3.5 text-destructive shrink-0" />,
  denied: <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0" />,
  timeout: <AlertTriangle className="w-3.5 h-3.5 text-orange-500 shrink-0" />,
  unset: <Clock className="w-3.5 h-3.5 text-muted-foreground shrink-0" />,
};

interface SpanRowProps {
  span: TraceSpanNode;
  depth: number;
  maxDurationMs: number;
}

const SpanRow: React.FC<SpanRowProps> = ({ span, depth, maxDurationMs }) => {
  const [expanded, setExpanded] = useState<boolean>(false);
  const kindMeta = KIND_LABELS[span.kind] || KIND_LABELS.internal;
  const pct = maxDurationMs > 0 ? Math.min(100, Math.max(2, (span.duration_ms / maxDurationMs) * 100)) : 100;
  const hasChildren = span.children && span.children.length > 0;
  const hasAttributes = span.attributes && Object.keys(span.attributes).length > 0;

  return (
    <div className="flex flex-col gap-1 text-xs">
      <div
        className="flex items-center justify-between p-2 rounded-lg border border-border/40 hover:bg-muted/30 transition-colors gap-2 cursor-pointer"
        style={{ paddingLeft: `${Math.max(8, depth * 16 + 8)}px` }}
        onClick={() => setExpanded(!expanded)}
      >
        {/* 左侧：折叠指示、类型与名称 */}
        <div className="flex items-center gap-2 overflow-hidden shrink-0 max-w-[45%]">
          {hasChildren || hasAttributes ? (
            expanded ? (
              <ChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            )
          ) : (
            <span className="w-3.5" />
          )}
          {STATUS_ICONS[span.status]}
          <span className={`px-1.5 py-0.5 rounded text-[10px] border font-medium shrink-0 ${kindMeta.color}`}>
            {kindMeta.label}
          </span>
          <span className="font-semibold text-foreground truncate" title={span.name}>
            {span.name}
          </span>
        </div>

        {/* 中间：时序瀑布条 */}
        <div className="flex-1 mx-3 h-2 rounded-full bg-muted/40 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              span.status === 'error'
                ? 'bg-destructive'
                : span.status === 'denied'
                  ? 'bg-amber-500'
                  : 'bg-primary'
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>

        {/* 右侧：精确耗时 */}
        <div className="text-right shrink-0 font-mono text-[11px] text-muted-foreground min-w-[65px]">
          {span.duration_ms.toFixed(1)} ms
        </div>
      </div>

      {/* 展开的属性与事件抽屉 */}
      {expanded && hasAttributes && (
        <div
          className="ml-8 p-2.5 rounded-md bg-muted/20 border border-border/30 text-[11px] font-mono space-y-1"
          style={{ marginLeft: `${depth * 16 + 28}px` }}
        >
          <div className="flex items-center gap-1 font-semibold text-muted-foreground pb-1 border-b border-border/20">
            <Tag className="w-3 h-3 text-primary" />
            <span>Span Attributes</span>
          </div>
          {Object.entries(span.attributes).map(([k, v]) => (
            <div key={k} className="flex items-start gap-2">
              <span className="text-muted-foreground shrink-0">{k}:</span>
              <span className="text-foreground break-all">{String(v)}</span>
            </div>
          ))}
          {span.status_message && (
            <div className="pt-1 text-destructive flex items-center gap-1">
              <span>Error: {span.status_message}</span>
            </div>
          )}
        </div>
      )}

      {/* 递归子 Span */}
      {span.children &&
        span.children.map((child) => (
          <SpanRow
            key={child.span_id}
            span={child}
            depth={depth + 1}
            maxDurationMs={maxDurationMs}
          />
        ))}
    </div>
  );
};

interface CausalTraceWaterfallViewProps {
  trace: CausalTraceData;
  className?: string;
}

export const CausalTraceWaterfallView: React.FC<CausalTraceWaterfallViewProps> = ({
  trace,
  className = '',
}) => {
  if (!trace || !trace.root) {
    return (
      <div className={`p-4 text-xs text-muted-foreground text-center bg-muted/20 rounded-lg ${className}`}>
        暂无可用因果链路时序数据
      </div>
    );
  }

  const rootDuration = Math.max(1.0, trace.root.duration_ms);

  return (
    <div
      data-testid="causal-trace-waterfall-view"
      className={`rounded-xl border border-border/60 bg-background/50 p-4 space-y-3.5 ${className}`}
    >
      <div className="flex items-center justify-between border-b border-border/40 pb-3">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">
            单次任务因果时序链路 (Causal Trace Waterfall)
          </h3>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
          <GitCommit className="w-3.5 h-3.5 text-primary/70" />
          <span>Trace ID: {trace.trace_id.slice(0, 12)}...</span>
          <span className="px-2 py-0.5 rounded bg-muted font-bold text-foreground">
            总耗时: {rootDuration.toFixed(1)} ms
          </span>
        </div>
      </div>

      <div className="space-y-1">
        <SpanRow span={trace.root} depth={0} maxDurationMs={rootDuration} />
      </div>
    </div>
  );
};
