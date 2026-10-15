/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Vector Icons)
 * - @/components/features/chat-window/three-pane-studio/threePaneStudioTypes
 * - @/components/features/chat-window/three-pane-studio/useThreePaneStudioStore
 *
 * [OUTPUT]
 * - MiddleContentPane (POS: Middle pane file/memory content viewer and Markdown previewer)
 *
 * [POS]
 * Central content explorer for Item 198 (P0): ThreePaneContextStudioAndRealtimeToolHighlightSuite.
 * Renders selected context node content, Agent read/write live indicators,
 * metadata attributes, and provides one-click content copying.
 */

import React, { useState } from 'react';
import {
  FileText,
  Copy,
  Check,
  FileQuestion,
  Hash,
  Clock,
} from 'lucide-react';
import type { ContextTreeNode } from './threePaneStudioTypes';
import { useThreePaneStudioStore } from './useThreePaneStudioStore';

export interface MiddleContentPaneProps {
  readonly nodeOverride?: ContextTreeNode | null;
  readonly className?: string;
}

export const MiddleContentPane: React.FC<MiddleContentPaneProps> = ({
  nodeOverride,
  className = '',
}) => {
  const store = useThreePaneStudioStore();
  const activeNode = nodeOverride !== undefined ? nodeOverride : store.getSelectedNode();
  const [copied, setCopied] = useState(false);

  const handleCopyContent = async () => {
    if (!activeNode?.content) {
      return;
    }

    if (typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      try {
        await navigator.clipboard.writeText(activeNode.content);
        setCopied(true);
        setTimeout(() => {
          setCopied(false);
        }, 2000);
      } catch {
        setCopied(false);
      }
    }
  };

  if (!activeNode) {
    return (
      <main
        data-testid="middle-content-pane-empty"
        className={`flex flex-col items-center justify-center h-full p-6 text-center bg-slate-950/60 border-r border-slate-800/80 ${className}`}
      >
        <div className="p-3 mb-3 rounded-full bg-slate-900 border border-slate-800 text-slate-500">
          <FileQuestion className="w-8 h-8" />
        </div>
        <h3 className="text-sm font-semibold text-slate-300">
          未选择任何上下文条目
        </h3>
        <p className="max-w-xs mt-1 text-xs text-slate-500">
          请从左侧上下文树中点击条目进行查阅，或等待智能体在执行任务时自动为您加载被操作的文件与记忆。
        </p>
      </main>
    );
  }

  const contentText = activeNode.content ?? '/* 当前条目暂无正文内容 */';
  const lineCount = contentText.split('\n').length;
  const charCount = contentText.length;

  return (
    <main
      data-testid="middle-content-pane"
      className={`flex flex-col h-full bg-slate-950 border-r border-slate-800/80 min-w-0 ${className}`}
    >
      {/* 头部元数据栏 */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-slate-800/80 bg-slate-900/60 shrink-0">
        <div className="flex items-center gap-2 min-w-0 flex-1 mr-2">
          <FileText className="w-4 h-4 text-cyan-400 shrink-0" />
          <div className="flex flex-col min-w-0">
            <span
              data-testid="node-title"
              className="text-xs font-semibold text-slate-200 truncate"
            >
              {activeNode.label}
            </span>
            <span
              data-testid="node-path"
              className="text-[10px] font-mono text-slate-500 truncate"
              title={activeNode.path}
            >
              {activeNode.path}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="hidden sm:flex items-center gap-2 text-[10px] font-mono text-slate-500 border-r border-slate-800 pr-2">
            <span className="flex items-center gap-0.5">
              <Hash className="w-3 h-3" />
              {lineCount} 行
            </span>
            <span>{charCount} 字符</span>
          </div>

          <button
            type="button"
            data-testid="btn-copy-content"
            aria-label="复制内容"
            title="复制正文到剪贴板"
            onClick={handleCopyContent}
            className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors focus:outline-none focus:ring-1 focus:ring-cyan-500"
          >
            {copied ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* 状态徽章浮条 (若 Agent 正在读写) */}
      {activeNode.status && activeNode.status !== 'idle' && (
        <div
          data-testid="agent-live-action-banner"
          className="flex items-center gap-1.5 px-4 py-1 bg-cyan-950/40 border-b border-cyan-900/40 text-[11px] text-cyan-300"
        >
          <Clock className="w-3 h-3 animate-spin text-cyan-400" />
          <span>
            智能体当前状态：
            {activeNode.status === 'reading' && '正在读取该条目上下文...'}
            {activeNode.status === 'writing' && '正在向该条目写入生成产物...'}
            {activeNode.status === 'modified' && '已完成文件变更与固化'}
          </span>
        </div>
      )}

      {/* 内容区域 */}
      <div className="flex-1 overflow-auto p-4 font-mono text-xs text-slate-300 leading-relaxed scrollbar-thin">
        <pre
          data-testid="node-content-body"
          className="whitespace-pre-wrap break-words font-mono bg-slate-900/40 p-3 rounded border border-slate-800/60"
        >
          {contentText}
        </pre>
      </div>
    </main>
  );
};
