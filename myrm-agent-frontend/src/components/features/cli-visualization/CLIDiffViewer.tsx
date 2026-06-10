/**
 * CLI Diff 预览组件
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - diff: unified diff 格式字符串
 * - filePath: 文件路径（可选，用于显示）
 * - onClose: 关闭回调
 *
 * [OUTPUT]
 * - CLIDiffViewer: Diff 对比预览组件
 *   - 支持 unified/split 视图模式
 *   - 语法高亮（基于文件扩展名）
 *   - 新增/删除行数统计
 *
 * [POS]
 * CLI 可视化工具的 Diff 预览组件。将 unified diff 格式
 * 解析并以可视化方式展示，支持行号、颜色标记、统计信息。
 * 仅在 Tauri 桌面环境使用。
 */

'use client';

import React, { memo, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Copy, Check, SplitSquareHorizontal, AlignJustify, FileEdit, Plus, Minus } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useDiffParser } from '@/hooks/useDiffParser';
import type { DiffLine } from '@/lib/diff/parseUnifiedDiff';
import { CLIFileIcon } from './CLIFileIcon';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

export interface CLIDiffViewerProps {
  /** unified diff 格式字符串 */
  diff: string;
  /** 文件路径（可选） */
  filePath?: string;
  /** 关闭回调 */
  onClose?: () => void;
  /** 初始视图模式 */
  defaultViewMode?: 'unified' | 'split';
  /** 类名 */
  className?: string;
}

/** 视图模式 */
type ViewMode = 'unified' | 'split';

/**
 * 获取行的背景色
 */
function getLineBackground(type: DiffLine['type']): string {
  switch (type) {
    case 'addition':
      return 'bg-green-500/10 dark:bg-green-500/20';
    case 'deletion':
      return 'bg-red-500/10 dark:bg-red-500/20';
    case 'header':
      return 'bg-blue-500/10 dark:bg-blue-500/20';
    default:
      return '';
  }
}

/**
 * 获取行号的样式
 */
function getLineNumberStyle(type: DiffLine['type']): string {
  switch (type) {
    case 'addition':
      return 'text-green-600 dark:text-green-400';
    case 'deletion':
      return 'text-red-600 dark:text-red-400';
    default:
      return 'text-muted-foreground';
  }
}

/**
 * 获取行前缀符号
 */
function getLinePrefix(type: DiffLine['type']): string {
  switch (type) {
    case 'addition':
      return '+';
    case 'deletion':
      return '-';
    default:
      return ' ';
  }
}

/**
 * Unified 视图单行
 */
const UnifiedDiffLine: React.FC<{ line: DiffLine }> = memo(({ line }) => {
  const bgClass = getLineBackground(line.type);
  const numClass = getLineNumberStyle(line.type);

  if (line.type === 'header') {
    return (
      <div className={cn('flex font-mono text-xs', bgClass)}>
        <span className="w-16 text-center py-0.5 text-blue-600 dark:text-blue-400 font-medium">{line.content}</span>
      </div>
    );
  }

  return (
    <div className={cn('flex font-mono text-xs hover:bg-muted/50', bgClass)}>
      {/* 旧行号 */}
      <span className={cn('w-12 text-right pr-2 py-0.5 select-none border-r border-border/50', numClass)}>
        {line.oldLineNumber ?? ''}
      </span>
      {/* 新行号 */}
      <span className={cn('w-12 text-right pr-2 py-0.5 select-none border-r border-border/50', numClass)}>
        {line.newLineNumber ?? ''}
      </span>
      {/* 前缀 */}
      <span className={cn('w-6 text-center py-0.5 font-bold', numClass)}>{getLinePrefix(line.type)}</span>
      {/* 内容 */}
      <code className="flex-1 py-0.5 pr-4 whitespace-pre overflow-x-auto">{line.content}</code>
    </div>
  );
});
UnifiedDiffLine.displayName = 'UnifiedDiffLine';

/**
 * Split 视图单行
 */
