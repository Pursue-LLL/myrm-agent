/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Consistent vector icons)
 * - @/components/features/chat-window/modal-editor/modalEditorTypes
 * - @/components/features/chat-window/modal-editor/modalEditorEngine
 * - @/components/features/chat-window/modal-editor/useModalEditorStore
 *
 * [OUTPUT]
 * - PopoutFullscreenModalEditor (POS: Immersive fullscreen modal Markdown composer)
 *
 * [POS]
 * Primary modal UI for Item 196 (P1): PopoutFullscreenModalEditorAndDesktopBridgeSuite.
 * Resolves long-form PRDs, logs, and multi-paragraph prompts via pop-out modal composing (Ctrl+G).
 */

import React, { useEffect, useCallback } from 'react';
import {
  FileEdit,
  Columns,
  Eye,
  EyeOff,
  ExternalLink,
  X,
  Check,
  BookOpen,
  Hash,
  Type,
  CornerDownLeft,
} from 'lucide-react';
import {
  BUILTIN_EDITOR_TEMPLATES,
  calculateEditorMetrics,
} from './modalEditorEngine';
import { useModalEditorStore } from './useModalEditorStore';

export interface PopoutFullscreenModalEditorProps {
  readonly sessionId?: string;
  readonly onConfirm?: (content: string) => void;
  readonly onCancel?: () => void;
  readonly className?: string;
}

