/**
 * [INPUT]
 * @/services/memory::(MarkdownChunkDTO, HydrateResponse)
 * lucide-react::Code2, Hash, Sparkles, Eye, Check, ChevronDown, ChevronRight
 *
 * [OUTPUT]
 * Component: SlidingWindowVisualizerCard
 *
 * [POS]
 * Visual inspector rendering Markdown chunks with line-level pointers,
 * content-hash signatures, and inline context hydration viewer.
 * Strictly typed with zero `any`. Single file < 350 lines.
 */

import React, { useState } from 'react';
import {
  Code2,
  Hash,
  Sparkles,
  Eye,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import type { MarkdownChunkDTO, HydrateResponse } from '@/services/memory';

interface SlidingWindowVisualizerCardProps {
  chunks: MarkdownChunkDTO[];
  onHydrate: (chunk: MarkdownChunkDTO) => Promise<HydrateResponse | null>;
  isHydrating: boolean;
}

export const SlidingWindowVisualizerCard: React.FC<
  SlidingWindowVisualizerCardProps
> = ({ chunks, onHydrate, isHydrating }) => {
  const [selectedChunkId, setSelectedChunkId] = useState<string | null>(null);
  const [hydratedData, setHydratedData] = useState<HydrateResponse | null>(null);
  const [activeHydratingId, setActiveHydratingId] = useState<string | null>(null);

  const handleHydrateClick = async (chunk: MarkdownChunkDTO) => {
    setActiveHydratingId(chunk.chunk_id);
    setSelectedChunkId(chunk.chunk_id);
    const res = await onHydrate(chunk);
    setHydratedData(res);
    setActiveHydratingId(null);
  };

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-border">
        <div>
          <h4 className="font-medium text-foreground text-sm flex items-center gap-2">
            <Code2 className="w-4 h-4 text-primary" aria-hidden="true" />
            <span>滑动窗口切片可视化检视 ({chunks.length} 块)</span>
          </h4>
          <p className="text-xs text-muted-foreground mt-0.5">
            400 token 目标容量与 80 token 相邻重叠，保持代码块与段落上下文语义连贯
          </p>
        </div>
      </div>

      {chunks.length === 0 ? (
        <div className="py-8 text-center text-xs text-muted-foreground">
          暂无切片数据，请点击“执行滑动窗口切片”生成切片
        </div>
      ) : (
        <div className="space-y-3">
          {chunks.map((chunk, idx) => {
            const isSelected = selectedChunkId === chunk.chunk_id;
            const isThisHydrating =
              isHydrating && activeHydratingId === chunk.chunk_id;

            return (
              <div
                key={chunk.chunk_id}
                className={`rounded-lg border transition-all ${
                  isSelected
                    ? 'border-primary/50 bg-primary/[0.02]'
                    : 'border-border bg-background hover:border-border/80'
                }`}
              >
                <div className="p-3.5 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span className="flex items-center justify-center w-6 h-6 rounded-full bg-muted text-xs font-semibold text-foreground">
                      {idx + 1}
                    </span>
                    <span className="font-mono text-xs font-semibold text-foreground">
                      {chunk.chunk_id}
                    </span>
                    <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-secondary text-secondary-foreground">
                      行号: L{chunk.start_line}-L{chunk.end_line}
                    </span>
                    <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-accent/40 text-muted-foreground">
                      {chunk.token_estimate} tokens
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <div className="hidden sm:flex items-center gap-1 text-[11px] font-mono text-muted-foreground">
                      <Hash className="w-3 h-3 text-primary" aria-hidden="true" />
                      <span>{chunk.chunk_hash}</span>
                    </div>

                    <button
                      type="button"
                      onClick={() => void handleHydrateClick(chunk)}
                      disabled={isHydrating}
                      aria-label={`水合回溯切片 ${chunk.chunk_id}`}
                      className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-primary"
                    >
                      {isSelected ? (
                        <ChevronDown className="w-3.5 h-3.5" aria-hidden="true" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
                      )}
                      <span>
                        {isThisHydrating ? '水合中...' : '水合回溯'}
                      </span>
                    </button>
                  </div>
                </div>

                <div className="px-3.5 pb-3">
                  <pre className="p-3 rounded-lg bg-muted/40 border border-border/60 text-xs font-mono text-foreground overflow-x-auto whitespace-pre-wrap max-h-36">
                    {chunk.text}
                  </pre>
                </div>

                {isSelected && hydratedData && (
                  <div className="m-3 p-3.5 rounded-lg bg-accent/30 border border-primary/30 space-y-2">
                    <div className="flex items-center justify-between text-xs font-medium text-foreground">
                      <span className="flex items-center gap-1.5 text-primary">
                        <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
                        <span>原文水合上下文 (扩展前后 {hydratedData.window_lines} 行)</span>
                      </span>
                      <span className="text-muted-foreground font-mono">
                        涵盖范围: L{hydratedData.start_line} 至 L{hydratedData.end_line}
                      </span>
                    </div>
                    <pre className="p-3 rounded bg-background border border-border text-xs font-mono text-foreground overflow-x-auto whitespace-pre-wrap max-h-48">
                      {hydratedData.hydrated_text}
                    </pre>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
