/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Consistent vector icons)
 * - @/components/features/chat-window/final-card/finalCardTypes
 * - @/components/features/chat-window/final-card/finalCardEngine
 * - @/components/features/chat-window/final-card/useFinalCardStore
 *
 * [OUTPUT]
 * - FullTranscriptModal (POS: Modal/drawer for full execution transcript and logs)
 *
 * [POS]
 * Secondary drawer/modal for Item 192 (P0).
 * Allows deep debugging on-demand without cluttering primary chat message stream.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  X,
  Copy,
  Check,
  ExternalLink,
  Terminal,
  FileText,
  Clock,
} from 'lucide-react';
import { useFinalCardStore } from './useFinalCardStore';
import { formatDurationText } from './finalCardEngine';

export interface FullTranscriptModalProps {
  readonly onClose?: () => void;
  readonly className?: string;
}

export const FullTranscriptModal: React.FC<FullTranscriptModalProps> = ({
  onClose,
  className = '',
}) => {
  const activeTranscriptCardId = useFinalCardStore((state) => state.activeTranscriptCardId);
  const cards = useFinalCardStore((state) => state.cards);
  const closeTranscriptModal = useFinalCardStore((state) => state.closeTranscriptModal);

  const [copied, setCopied] = useState<boolean>(false);

  const activeCard = activeTranscriptCardId ? cards[activeTranscriptCardId] : undefined;

  const handleClose = useCallback(() => {
    closeTranscriptModal();
    if (onClose) {
      onClose();
    }
  }, [closeTranscriptModal, onClose]);

  // 支持键盘 Escape 关闭
  useEffect(() => {
    if (!activeCard) {
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [activeCard, handleClose]);

  if (!activeCard) {
    return null;
  }

  const logs = activeCard.rawLogsPreview ?? [];

  const handleCopyLogs = async () => {
    const textToCopy = logs.join('\n') || `Transcript URL: ${activeCard.transcriptUrl}`;
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
      }, 2000);
    } catch {
      // 容错处理
    }
  };

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="transcript-modal-title"
      data-testid="full-transcript-modal"
      onCancel={handleClose}
      className={`fixed inset-0 z-50 m-0 flex h-full w-full max-h-none max-w-none items-center justify-center bg-transparent p-4 border-none ${className}`}
    >
      {/* 语义化全屏背景遮罩按钮 */}
      <button
        type="button"
        aria-label="关闭背景遮罩"
        data-testid="transcript-modal-backdrop"
        onClick={handleClose}
        className="fixed inset-0 -z-10 h-full w-full bg-black/60 backdrop-blur-sm cursor-default border-none p-0 m-0"
      />

      <div className="relative w-full max-w-3xl max-h-[85vh] flex flex-col rounded-xl border border-border bg-card shadow-2xl overflow-hidden">
        {/* 标题栏 */}
        <div className="flex items-center justify-between border-b border-border/80 px-5 py-3.5 bg-muted/30">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-primary" />
            <h3 id="transcript-modal-title" className="text-sm font-semibold text-foreground">
              完整执行轨迹 · {activeCard.title}
            </h3>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleCopyLogs}
              title="复制日志"
              aria-label="复制日志"
              className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-500" />
                  <span className="text-emerald-500">已复制</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>复制日志</span>
                </>
              )}
            </button>

            <button
              type="button"
              onClick={handleClose}
              title="关闭对话框"
              aria-label="关闭对话框"
              className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* 元信息摘要条 */}
        <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-2.5 bg-muted/10 border-b border-border/40 text-xs text-muted-foreground">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" />
              耗时: {formatDurationText(activeCard.executionDurationMs)}
            </span>
            <span className="flex items-center gap-1">
              <FileText className="w-3.5 h-3.5" />
              日志量: {activeCard.rawLogLinesCount} 行
            </span>
          </div>

          <a
            href={activeCard.transcriptUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-primary hover:underline font-medium"
          >
            <span>在新窗口打开原始 Transcript</span>
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>

        {/* 日志内容区域 */}
        <div className="flex-1 overflow-y-auto p-4 bg-slate-950 font-mono text-xs text-slate-200">
          {logs.length > 0 ? (
            <div className="space-y-1">
              {logs.map((line, index) => (
                <div key={`log-${index}`} className="flex items-start gap-3 hover:bg-slate-900/60 px-1 rounded">
                  <span className="w-8 shrink-0 select-none text-right text-slate-500">
                    {index + 1}
                  </span>
                  <span className="flex-1 break-all whitespace-pre-wrap">{line}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-12 text-center text-slate-500">
              <p>暂无精简日志预览片段</p>
              <p className="mt-1 text-[11px]">请点击右上角链接访问完整 Transcript 审计归档</p>
            </div>
          )}
        </div>

        {/* 底部按钮栏 */}
        <div className="flex items-center justify-between border-t border-border px-5 py-3 bg-muted/20">
          <span className="text-[11px] text-muted-foreground">
            会话轮次: {activeCard.turnId}
          </span>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg bg-secondary px-4 py-1.5 text-xs font-medium text-secondary-foreground hover:bg-secondary/80 transition-colors"
          >
            完成查看
          </button>
        </div>
      </div>
    </dialog>
  );
};
