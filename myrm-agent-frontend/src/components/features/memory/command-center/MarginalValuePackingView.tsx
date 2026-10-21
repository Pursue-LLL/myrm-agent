/**
 * [INPUT]
 * Props: packedResult, onRepack, repacking
 *
 * [OUTPUT]
 * MarginalValuePackingView: Main packing breakdown visualizer for Item 122.
 *
 * [POS]
 * Command-center subview showing accepted/dropped candidates and context prompt preview.
 * Strict typing applied: No `any` types allowed. Accessible markup. Single file < 260 lines.
 */

import React, { useState } from 'react';
import {
  PackageCheck,
  PackageX,
  Code2,
  Copy,
  Check,
  Sparkles,
  Layers,
  Zap,
} from 'lucide-react';
import type { PackedRecallResultDTO } from '@/services/memory/budgetPacking';

export interface MarginalValuePackingViewProps {
  packedResult: PackedRecallResultDTO;
  onRepack: () => void;
  repacking: boolean;
}

export const MarginalValuePackingView: React.FC<MarginalValuePackingViewProps> = ({
  packedResult,
  onRepack,
  repacking,
}) => {
  const [copied, setCopied] = useState<boolean>(false);

  const handleCopyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(packedResult.composed_prompt_block);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback silent fail
    }
  };

  const { packed_items, dropped_candidates, accounting } = packedResult;

  return (
    <div className="space-y-4">
      {/* 头部原理横幅 */}
      <div className="p-3.5 rounded-lg bg-blue-500/10 border border-blue-500/20 space-y-1.5">
        <div className="flex items-center gap-2 text-xs font-semibold text-blue-700 dark:text-blue-400">
          <Sparkles className="w-4 h-4 shrink-0" />
          <span>贪心边际价值装箱（Marginal Value Density Knapsack）原理</span>
        </div>
        <p className="text-xs text-blue-800 dark:text-blue-300/90 leading-relaxed">
          打破传统 RAG 固定条数截断导致 Token 浪费或超出的弊端。系统以{' '}
          <code className="px-1.5 py-0.5 rounded bg-blue-500/20 font-mono text-[11px]">
            边际价值 / 计费 Token
          </code>{' '}
          为密度指标执行贪心背包填充，自动压制高语义重叠的冗余条目，并利用较小的高价值片段回填预算缝隙。
        </p>
      </div>

      {/* 主展示区：左侧入选，右侧丢弃 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 左侧：已入选装箱片段 */}
        <div className="p-4 bg-card/60 rounded-lg border border-border space-y-3">
          <div className="flex items-center justify-between border-b border-border/60 pb-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
              <PackageCheck className="w-4 h-4 text-emerald-500" />
              <span>入选装箱记忆片段 ({packed_items.length})</span>
            </div>
            <button
              type="button"
              aria-label="重新触发贪心装箱"
              onClick={onRepack}
              disabled={repacking}
              className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md bg-muted hover:bg-muted/80 text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
            >
              <Zap className={`w-3 h-3 ${repacking ? 'animate-spin' : ''}`} />
              <span>重新装箱</span>
            </button>
          </div>

          <div className="space-y-2.5 max-h-[380px] overflow-y-auto pr-1">
            {packed_items.map((item) => (
              <div
                key={`packed-${item.candidate.id}`}
                className="p-3 rounded-lg bg-muted/20 border border-border/80 space-y-2"
              >
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="w-5 h-5 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-[10px]">
                      {item.order_index + 1}
                    </span>
                    <span className="font-mono font-medium text-foreground">
                      {item.candidate.id}
                    </span>
                    {item.candidate.domain_tags?.map((t) => (
                      <span
                        key={t}
                        className="px-1.5 py-0.2 rounded bg-muted text-[10px] text-muted-foreground"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                  <div className="flex items-center gap-1.5 font-mono text-[11px]">
                    <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                      MVD: {item.metrics.marginal_value_density.toFixed(4)}
                    </span>
                    <span className="text-muted-foreground">
                      ({item.candidate.billed_tokens}t)
                    </span>
                  </div>
                </div>

                <p className="text-xs text-foreground/90 leading-relaxed">
                  {item.candidate.content}
                </p>

                <div className="flex items-center justify-between pt-1 text-[11px] text-muted-foreground border-t border-border/40">
                  <span>基础效用: {item.metrics.base_utility.toFixed(3)}</span>
                  <span>边际增益: {item.metrics.marginal_info_gain.toFixed(3)}</span>
                  <span>累计消费: {item.cumulative_billed_tokens}t</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 右侧：被淘汰或抑制候选 */}
        <div className="p-4 bg-card/60 rounded-lg border border-border space-y-3">
          <div className="flex items-center justify-between border-b border-border/60 pb-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
              <PackageX className="w-4 h-4 text-amber-500" />
              <span>淘汰与抑制片段 ({dropped_candidates.length})</span>
            </div>
            <span className="text-[11px] text-muted-foreground font-mono">
              过滤节省 {accounting.storage_tokens_saved}t 存储
            </span>
          </div>

          <div className="space-y-2.5 max-h-[380px] overflow-y-auto pr-1">
            {dropped_candidates.map((drop) => {
              const isRedundant = drop.reason === 'redundancy_suppressed';
              return (
                <div
                  key={`drop-${drop.candidate.id}`}
                  className="p-3 rounded-lg bg-muted/20 border border-border/80 space-y-2 opacity-85"
                >
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-muted-foreground">
                        {drop.candidate.id}
                      </span>
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          isRedundant
                            ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20'
                            : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                        }`}
                      >
                        {isRedundant ? '语义冗余抑制' : '预算用尽拦截'}
                      </span>
                    </div>
                    <span className="text-[10px] font-mono text-muted-foreground">
                      体量: {drop.candidate.billed_tokens}t
                    </span>
                  </div>

                  <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
                    {drop.candidate.content}
                  </p>

                  <div className="flex items-center justify-between pt-1 text-[11px] text-muted-foreground border-t border-border/40">
                    <span>重叠度: {(drop.metrics.redundancy_score * 100).toFixed(1)}%</span>
                    <span>剩余边际价值: {drop.metrics.marginal_value.toFixed(3)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* 底部：最终装箱注入 Prompt 预览 */}
      <div className="p-4 bg-card/60 rounded-lg border border-border space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
            <Code2 className="w-4 h-4 text-primary" />
            <span>编译生成的结构化上下文装箱块 (Prompt Context Block)</span>
          </div>
          <button
            type="button"
            aria-label="复制装箱上下文代码块"
            onClick={handleCopyPrompt}
            className="flex items-center gap-1.5 px-3 py-1 text-xs rounded-md bg-muted hover:bg-muted/80 text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-500" />
                <span className="text-emerald-500 font-medium">已复制</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>复制 XML 块</span>
              </>
            )}
          </button>
        </div>
        <pre className="p-3 rounded-md bg-muted/40 border border-border/80 font-mono text-[11px] text-foreground overflow-x-auto whitespace-pre-wrap max-h-48 leading-relaxed">
          {packedResult.composed_prompt_block}
        </pre>
      </div>
    </div>
  );
};