const SplitDiffLine: React.FC<{
  leftLine: DiffLine | null;
  rightLine: DiffLine | null;
}> = memo(({ leftLine, rightLine }) => {
  return (
    <div className="flex font-mono text-xs">
      {/* 左侧（旧文件） */}
      <div
        className={cn(
          'flex-1 flex border-r border-border',
          leftLine?.type === 'deletion' ? 'bg-red-500/10 dark:bg-red-500/20' : '',
        )}
      >
        <span
          className={cn(
            'w-12 text-right pr-2 py-0.5 select-none border-r border-border/50',
            leftLine?.type === 'deletion' ? 'text-red-600 dark:text-red-400' : 'text-muted-foreground',
          )}
        >
          {leftLine?.oldLineNumber ?? ''}
        </span>
        <code className="flex-1 py-0.5 px-2 whitespace-pre overflow-x-auto">{leftLine?.content ?? ''}</code>
      </div>
      {/* 右侧（新文件） */}
      <div className={cn('flex-1 flex', rightLine?.type === 'addition' ? 'bg-green-500/10 dark:bg-green-500/20' : '')}>
        <span
          className={cn(
            'w-12 text-right pr-2 py-0.5 select-none border-r border-border/50',
            rightLine?.type === 'addition' ? 'text-green-600 dark:text-green-400' : 'text-muted-foreground',
          )}
        >
          {rightLine?.newLineNumber ?? ''}
        </span>
        <code className="flex-1 py-0.5 px-2 whitespace-pre overflow-x-auto">{rightLine?.content ?? ''}</code>
      </div>
    </div>
  );
});
SplitDiffLine.displayName = 'SplitDiffLine';

/**
 * CLI Diff 预览组件
 */
export const CLIDiffViewer: React.FC<CLIDiffViewerProps> = memo(
  ({ diff, filePath, onClose, defaultViewMode = 'unified', className }) => {
    const [viewMode, setViewMode] = useState<ViewMode>(defaultViewMode);
    const [copied, setCopied] = useState(false);

    const parsed = useDiffParser(diff);
    const displayPath = filePath || parsed.filePath || 'Unknown file';

    // 复制 diff
    const handleCopy = useCallback(async () => {
      try {
        await writeToClipboard(diff);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch {
        console.error('Failed to copy diff');
      }
    }, [diff]);

    // 切换视图模式
    const toggleViewMode = useCallback(() => {
      setViewMode((prev) => (prev === 'unified' ? 'split' : 'unified'));
    }, []);

    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 10 }}
        className={cn('bg-background border border-border rounded-lg overflow-hidden shadow-lg', className)}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2 bg-muted/50 border-b border-border">
          <div className="flex items-center gap-2">
            <FileEdit className="h-4 w-4 text-orange-500" />
            <CLIFileIcon filename={displayPath} className="h-4 w-4" />
            <span className="text-sm font-medium truncate max-w-[300px]" title={displayPath}>
              {displayPath.split('/').pop()}
            </span>
            {/* 统计 */}
            <div className="flex items-center gap-2 ml-2 text-xs">
              <span className="flex items-center gap-1 text-green-600 dark:text-green-400">
                <Plus className="h-3 w-3" />
                {parsed.additions}
              </span>
              <span className="flex items-center gap-1 text-red-600 dark:text-red-400">
                <Minus className="h-3 w-3" />
                {parsed.deletions}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1">
            {/* 视图模式切换 */}
            <button
              onClick={toggleViewMode}
              className="p-1.5 rounded hover:bg-muted transition-colors"
              title={viewMode === 'unified' ? 'Split view' : 'Unified view'}
            >
              {viewMode === 'unified' ? (
                <SplitSquareHorizontal className="h-4 w-4" />
              ) : (
                <AlignJustify className="h-4 w-4" />
              )}
            </button>
            {/* 复制 */}
            <button onClick={handleCopy} className="p-1.5 rounded hover:bg-muted transition-colors" title="Copy diff">
              {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
            </button>
            {/* 关闭 */}
            {onClose && (
              <button onClick={onClose} className="p-1.5 rounded hover:bg-muted transition-colors" title="Close">
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        <div className="max-h-[400px] overflow-auto">
          {parsed.isBinary ? (
            <div className="p-4 text-center text-muted-foreground">Binary file changed</div>
          ) : parsed.hunks.length === 0 ? (
            <div className="p-4 text-center text-muted-foreground">No changes</div>
          ) : (
            <AnimatePresence mode="wait">
              <motion.div
                key={viewMode}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
              >
                {parsed.hunks.map((hunk, hunkIndex) => (
                  <div key={hunkIndex}>
                    {viewMode === 'unified'
                      ? // Unified 视图
                        hunk.lines.map((line, lineIndex) => <UnifiedDiffLine key={lineIndex} line={line} />)
                      : // Split 视图（简化版：按顺序排列）
                        hunk.lines
                          .filter((l) => l.type !== 'header')
                          .map((line, lineIndex) => {
                            const leftLine = line.type === 'deletion' || line.type === 'context' ? line : null;
                            const rightLine = line.type === 'addition' || line.type === 'context' ? line : null;
                            return <SplitDiffLine key={lineIndex} leftLine={leftLine} rightLine={rightLine} />;
                          })}
                  </div>
                ))}
              </motion.div>
            </AnimatePresence>
          )}
        </div>
      </motion.div>
    );
  },
);

CLIDiffViewer.displayName = 'CLIDiffViewer';

export default CLIDiffViewer;