export const PopoutFullscreenModalEditor: React.FC<PopoutFullscreenModalEditorProps> = ({
  sessionId = 'current_session',
  onConfirm,
  onCancel,
  className = '',
}) => {
  const isOpen = useModalEditorStore((state) => state.isOpen);
  const content = useModalEditorStore((state) => state.content);
  const isPreviewOpen = useModalEditorStore((state) => state.isPreviewOpen);
  const setContent = useModalEditorStore((state) => state.setContent);
  const insertTemplate = useModalEditorStore((state) => state.insertTemplate);
  const togglePreview = useModalEditorStore((state) => state.togglePreview);
  const openExternalEditor = useModalEditorStore((state) => state.openExternalEditor);
  const confirmEdit = useModalEditorStore((state) => state.confirmEdit);
  const cancelEdit = useModalEditorStore((state) => state.cancelEdit);

  const metrics = calculateEditorMetrics(content);

  const handleConfirm = useCallback(() => {
    const text = confirmEdit();
    if (onConfirm) {
      onConfirm(text);
    }
  }, [confirmEdit, onConfirm]);

  const handleCancel = useCallback(() => {
    cancelEdit();
    if (onCancel) {
      onCancel();
    }
  }, [cancelEdit, onCancel]);

  // 快捷键支持：Cmd/Ctrl + Enter 提交，Escape 取消
  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        handleConfirm();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        handleCancel();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, handleConfirm, handleCancel]);

  if (!isOpen) {
    return null;
  }

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="modal-editor-title"
      data-testid="popout-fullscreen-modal-editor"
      onCancel={handleCancel}
      className={`fixed inset-0 z-50 m-0 flex h-full w-full max-h-none max-w-none items-center justify-center bg-transparent p-4 sm:p-6 border-none ${className}`}
    >
      {/* 语义化全屏背景遮罩按钮 */}
      <button
        type="button"
        aria-label="关闭背景遮罩"
        data-testid="modal-editor-backdrop"
        onClick={handleCancel}
        className="fixed inset-0 -z-10 h-full w-full bg-black/70 backdrop-blur-md cursor-default border-none p-0 m-0"
      />

      <div className="relative w-full max-w-5xl h-[88vh] flex flex-col rounded-2xl border border-border bg-card shadow-2xl overflow-hidden">
        {/* 对话框头部 */}
        <div className="flex items-center justify-between border-b border-border/80 px-5 py-3.5 bg-muted/40">
          <div className="flex items-center gap-2.5">
            <FileEdit className="w-4 h-4 text-primary" />
            <h3 id="modal-editor-title" className="text-sm font-semibold text-foreground">
              全屏 Markdown 撰写与长公文排版
            </h3>
            <span className="hidden sm:inline-flex rounded-full border border-border/60 bg-muted/40 px-2 py-0.5 text-[10px] font-mono text-muted-foreground">
              Ctrl+G
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* 双栏预览切换 */}
            <button
              type="button"
              onClick={() => {
                togglePreview();
              }}
              title={isPreviewOpen ? '切换为纯编辑模式' : '开启双栏实时预览'}
              aria-label="切换双栏实时预览"
              className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                isPreviewOpen
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-foreground'
              }`}
            >
              <Columns className="w-3.5 h-3.5" />
              <span>{isPreviewOpen ? '双栏开启' : '双栏预览'}</span>
            </button>

            {/* 外部桌面编辑器拉起 */}
            <button
              type="button"
              onClick={() => {
                openExternalEditor(sessionId);
              }}
              title="拉起桌面外部记事本/VSCode 编辑"
              aria-label="拉起桌面外部编辑器"
              className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">桌面外部编辑</span>
            </button>

            <button
              type="button"
              onClick={handleCancel}
              title="放弃修改并关闭"
              aria-label="放弃修改并关闭"
              className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* 模板与指标工具栏 */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 px-5 py-2 bg-muted/20 text-xs">
          <div className="flex items-center gap-1.5 overflow-x-auto">
            <span className="flex items-center gap-1 text-muted-foreground font-medium shrink-0">
              <BookOpen className="w-3.5 h-3.5" />
              <span>模版插入:</span>
            </span>
            {BUILTIN_EDITOR_TEMPLATES.map((tmpl) => (
              <button
                key={tmpl.id}
                type="button"
                onClick={() => {
                  insertTemplate(tmpl.id);
                }}
                title={tmpl.description}
                className="rounded-md border border-border/50 bg-card px-2 py-0.5 text-[11px] font-medium text-foreground/80 hover:bg-accent hover:text-foreground transition-colors shrink-0"
              >
                {tmpl.name}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3 font-mono text-[11px] text-muted-foreground shrink-0">
            <span className="flex items-center gap-0.5">
              <Type className="w-3 h-3 text-sky-500" />
              <span>{metrics.charCount} 字符</span>
            </span>
            <span>·</span>
            <span className="flex items-center gap-0.5">
              <Hash className="w-3 h-3 text-emerald-500" />
              <span>{metrics.wordCount} 词</span>
            </span>
            <span>·</span>
            <span>{metrics.lineCount} 行</span>
          </div>
        </div>

        {/* 编辑器核心区域 */}
        <div className="flex-1 flex overflow-hidden">
          {/* 左侧主编辑框 */}
          <div className={`h-full flex flex-col p-4 ${isPreviewOpen ? 'w-1/2 border-r border-border/60' : 'w-full'}`}>
            <textarea
              value={content}
              onChange={(e) => {
                setContent(e.target.value);
              }}
              placeholder="在此输入大篇幅公文材料、PRD 需求规格或报错日志（支持标准 Markdown 语法，Ctrl+Enter 完成）..."
              aria-label="Markdown 撰写内容"
              data-testid="modal-editor-textarea"
              className="w-full flex-1 resize-none bg-transparent font-mono text-sm leading-relaxed text-foreground placeholder:text-muted-foreground/60 focus:outline-none"
            />
          </div>

          {/* 右侧双栏实时预览区 */}
          {isPreviewOpen ? (
            <div
              data-testid="modal-editor-preview-panel"
              className="w-1/2 h-full overflow-y-auto p-5 bg-muted/10 font-sans text-sm text-foreground leading-relaxed"
            >
              <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                实时渲染预览
              </div>
              <div className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap font-sans">
                {content.trim() ? content : <span className="text-muted-foreground/50">暂无内容预览</span>}
              </div>
            </div>
          ) : null}
        </div>

        {/* 底部按钮栏 */}
        <div className="flex items-center justify-between border-t border-border px-5 py-3 bg-muted/30">
          <div className="text-[11px] text-muted-foreground flex items-center gap-1.5">
            <span>Esc 键直接取消（不影响输入框已有内容）</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleCancel}
              className="rounded-lg border border-border bg-card px-4 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            >
              放弃退出
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              data-testid="modal-editor-confirm-button"
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors shadow-sm"
            >
              <Check className="w-3.5 h-3.5" />
              <span>完成并填入输入框</span>
              <CornerDownLeft className="w-3 h-3 opacity-70" />
            </button>
          </div>
        </div>
      </div>
    </dialog>
  );
};
