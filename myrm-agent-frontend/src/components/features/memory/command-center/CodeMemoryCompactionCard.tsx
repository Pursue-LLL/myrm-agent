/**
 * [INPUT]
 * - @/services/memory/codeCompaction: compactCodeMemory, extractCodeSkeleton, CompactedBlockOutput, CodeCompactionResponse
 * - @/components/primitives: Card, Button, Badge, Input
 * - ./CodeSkeletonPreviewView: CodeSkeletonPreviewView
 *
 * [OUTPUT]
 * - CodeMemoryCompactionCard: React container rendering Token-Budget-Aware Codebase Semantic Memory
 *   compaction controls, skeleton extraction, and multi-tier compression preview.
 *
 * [POS]
 * Personal Brain Command Center UnderstandSection card for code memory compaction and token budgeting.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useState } from 'react';
import {
  Archive,
  ArrowDownRight,
  Code2,
  FileCode,
  Gauge,
  Layers,
  Sparkles,
} from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import { cn } from '@/lib/utils/classnameUtils';
import {
  type CompactedBlockOutput,
  compactCodeMemory,
  extractCodeSkeleton,
} from '@/services/memory/codeCompaction';
import { CodeSkeletonPreviewView } from './CodeSkeletonPreviewView';

interface CodeMemoryCompactionCardProps {
  className?: string;
}

const DEFAULT_SAMPLE_CODE = `class TokenCompactor:
    def __init__(self, budget: int):
        self.budget = budget
        self.history = []

    def process_node(self, node: dict) -> bool:
        """Evaluate AST node against budget constraints."""
        if not node:
            return False
        weight = len(str(node)) * 0.25
        if weight > self.budget:
            return False
        self.history.append(node)
        return True`;

export function CodeMemoryCompactionCard({ className }: CodeMemoryCompactionCardProps) {
  const [tokenBudget, setTokenBudget] = useState(120);
  const [filePath, setFilePath] = useState('src/engine/compactor.py');
  const [sourceCode, setSourceCode] = useState(DEFAULT_SAMPLE_CODE);
  const [selectedLevel, setSelectedLevel] = useState<'L1_SIGNATURES' | 'L2_CONTROL_FLOW' | 'L3_FULL_SOURCE'>('L1_SIGNATURES');

  const [isLoading, setIsLoading] = useState(false);
  const [blocks, setBlocks] = useState<CompactedBlockOutput[]>([]);
  const [totalOriginal, setTotalOriginal] = useState<number | null>(null);
  const [totalCompacted, setTotalCompacted] = useState<number | null>(null);
  const [compressionRatio, setCompressionRatio] = useState<number | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const handleExtractSkeleton = async () => {
    setIsLoading(true);
    setStatusMessage(null);
    try {
      const res = await extractCodeSkeleton({
        source_code: sourceCode,
        level: selectedLevel,
      });
      const singleBlock: CompactedBlockOutput = {
        file_path: filePath,
        abstraction_level: res.abstraction_level,
        content: res.content,
        original_token_count: res.original_token_count,
        compacted_token_count: res.compacted_token_count,
      };
      setBlocks([singleBlock]);
      setTotalOriginal(res.original_token_count);
      setTotalCompacted(res.compacted_token_count);
      const ratio =
        res.original_token_count > 0
          ? ((res.original_token_count - res.compacted_token_count) / res.original_token_count) * 100
          : 0;
      setCompressionRatio(Math.round(ratio));
      setStatusMessage(`已按 ${selectedLevel} 级别提取骨架`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '提取骨架失败';
      setStatusMessage(`错误: ${message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleBudgetCompaction = async () => {
    setIsLoading(true);
    setStatusMessage(null);
    try {
      const res = await compactCodeMemory({
        items: [
          {
            file_path: filePath,
            source_code: sourceCode,
            relevance_score: 0.8,
            language: 'python',
          },
        ],
        token_budget: tokenBudget,
      });
      setBlocks(res.compacted_blocks);
      setTotalOriginal(res.total_original_tokens);
      setTotalCompacted(res.total_compacted_tokens);
      setCompressionRatio(Math.round(res.compression_ratio * 100));
      setStatusMessage(`已根据 Token 预算 ${tokenBudget} 完成动态压缩`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '预算压缩失败';
      setStatusMessage(`错误: ${message}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className={cn('border-border/80 shadow-sm', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-primary" />
            <CardTitle className="text-base font-semibold">
              代码语义记忆骨架化压缩引擎
            </CardTitle>
          </div>
          <Badge variant="outline" className="border-primary/40 text-primary text-xs">
            Token 预算感知
          </Badge>
        </div>
        <CardDescription className="text-xs text-muted-foreground">
          基于 AST 语法的多级结构骨架提取（L1 签名 / L2 控制流 / L3 全量），在有限 Context 窗口下动态保留高价值代码细节
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 pt-1">
        {/* Token 统计指标栏 */}
        {totalOriginal !== null && totalCompacted !== null && (
          <div className="grid grid-cols-3 gap-2 rounded-lg border border-border/60 bg-muted/30 p-2.5 text-center">
            <div>
              <div className="text-[10px] text-muted-foreground">原始 Token</div>
              <div className="font-mono text-sm font-semibold text-foreground">
                {totalOriginal}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-muted-foreground">压缩后 Token</div>
              <div className="font-mono text-sm font-semibold text-primary">
                {totalCompacted}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-muted-foreground">Token 节省率</div>
              <div className="flex items-center justify-center gap-0.5 font-mono text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                <ArrowDownRight className="h-3.5 w-3.5" />
                {compressionRatio}%
              </div>
            </div>
          </div>
        )}

        {/* 控制区：文件路径与预算设置 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="space-y-1">
            <label
              htmlFor="compaction-file-path-input"
              className="text-[11px] font-medium text-muted-foreground flex items-center gap-1"
            >
              <FileCode className="h-3 w-3" /> 文件路径
            </label>
            <Input
              id="compaction-file-path-input"
              value={filePath}
              onChange={(e) => setFilePath(e.target.value)}
              placeholder="e.g. src/auth/service.py"
              className="h-8 font-mono text-xs"
            />
          </div>

          <div className="space-y-1">
            <label
              htmlFor="compaction-budget-input"
              className="text-[11px] font-medium text-muted-foreground flex items-center gap-1"
            >
              <Gauge className="h-3 w-3" /> Token 预算上限
            </label>
            <Input
              id="compaction-budget-input"
              type="number"
              value={tokenBudget}
              onChange={(e) => setTokenBudget(Number(e.target.value) || 0)}
              className="h-8 font-mono text-xs"
            />
          </div>
        </div>

        {/* 源码输入区 */}
        <div className="space-y-1">
          <label
            htmlFor="compaction-source-textarea"
            className="text-[11px] font-medium text-muted-foreground flex items-center justify-between"
          >
            <span className="flex items-center gap-1">
              <Code2 className="h-3 w-3" /> 待压缩代码内容
            </span>
            <span className="text-[10px] text-muted-foreground">
              约 {Math.round(sourceCode.length * 0.26)} tokens
            </span>
          </label>
          <textarea
            id="compaction-source-textarea"
            value={sourceCode}
            onChange={(e) => setSourceCode(e.target.value)}
            rows={5}
            className="w-full resize-none rounded-md border border-input bg-background p-2 font-mono text-xs leading-relaxed text-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            placeholder="输入待压缩的代码片段..."
          />
        </div>

        {/* 抽象层级选择与操作按钮 */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-border/50">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground">提取级别:</span>
            {(['L1_SIGNATURES', 'L2_CONTROL_FLOW', 'L3_FULL_SOURCE'] as const).map((tier) => (
              <Button
                key={tier}
                size="sm"
                variant={selectedLevel === tier ? 'default' : 'outline'}
                className="h-7 px-2 text-[10px]"
                onClick={() => setSelectedLevel(tier)}
              >
                {tier.replace('_', ' ')}
              </Button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={isLoading || !sourceCode.trim()}
              onClick={handleExtractSkeleton}
              className="h-7 text-xs"
            >
              <Sparkles className="mr-1 h-3.5 w-3.5" />
              提取骨架
            </Button>
            <Button
              size="sm"
              disabled={isLoading || !sourceCode.trim()}
              onClick={handleBudgetCompaction}
              className="h-7 text-xs"
            >
              <Archive className="mr-1 h-3.5 w-3.5" />
              预算压缩
            </Button>
          </div>
        </div>

        {statusMessage && (
          <div className="rounded bg-accent/40 px-2.5 py-1.5 text-[11px] text-muted-foreground">
            {statusMessage}
          </div>
        )}

        {/* 骨架与压缩预览 */}
        <CodeSkeletonPreviewView blocks={blocks} />
      </CardContent>
    </Card>
  );
}
