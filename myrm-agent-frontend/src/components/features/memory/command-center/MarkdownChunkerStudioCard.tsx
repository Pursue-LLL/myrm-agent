/**
 * [INPUT]
 * @/services/memory::(sliceMarkdown, incrementalIndexMarkdown, hydrateChunkContext, MarkdownChunkDTO, ChunkSliceResponse, IncrementalIndexResponse, HydrateResponse)
 * ./MarkdownChunkerHudBar::MarkdownChunkerHudBar
 * ./SlidingWindowVisualizerCard::SlidingWindowVisualizerCard
 * ./IncrementalDiffInspectorCard::IncrementalDiffInspectorCard
 * ./markdownChunkerFallbacks::(SAMPLE_MARKDOWN_DOCUMENTS, FALLBACK_SLICE_RESPONSE, FALLBACK_INCREMENTAL_RESPONSE, FALLBACK_HYDRATE_RESPONSE)
 * lucide-react::Split, AlertCircle, Play
 *
 * [OUTPUT]
 * Component: MarkdownChunkerStudioCard
 *
 * [POS]
 * Studio card orchestrating Item 132 IncrementalSlidingWindowMarkdownChunkerSuite.
 * Manages 400-token sliding window slicing, 80-token overlap, line pointers,
 * content-hash incremental diffing, and hydration viewer.
 * Strictly typed with zero `any`. Single file < 350 lines.
 */

'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Split, AlertCircle, Play } from 'lucide-react';
import {
  sliceMarkdown,
  incrementalIndexMarkdown,
  hydrateChunkContext,
  type MarkdownChunkDTO,
  type IncrementalDiffReportDTO,
  type HydrateResponse,
} from '@/services/memory';
import { MarkdownChunkerHudBar } from './MarkdownChunkerHudBar';
import { SlidingWindowVisualizerCard } from './SlidingWindowVisualizerCard';
import { IncrementalDiffInspectorCard } from './IncrementalDiffInspectorCard';
import {
  SAMPLE_MARKDOWN_DOCUMENTS,
  FALLBACK_SLICE_RESPONSE,
  FALLBACK_INCREMENTAL_RESPONSE,
  FALLBACK_HYDRATE_RESPONSE,
} from './markdownChunkerFallbacks';

interface MarkdownChunkerStudioCardProps {
  initialDocumentKey?: string;
}

export const MarkdownChunkerStudioCard: React.FC<
  MarkdownChunkerStudioCardProps
