/**
 * IncrementalStreamingMarkdownRenderer - 高帧率增量流式 Markdown 渲染器
 *
 * [INPUT]
 * - content: string 原始 Markdown 字符串
 * - isStreaming?: boolean 是否正处于流式生成状态
 * - throttleOptions?: RafThrottleOptions 帧率节流与自适应降级配置
 * - className?: string 样式类名
 * - showFpsHud?: boolean 是否展示性能监控 HUD
 *
 * [OUTPUT]
 * - IncrementalStreamingMarkdownRenderer: React.FC
 *
 * [POS]
 * 会话窗口核心渲染组件。结合 RAF 微任务批处理帧缓冲区与增量切块解析器，
 * 在 150+ tokens/s 超高速生成场景下保持 60fps 丝滑交互与输入框无卡顿。
 */

import React, { useMemo } from 'react';
import { Activity, Gauge, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { parseIncrementalStream } from './incrementalStreamParser';
import { useRafStreamThrottler } from './useRafStreamThrottler';
import type {
  MarkdownBlock,
  RafThrottleOptions,
} from './streamingMarkdownTypes';

export interface IncrementalStreamingMarkdownRendererProps {
  content: string;
  isStreaming?: boolean;
  throttleOptions?: RafThrottleOptions;
  className?: string;
  showFpsHud?: boolean;
}

/**
 * 冻结块展示项：采用 React.memo 守护，避免由于后续 Token 追加导致的二次全量重绘
 */
const FrozenMarkdownBlockItem = React.memo(
  ({ block }: { block: MarkdownBlock }) => {
    switch (block.type) {
      case 'code':
        return (
          <div
            data-testid={`frozen-block-${block.id}`}
            className="my-3 overflow-hidden rounded-lg border bg-neutral-950 font-mono text-xs text-neutral-100 shadow-sm"
          >
            {block.language && (
              <div className="flex items-center justify-between border-b border-neutral-800 bg-neutral-900/80 px-3 py-1.5 text-[11px] text-neutral-400">
                <span>{block.language}</span>
                <span className="text-[10px] uppercase text-neutral-500">已闭合代码块</span>
              </div>
            )}
            <pre className="overflow-x-auto p-3 leading-relaxed">
              <code>{block.rawContent.replace(/^```[^\n]*\n?/, '').replace(/\n```$/, '')}</code>
            </pre>
          </div>
        );

      case 'heading': {
        const text = block.rawContent.replace(/^#{1,6}\s+/, '');
        const Tag = (`h${Math.min(6, block.level || 1)}`) as 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6';
        return (
          <Tag
            data-testid={`frozen-block-${block.id}`}
            className="my-2 font-semibold tracking-tight text-foreground"
          >
            {text}
          </Tag>
        );
      }

      case 'blockquote':
        return (
          <blockquote
            data-testid={`frozen-block-${block.id}`}
            className="my-2 border-l-4 border-primary/40 pl-3 italic text-muted-foreground"
          >
            {block.rawContent.replace(/^>\s*/, '')}
          </blockquote>
        );

      case 'list':
        return (
          <div
            data-testid={`frozen-block-${block.id}`}
            className="my-1.5 pl-4 text-sm leading-relaxed text-foreground whitespace-pre-wrap"
          >
            {block.rawContent}
          </div>
        );

      case 'table':
        return (
          <div
            data-testid={`frozen-block-${block.id}`}
            className="my-3 overflow-x-auto rounded border bg-card/60 p-2 font-mono text-xs"
          >
            <pre className="whitespace-pre">{block.rawContent}</pre>
          </div>
        );

      default:
        return (
          <p
            data-testid={`frozen-block-${block.id}`}
            className="my-1.5 text-sm leading-relaxed text-foreground break-words"
          >
            {block.rawContent}
          </p>
        );
    }
  },
  (prev, next) => prev.block.rawContent === next.block.rawContent,
);

FrozenMarkdownBlockItem.displayName = 'FrozenMarkdownBlockItem';

/**
 * 流式活跃末尾块展示项：仅在流式输出期间承受轻量增量更新
 */
const ActiveTailBlockItem: React.FC<{
  block: MarkdownBlock;
  isDegradedMode: boolean;
}> = ({ block, isDegradedMode }) => {
  if (block.type === 'code') {
    return (
      <div
        data-testid="active-tail-block"
        className="my-3 overflow-hidden rounded-lg border border-primary/40 bg-neutral-950 font-mono text-xs text-neutral-100 shadow-sm"
      >
        <div className="flex items-center justify-between border-b border-neutral-800 bg-neutral-900/90 px-3 py-1.5 text-[11px] text-primary">
          <div className="flex items-center gap-1.5">
            <Sparkles className="h-3 w-3 animate-pulse" />
            <span>{block.language || 'code'} (流式传输中...)</span>
          </div>
          {isDegradedMode && (
            <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[9px] text-amber-300 font-sans">
              极速排版模式
            </span>
          )}
        </div>
        <pre className="overflow-x-auto p-3 leading-relaxed whitespace-pre-wrap">
          <code>{block.rawContent.replace(/^```[^\n]*\n?/, '')}</code>
        </pre>
      </div>
    );
  }

  return (
    <div
      data-testid="active-tail-block"
      className="my-1.5 text-sm leading-relaxed text-foreground break-words"
    >
      <span>{block.rawContent}</span>
    </div>
  );
};

export const IncrementalStreamingMarkdownRenderer: React.FC<
  IncrementalStreamingMarkdownRendererProps
> = ({
  content,
  isStreaming = false,
  throttleOptions,
  className,
  showFpsHud = false,
}) => {
  // 1. RAF 帧聚合与吞吐节流
  const { displayedContent, metrics } = useRafStreamThrottler(
    content,
    isStreaming,
    throttleOptions,
  );

  // 2. 增量切块解析
  const { frozenBlocks, activeTailBlock } = useMemo(() => {
    return parseIncrementalStream(displayedContent, isStreaming);
  }, [displayedContent, isStreaming]);

  return (
    <div
      data-testid="incremental-streaming-renderer"
      className={cn('relative w-full text-left', className)}
    >
      {/* 性能监控 HUD 仪表盘 */}
      {showFpsHud && (
        <div
          data-testid="stream-performance-hud"
          className="mb-3 flex items-center gap-3 rounded-md border border-neutral-200 dark:border-neutral-800 bg-muted/40 px-2.5 py-1 text-[11px] font-mono text-muted-foreground"
        >
          <div className="flex items-center gap-1">
            <Gauge className="h-3.5 w-3.5 text-primary" />
            <span>{metrics.currentFps} FPS</span>
          </div>
          <div className="flex items-center gap-1">
            <Activity className="h-3.5 w-3.5 text-amber-500" />
            <span>{metrics.tokensPerSecond} tokens/s</span>
          </div>
          {metrics.isDegradedMode && (
            <span className="rounded bg-amber-500/10 px-1 text-[10px] text-amber-600 dark:text-amber-400">
              负载降级保护中
            </span>
          )}
        </div>
      )}

      {/* 冻结块渲染流 (Memoized 快照) */}
      {frozenBlocks.map((block) => (
        <FrozenMarkdownBlockItem key={block.id} block={block} />
      ))}

      {/* 活跃尾部块渲染 */}
      {activeTailBlock && (
        <div className="relative inline-block w-full">
          <ActiveTailBlockItem
            block={activeTailBlock}
            isDegradedMode={metrics.isDegradedMode}
          />
        </div>
      )}

      {/* 流式生成呼吸微光标 */}
      {isStreaming && (
        <span
          data-testid="streaming-pulse-cursor"
          className="inline-block h-3.5 w-1.5 translate-y-0.5 rounded-sm bg-primary align-baseline animate-pulse ml-0.5"
          aria-hidden="true"
        />
      )}
    </div>
  );
};
