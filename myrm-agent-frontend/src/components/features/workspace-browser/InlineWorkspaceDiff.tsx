'use client';

/**
 * InlineWorkspaceDiff - 工作区代码即时 Diff 对比抽屉/面板
 *
 * [INPUT]
 * - file: FileEntry
 * - workspace: string (workspace root)
 * - originalContent: string | null (基线内容，如原始或上一个已存版本)
 * - modifiedContent: string | null (当前改动内容)
 * - onClose: () => void
 *
 * [OUTPUT]
 * - InlineWorkspaceDiff: 使用 DiffViewer 渲染的内嵌 Diff 面板
 *
 * [POS]
 * workspace-browser 模块的内嵌代码变更审查组件。
 */

import React, { memo, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { X, GitCommit } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { DiffViewer } from '@/lib/diff/DiffViewer';
import type { FileEntry } from '@/services/chat';
import { CLIFileIcon } from '@/components/features/cli-visualization/CLIFileIcon';

interface InlineWorkspaceDiffProps {
  file: FileEntry;
  workspace: string;
  originalContent: string;
  modifiedContent: string;
  onClose: () => void;
  className?: string;
}

function createUnifiedDiffText(filename: string, oldText: string, newText: string): string {
  const oldLines = oldText.split('\n');
  const newLines = newText.split('\n');

  const diffHeader = [
    `--- a/${filename}`,
    `+++ b/${filename}`,
    `@@ -1,${oldLines.length} +1,${newLines.length} @@`,
  ];

  const body: string[] = [];
  const max = Math.max(oldLines.length, newLines.length);

  for (let i = 0; i < max; i++) {
    const o = oldLines[i];
    const n = newLines[i];
    if (o === n) {
      if (o !== undefined) {
        body.push(` ${o}`);
      }
    } else {
      if (o !== undefined) {
        body.push(`-${o}`);
      }
      if (n !== undefined) {
        body.push(`+${n}`);
      }
    }
  }

  return [...diffHeader, ...body].join('\n');
}

export const InlineWorkspaceDiff: React.FC<InlineWorkspaceDiffProps> = memo(
  ({ file, originalContent, modifiedContent, onClose, className }) => {
    const t = useTranslations('workspace');

    const generatedDiff = useMemo(() => {
      return createUnifiedDiffText(file.name, originalContent, modifiedContent);
    }, [file.name, originalContent, modifiedContent]);

    return (
      <div
        data-testid="inline-workspace-diff"
        className={cn('flex flex-col h-full bg-background border-l border-border', className)}
      >
        <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <GitCommit className="h-4 w-4 text-emerald-500 shrink-0" />
            <CLIFileIcon filename={file.name} className="shrink-0" />
            <span className="text-sm font-medium truncate" title={file.path}>
              {file.name}
            </span>
            <span className="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono">
              {t('diffView')}
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-muted transition-colors"
            title={t('close')}
          >
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-2">
          <DiffViewer
            diff={generatedDiff}
            filePath={file.path}
            defaultViewMode="unified"
            embedded
          />
        </div>
      </div>
    );
  },
);

InlineWorkspaceDiff.displayName = 'InlineWorkspaceDiff';
