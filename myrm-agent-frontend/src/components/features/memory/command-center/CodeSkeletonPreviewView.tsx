/**
 * [INPUT]
 * - @/services/memory/codeCompaction: CompactedBlockOutput
 * - @/components/primitives/badge: Badge
 *
 * [OUTPUT]
 * - CodeSkeletonPreviewView: Sub-component rendering AST compacted code blocks and token stats.
 *
 * [POS]
 * Sub-component for CodeMemoryCompactionCard under command-center.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React from 'react';
import { Code2, FileCode, Sparkles } from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import type { CompactedBlockOutput } from '@/services/memory/codeCompaction';

interface CodeSkeletonPreviewViewProps {
  blocks: CompactedBlockOutput[];
}

function getTierBadgeVariant(level: string): { label: string; className: string } {
  if (level.includes('L1')) {
    return {
      label: 'L1 结构签名',
      className: 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10',
    };
  }
  if (level.includes('L2')) {
    return {
      label: 'L2 控制流骨架',
      className: 'border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-500/10',
    };
  }
  return {
    label: 'L3 全量源码',
    className: 'border-blue-500/40 text-blue-600 dark:text-blue-400 bg-blue-500/10',
  };
}

export function CodeSkeletonPreviewView({ blocks }: CodeSkeletonPreviewViewProps) {
  if (blocks.length === 0) {
    return (
      <div className="rounded border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
        暂无代码压缩块，请提交代码或调整 Token 预算以生成骨架
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="text-[11px] font-medium text-muted-foreground flex items-center justify-between">
        <span>压缩结果预览 ({blocks.length} 块)</span>
      </div>
      <div className="max-h-72 space-y-2.5 overflow-y-auto pr-1">
        {blocks.map((b) => {
          const badge = getTierBadgeVariant(b.abstraction_level);
          const savedTokens = Math.max(0, b.original_token_count - b.compacted_token_count);
          const savedRatio =
            b.original_token_count > 0
              ? Math.round((savedTokens / b.original_token_count) * 100)
              : 0;

          return (
            <div
              key={b.file_path}
              className="rounded-md border border-border/70 bg-card p-3 text-xs transition"
            >
              <div className="flex flex-wrap items-center justify-between gap-1.5 pb-2 border-b border-border/50">
                <div className="flex items-center gap-1.5 font-mono text-[11px] text-foreground">
                  <FileCode className="h-3.5 w-3.5 text-primary" />
                  <span className="font-semibold">{b.file_path}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Badge variant="outline" className={badge.className}>
                    {badge.label}
                  </Badge>
                  <span className="text-[10px] text-muted-foreground">
                    {b.compacted_token_count} / {b.original_token_count} Tokens
                  </span>
                  {savedRatio > 0 && (
                    <Badge variant="secondary" className="text-[10px] text-emerald-600 dark:text-emerald-400">
                      省 {savedRatio}%
                    </Badge>
                  )}
                </div>
              </div>
              <div className="mt-2">
                <pre className="max-h-36 overflow-x-auto rounded bg-muted/60 p-2 font-mono text-[11px] leading-relaxed text-foreground/90 whitespace-pre">
                  <code>{b.content || '// 空代码块'}</code>
                </pre>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
