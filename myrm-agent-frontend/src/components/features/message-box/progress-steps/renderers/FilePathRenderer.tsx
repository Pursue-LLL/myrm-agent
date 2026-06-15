import React, { useState, useCallback } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { File, ChevronDown, ChevronRight } from 'lucide-react';
import { DiffViewer } from '@/lib/diff/DiffViewer';
import type { FilePathItem } from '../utils';

interface FilePathRendererProps {
  items: FilePathItem[];
  messageId: string;
  stepIndex: number;
}

const truncatePath = (path: string, maxLength: number = 50): string => {
  if (path.length <= maxLength) {
    return path;
  }
  return '...' + path.slice(-(maxLength - 3));
};

function countDiffStats(diff: string): { added: number; removed: number } {
  let added = 0;
  let removed = 0;
  const lines = diff.split('\n');
  for (const line of lines) {
    if (line.startsWith('+') && !line.startsWith('+++')) added++;
    else if (line.startsWith('-') && !line.startsWith('---')) removed++;
  }
  return { added, removed };
}

/**
 * 文件路径渲染器
 * 展示文件列表，有 diff 数据时支持点击展开查看变更
 */
const FilePathRenderer: React.FC<FilePathRendererProps> = ({ items, messageId, stepIndex }) => {
  const [expandedSet, setExpandedSet] = useState<Set<number>>(new Set());

  const toggleExpand = useCallback((index: number) => {
    setExpandedSet((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }, []);

  return (
    <div className="space-y-1.5">
      {items.map((item, index) => {
        const hasDiff = Boolean(item.diff);
        const isExpanded = expandedSet.has(index);
        const stats = hasDiff ? countDiffStats(item.diff!) : null;

        return (
          <div key={`${messageId}-step-${stepIndex}-file-${index}`}>
            <div
              className={cn(
                'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md',
                'bg-muted/50 border border-border/50',
                'text-xs font-mono text-muted-foreground',
                'transition-colors duration-200 hover:bg-muted hover:border-border',
                hasDiff && 'cursor-pointer',
              )}
              title={item.file_path}
              onClick={hasDiff ? () => toggleExpand(index) : undefined}
            >
              {hasDiff ? (
                isExpanded ? (
                  <ChevronDown className="w-3 h-3 flex-shrink-0" />
                ) : (
                  <ChevronRight className="w-3 h-3 flex-shrink-0" />
                )
              ) : (
                <File className="w-3 h-3 flex-shrink-0" />
              )}
              <span>{truncatePath(item.file_path)}</span>
              {stats && (
                <span className="ml-1.5 text-[10px] select-none">
                  {stats.added > 0 && <span className="text-green-600 dark:text-green-400">+{stats.added}</span>}
                  {stats.added > 0 && stats.removed > 0 && <span className="mx-0.5 text-muted-foreground/60">/</span>}
                  {stats.removed > 0 && <span className="text-red-500 dark:text-red-400">-{stats.removed}</span>}
                </span>
              )}
              {item.diff_truncated && (
                <span className="text-[10px] text-amber-500 dark:text-amber-400 ml-1">(truncated)</span>
              )}
            </div>

            {hasDiff && isExpanded && (
              <div className="mt-1 ml-1 max-w-full overflow-hidden">
                <DiffViewer
                  diff={item.diff!}
                  filePath={item.file_path}
                  className="text-[11px]"
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default FilePathRenderer;