> = ({ initialDocumentKey = 'memory_architecture' }) => {
  const [selectedDocKey, setSelectedDocKey] = useState<string>(initialDocumentKey);
  const activeDoc =
    SAMPLE_MARKDOWN_DOCUMENTS[selectedDocKey] ??
    SAMPLE_MARKDOWN_DOCUMENTS.memory_architecture;

  const [content, setContent] = useState<string>(activeDoc.initial);
  const [sourcePath, setSourcePath] = useState<string>(activeDoc.path);
  const [targetTokens, setTargetTokens] = useState<number>(400);
  const [overlapTokens, setOverlapTokens] = useState<number>(80);

  const [chunks, setChunks] = useState<MarkdownChunkDTO[]>([]);
  const [diffReport, setDiffReport] = useState<IncrementalDiffReportDTO | null>(null);

  const [isSlicing, setIsSlicing] = useState<boolean>(false);
  const [isDiffing, setIsDiffing] = useState<boolean>(false);
  const [isHydrating, setIsHydrating] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleDocPresetChange = (docKey: string) => {
    setSelectedDocKey(docKey);
    const doc = SAMPLE_MARKDOWN_DOCUMENTS[docKey];
    if (doc) {
      setContent(doc.initial);
      setSourcePath(doc.path);
      setDiffReport(null);
    }
  };

  const handleExecuteSlice = useCallback(async () => {
    if (!content.trim()) return;
    setIsSlicing(true);
    setErrorMessage(null);
    try {
      const res = await sliceMarkdown({
        content,
        source_path: sourcePath,
        config: {
          target_tokens: targetTokens,
          overlap_tokens: overlapTokens,
        },
      });
      setChunks(res.chunks);
    } catch {
      setChunks(FALLBACK_SLICE_RESPONSE.chunks);
      setErrorMessage('无法连接切片服务，已载入离线模拟切片数据');
    } finally {
      setIsSlicing(false);
    }
  }, [content, sourcePath, targetTokens, overlapTokens]);

  useEffect(() => {
    void handleExecuteSlice();
  }, [handleExecuteSlice]);

  const handleSimulateIncrementalDiff = async () => {
    setIsDiffing(true);
    setErrorMessage(null);
    try {
      const updatedContent = activeDoc.updated;
      setContent(updatedContent);

      const res = await incrementalIndexMarkdown({
        source_path: sourcePath,
        new_content: updatedContent,
        config: {
          target_tokens: targetTokens,
          overlap_tokens: overlapTokens,
        },
      });
      setDiffReport(res.report);
      setChunks(res.chunks);
    } catch {
      setContent(activeDoc.updated);
      setDiffReport(FALLBACK_INCREMENTAL_RESPONSE.report);
      setChunks(FALLBACK_INCREMENTAL_RESPONSE.chunks);
      setErrorMessage('执行增量比对失败，已载入离线模拟增量数据');
    } finally {
      setIsDiffing(false);
    }
  };

  const handleHydrateContext = async (
    chunk: MarkdownChunkDTO
  ): Promise<HydrateResponse | null> => {
    setIsHydrating(true);
    try {
      const res = await hydrateChunkContext({
        chunk,
        full_document: content,
        window_lines: 2,
      });
      return res;
    } catch {
      return {
        ...FALLBACK_HYDRATE_RESPONSE,
        start_line: chunk.start_line,
        end_line: chunk.end_line,
      };
    } finally {
      setIsHydrating(false);
    }
  };

  return (
    <section
      aria-labelledby="markdown-chunker-heading"
      className="p-6 rounded-2xl bg-card/60 backdrop-blur border border-border space-y-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-primary/10 text-primary">
            <Split className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <h2
              id="markdown-chunker-heading"
              className="text-lg font-semibold text-foreground tracking-tight"
            >
              增量滑动窗口 Markdown 切片与重叠索引
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              400 token 目标块 + 80 token 语义重叠，内容哈希增量感知，杜绝截断与 Token 浪费
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div>
            <label
              htmlFor="select-markdown-preset"
              className="sr-only"
            >
              选择文档预设
            </label>
            <select
              id="select-markdown-preset"
              value={selectedDocKey}
              onChange={(e) => handleDocPresetChange(e.target.value)}
              className="px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="memory_architecture">核心记忆架构 (MEMORY.md)</option>
            </select>
          </div>

          <button
            type="button"
            onClick={() => void handleExecuteSlice()}
            disabled={isSlicing || !content.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <Play className="w-3.5 h-3.5" aria-hidden="true" />
            <span>{isSlicing ? '切片中...' : '重新切片'}</span>
          </button>
        </div>
      </div>

      {errorMessage && (
        <div
          role="alert"
          className="flex items-center gap-2 p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-xs"
        >
          <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
          <span>{errorMessage}</span>
        </div>
      )}

      <MarkdownChunkerHudBar
        sourcePath={sourcePath}
        totalChunks={chunks.length}
        overlapTokens={overlapTokens}
        tokenSavingsPct={diffReport?.token_savings_pct ?? 0}
        status={diffReport?.status ?? 'ready'}
        isLoading={isSlicing}
        onRefresh={() => void handleExecuteSlice()}
      />

      <div className="p-4 rounded-xl border border-border bg-card/40 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-medium text-foreground">切片参数配置</span>
          <span className="text-[11px] text-muted-foreground font-mono">
            {targetTokens} tokens / chunk · {overlapTokens} tokens overlap
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label
              htmlFor="input-target-tokens"
              className="block text-xs font-medium text-foreground mb-1"
            >
              目标容量 (Target Tokens)
            </label>
            <input
              id="input-target-tokens"
              type="number"
              min={50}
              max={2048}
              value={targetTokens}
              onChange={(e) => setTargetTokens(parseInt(e.target.value, 10) || 400)}
              className="w-full px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div>
            <label
              htmlFor="input-overlap-tokens"
              className="block text-xs font-medium text-foreground mb-1"
            >
              相邻重叠预算 (Overlap Tokens)
            </label>
            <input
              id="input-overlap-tokens"
              type="number"
              min={0}
              max={512}
              value={overlapTokens}
              onChange={(e) => setOverlapTokens(parseInt(e.target.value, 10) || 80)}
              className="w-full px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6">
        <IncrementalDiffInspectorCard
          report={diffReport}
          onSimulateEdit={() => void handleSimulateIncrementalDiff()}
          isSimulating={isDiffing}
        />

        <SlidingWindowVisualizerCard
          chunks={chunks}
          onHydrate={handleHydrateContext}
          isHydrating={isHydrating}
        />
      </div>
    </section>
  );
};
