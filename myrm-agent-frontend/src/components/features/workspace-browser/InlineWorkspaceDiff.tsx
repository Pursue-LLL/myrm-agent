'use client';

/**
 * InlineWorkspaceDiff - 工作区代码即时 Diff 对比抽屉/面板
 *
 * [INPUT]
 * - file: FileEntry
 * - originalContent: string (基线内容，即磁盘上已存的版本)
 * - modifiedContent: string (当前改动内容，即编辑中的草稿)
 * - onClose: () => void
 * - lib/diff/TextDiffViewer (POS: 文本 old/new 对比，带耗时上限)
 *
 * [OUTPUT]
 * - InlineWorkspaceDiff: 带文件名标题与关闭按钮的内嵌 Diff 面板
 *
 * [POS]
 * workspace-browser 模块的内嵌代码变更审查组件；对比本身交给共享的 TextDiffViewer。
 */

import React, { memo } from 'react';
import { useTranslations } from 'next-intl';
import { X, GitCommit } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { TextDiffViewer } from '@/lib/diff/TextDiffViewer';
import type { FileEntry } from '@/services/chat';
import { FileTypeIcon } from '@/components/features/files/FileTypeIcon';

interface InlineWorkspaceDiffProps {
  file: FileEntry;
  originalContent: string;
  modifiedContent: string;
  onClose: () => void;
  className?: string;
}

export const InlineWorkspaceDiff: React.FC<InlineWorkspaceDiffProps> = memo(
  ({ file, originalContent, modifiedContent, onClose, className }) => {
    const t = useTranslations('workspace');

    return (
      <div
        data-testid="inline-workspace-diff"
        className={cn('flex flex-col h-full bg-background border-l border-border', className)}
      >
        <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <GitCommit className="h-4 w-4 text-emerald-500 shrink-0" />
            <FileTypeIcon filename={file.name} className="shrink-0" />
            <span className="text-sm font-medium truncate" title={file.path}>
              {file.name}
            </span>
            <span className="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono">
              {t('diffView')}
            </span>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-muted transition-colors" title={t('close')}>
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-2">
          <TextDiffViewer oldValue={originalContent} newValue={modifiedContent} filePath={file.path} maxHeight="none" />
        </div>
      </div>
    );
  },
);

InlineWorkspaceDiff.displayName = 'InlineWorkspaceDiff';
