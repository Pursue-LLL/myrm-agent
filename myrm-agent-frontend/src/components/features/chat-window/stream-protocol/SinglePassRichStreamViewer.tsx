'use client';

import React, { useRef, useEffect } from 'react';
import {
  Code,
  Activity,
  ArrowDown,
  Check,
  Copy,
  Zap,
  Gauge,
  Sliders,
} from 'lucide-react';
import { useStreamProtocolStore } from './useStreamProtocolStore';
import { TypedStreamBlock, RichSpan } from './streamProtocolTypes';

export const SinglePassRichStreamViewer: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [copiedBlockId, setCopiedBlockId] = React.useState<string | null>(null);

  const {
    typedBlocks,
    viewport,
    metrics,
    targetScrollTop,
    handleScroll,
    handleContentGrow,
    openBenchmarkModal,
  } = useStreamProtocolStore();

  // 监听 targetScrollTop 并执行受控滚动
  useEffect(() => {
    if (targetScrollTop !== null && containerRef.current) {
      containerRef.current.scrollTop = targetScrollTop;
    }
  }, [targetScrollTop]);

  // 内容高度变化时通知状态机
  useEffect(() => {
    if (containerRef.current && containerRef.current.scrollHeight > 0) {
      handleContentGrow(containerRef.current.scrollHeight);
    }
  }, [typedBlocks, handleContentGrow]);

  const handleCopyCode = (blockId: string, code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedBlockId(blockId);
    setTimeout(() => { setCopiedBlockId(null); }, 1500);
  };

  const renderSpan = (span: RichSpan, idx: number) => {
    if (span.type === 'bold') {
      return (
        <strong key={idx} className="font-semibold text-slate-100">
          {span.text}
        </strong>
      );
    }
    if (span.type === 'inline_code') {
      return (
        <code
          key={idx}
          className="px-1 py-0.5 rounded bg-slate-800 text-sky-300 font-mono text-[11px] border border-slate-700/60"
        >
          {span.text}
        </code>
      );
    }
    if (span.type === 'ansi_color') {
      return (
        <span key={idx} className={`font-mono font-medium ${span.colorClass || 'text-slate-300'}`}>
          {span.text}
        </span>
      );
    }
    return <span key={idx}>{span.text}</span>;
  };

  const renderBlock = (block: TypedStreamBlock) => {
    if (block.type === 'code_block') {
      const codeText = block.spans.map((s) => s.text).join('');
      return (
        <div
          key={block.id}
          className="my-3 rounded-xl border border-slate-700/80 bg-slate-950 overflow-hidden text-xs shadow-md"
        >
          <div className="flex items-center justify-between px-3.5 py-2 bg-slate-900 border-b border-slate-800 text-slate-400">
            <span className="flex items-center gap-1.5 font-mono text-[11px]">
              <Code className="w-3.5 h-3.5 text-blue-400" />
              {block.language || 'plaintext'}
            </span>
            <button
              type="button"
              onClick={() => { handleCopyCode(block.id, codeText); }}
              className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded hover:bg-slate-800 text-slate-300 transition-colors"
            >
              {copiedBlockId === block.id ? (
                <>
                  <Check className="w-3 h-3 text-emerald-400" /> 已复制
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3 text-slate-400" /> 复制代码
                </>
              )}
            </button>
          </div>
          <pre className="p-3.5 overflow-x-auto text-slate-200 font-mono text-xs leading-relaxed">
            <code>{codeText}</code>
          </pre>
        </div>
      );
    }

    return (
      <div key={block.id} className="my-1.5 text-xs text-slate-300 leading-relaxed break-words">
        {block.spans.map((span, idx) => renderSpan(span, idx))}
      </div>
    );
  };

  return (
    <div className="relative flex flex-col h-full w-full rounded-xl border border-slate-800 bg-slate-900/60 shadow-xl overflow-hidden font-sans">
      {/* Top Protocol Telemetry Bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-slate-950/80 border-b border-slate-800 text-xs text-slate-400 select-none">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1 font-medium text-slate-200">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            单遍流式引擎 (Single-Pass)
          </span>
          <span className="hidden sm:inline font-mono text-[11px] text-slate-400">
            {metrics.throughputTokensPerSec.toLocaleString()} Token/s
          </span>
          <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/40">
            耗时 {metrics.parseDurationMs} ms
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] text-slate-400 hidden md:inline">
            CPU &lt; {metrics.estimatedCpuUsagePct}%
          </span>
          <button
            type="button"
            onClick={openBenchmarkModal}
            className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
          >
            <Gauge className="w-3 h-3 text-sky-400" />
            性能对比看板
          </button>
        </div>
      </div>

      {/* Main Stream Viewport */}
      <div
        ref={containerRef}
        onScroll={(e) => { handleScroll(e.currentTarget.scrollTop); }}
        className="flex-1 overflow-y-auto p-4 space-y-1 relative"
      >
        {typedBlocks.length > 0 ? (
          typedBlocks.map((block) => renderBlock(block))
        ) : (
          <div className="flex items-center justify-center h-48 text-slate-500 text-xs">
            等待流式数据输入...
          </div>
        )}
      </div>

      {/* Floating Re-anchor CTA when User Detached */}
      {viewport.anchorMode === 'USER_DETACHED' && (
        <button
          type="button"
          onClick={() => {
            if (containerRef.current) {
              containerRef.current.scrollTop = containerRef.current.scrollHeight;
            }
          }}
          className="absolute bottom-4 right-4 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium shadow-lg transition-transform hover:scale-105"
        >
          <ArrowDown className="w-3.5 h-3.5" />
          回到底部追踪
        </button>
      )}
    </div>
  );
};
