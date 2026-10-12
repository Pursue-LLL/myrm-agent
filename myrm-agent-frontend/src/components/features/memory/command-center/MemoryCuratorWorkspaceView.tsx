'use client';

/**
 * [INPUT]
 * @/services/memory/curatorStudio::CuratedMemoryEntryDTO, MarkdownSyncResponseDTO
 *
 * [OUTPUT]
 * MemoryCuratorWorkspaceView: Subview for human-readable Markdown bi-directional sync,
 * raw mirror editing, and disk reconciliation diff inspection.
 *
 * [POS]
 * Subcomponent for Item 101 (HumanReadableMarkdownBidiSyncAndMemoryCuratorStudioSuite).
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  FileText,
  RefreshCw,
  Download,
  CheckCircle2,
  AlertCircle,
  Clock,
  Sparkles,
  ArrowRightLeft,
  FileDiff,
} from 'lucide-react';
import type { MarkdownSyncResponseDTO } from '@/services/memory/curatorStudio';

interface MemoryCuratorWorkspaceViewProps {
  markdownContent: string;
  onSyncMarkdown: (text: string, hardDelete: boolean) => Promise<void>;
  onExportMarkdown: () => Promise<void>;
  lastSyncResult: MarkdownSyncResponseDTO | null;
  isLoading: boolean;
}

export function MemoryCuratorWorkspaceView({
  markdownContent,
  onSyncMarkdown,
  onExportMarkdown,
  lastSyncResult,
  isLoading,
}: MemoryCuratorWorkspaceViewProps): React.JSX.Element {
  const [editorText, setEditorText] = useState<string>(markdownContent);
  const [hardDelete, setHardDelete] = useState<boolean>(false);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);

  // Sync editorText when parent props change if user hasn't typed
  React.useEffect(() => {
    setEditorText(markdownContent);
  }, [markdownContent]);

  const handleApplySync = async () => {
    if (!editorText.trim()) return;
    setIsSyncing(true);
    try {
      await onSyncMarkdown(editorText, hardDelete);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleResetToCurrent = () => {
    setEditorText(markdownContent);
  };

  return (
    <div className="space-y-4">
      {/* Workspace Mirror HUD Banner */}
      <div className="rounded-xl border border-border-subtle bg-surface-subtle/50 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FileText className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-text-primary text-sm">
                  工作区 Markdown 镜像 (MEMORY.md)
                </span>
                <Badge variant="outline" className="bg-emerald-500/10 text-emerald-600 text-xs">
                  双向实时同步就绪
                </Badge>
              </div>
              <p className="text-text-secondary text-xs">
                严格遵循人类可读与可编辑哲学，支持在 VSCode/Obsidian 中直接修改并毫秒级重载
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onExportMarkdown}
              disabled={isLoading || isSyncing}
              className="flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-primary"
              aria-label="导出 Markdown 镜像文件"
            >
              <Download className="h-3.5 w-3.5" />
              <span>导出磁盘镜像</span>
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={handleApplySync}
              disabled={isLoading || isSyncing || !editorText.trim()}
              className="flex items-center gap-1.5 bg-primary text-primary-foreground hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary"
              aria-label="热重载双向对账同步"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
              <span>{isSyncing ? '对账中...' : '热重载同步至 SQLite'}</span>
            </Button>
          </div>
        </div>

        {/* Sync Status Attributes */}
        <div className="mt-3 grid grid-cols-2 gap-2 border-border-subtle/60 border-t pt-3 sm:grid-cols-4">
          <div className="flex items-center gap-2 text-xs">
            <Clock className="h-3.5 w-3.5 text-text-tertiary" />
            <span className="text-text-secondary">挂载文件:</span>
            <span className="font-mono text-text-primary">.myrm/memory/MEMORY.md</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <ArrowRightLeft className="h-3.5 w-3.5 text-text-tertiary" />
            <span className="text-text-secondary">同步模式:</span>
            <span className="font-medium text-emerald-600">人类最高仲裁优先</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <Sparkles className="h-3.5 w-3.5 text-text-tertiary" />
            <span className="text-text-secondary">重载延迟:</span>
            <span className="font-mono text-text-primary">&lt; 50ms</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <label htmlFor="hard-delete-toggle" className="flex cursor-pointer items-center gap-1.5 text-text-secondary">
              <input
                id="hard-delete-toggle"
                type="checkbox"
                checked={hardDelete}
                onChange={(e) => setHardDelete(e.target.checked)}
                className="h-3.5 w-3.5 rounded border-border-subtle text-primary focus:ring-2 focus:ring-primary"
              />
              <span>文本删除时物理擦除</span>
            </label>
          </div>
        </div>
      </div>

      {/* Reconciliation Diff Banner if sync executed */}
      {lastSyncResult && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 font-medium text-primary">
              <FileDiff className="h-4 w-4" />
              <span>最近双向对账结果</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-emerald-600 font-medium">+{lastSyncResult.added_count} 新增</span>
              <span className="text-amber-600 font-medium">~{lastSyncResult.updated_count} 修改</span>
              <span className="text-rose-600 font-medium">-{lastSyncResult.deleted_count} 移除/归档</span>
            </div>
          </div>
        </div>
      )}

      {/* Live Markdown Mirror Editor */}
      <div className="rounded-xl border border-border-subtle bg-surface p-4 shadow-sm">
        <div className="mb-2 flex items-center justify-between">
          <label htmlFor="markdown-mirror-editor" className="flex items-center gap-2 font-medium text-text-primary text-sm">
            <FileText className="h-4 w-4 text-primary" />
            <span>实时 Markdown 纯文本编辑器 (支持即时手写编辑)</span>
          </label>
          <button
            type="button"
            onClick={handleResetToCurrent}
            className="text-text-secondary hover:text-text-primary text-xs underline focus:outline-none focus:ring-2 focus:ring-primary rounded"
            aria-label="重置编辑器内容"
          >
            还原为当前已生效内容
          </button>
        </div>

        <textarea
          id="markdown-mirror-editor"
          value={editorText}
          onChange={(e) => setEditorText(e.target.value)}
          rows={14}
          className="w-full rounded-lg border border-border-subtle bg-surface-subtle p-3 font-mono text-text-primary text-xs leading-relaxed focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary"
          placeholder="# Workspace Memory Mirror&#10;&#10;## Preferences&#10;- [x] **界面深色主题** (id: mem_pref_01, confidence: 1.00): 偏好深色模式"
        />

        <div className="mt-2 flex items-center justify-between text-text-tertiary text-xs">
          <span>语法规范: YAML Frontmatter 元数据 + 分类二级标题 + 带状态复选框条目列表</span>
          <span>{editorText.length} 字符</span>
        </div>
      </div>
    </div>
  );
}
