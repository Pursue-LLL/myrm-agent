/**
 * [INPUT]
 * - ./revertReviewTypes::InlineReviewComment
 * - ./InlineReviewCommentBubble::InlineReviewCommentBubble
 * - ./useTurnRevertReviewStore::useTurnRevertReviewStore
 * - @/lib/diff/DiffViewer::DiffViewer
 * - lucide-react::FileText, X, MessageSquarePlus, CheckCircle2
 *
 * [OUTPUT]
 * - DiffReviewContainer: 结合 DiffViewer 与行内批注修复能力的审查容器组件
 *
 * [POS]
 * 在 Diff 视图中赋予用户点击代码行添加批注并一键定向派发 Agent 修复的能力。
 */

'use client';

import React, { useState, useCallback } from 'react';
import { FileText, X, MessageSquarePlus, CheckCircle2 } from 'lucide-react';
import { DiffViewer } from '@/lib/diff/DiffViewer';
import { InlineReviewCommentBubble } from './InlineReviewCommentBubble';
import { useTurnRevertReviewStore } from './useTurnRevertReviewStore';
import type { InlineReviewComment } from './revertReviewTypes';

export interface DiffReviewContainerProps {
  filePath: string;
  diff: string;
  sessionId: string;
  messageId?: string;
  onClose?: () => void;
  onSubmitFix?: (comment: InlineReviewComment, prompt: string) => void;
  className?: string;
}

export const DiffReviewContainer: React.FC<DiffReviewContainerProps> = ({
  filePath,
  diff,
  sessionId,
  messageId,
  onClose,
  onSubmitFix,
  className = '',
}) => {
  const [activeLine, setActiveLine] = useState<number | null>(null);
  const [submittedFixPrompt, setSubmittedFixPrompt] = useState<string | null>(null);

  const addComment = useTurnRevertReviewStore((s) => s.addComment);
  const fileName = filePath.split('/').pop() || filePath;

  const handleLineClick = useCallback((lineNum: number) => {
    setActiveLine(lineNum);
    setSubmittedFixPrompt(null);
  }, []);

  const handleDismissBubble = useCallback(() => {
    setActiveLine(null);
  }, []);

  const handleSubmitFix = useCallback(
    (comment: InlineReviewComment, prompt: string) => {
      addComment(comment);
      setActiveLine(null);
      setSubmittedFixPrompt(prompt);
      if (onSubmitFix) {
        onSubmitFix(comment, prompt);
      }
    },
    [addComment, onSubmitFix]
  );

  return (
    <section
      aria-label={`Diff 审查与行内批注容器 - ${fileName}`}
      className={`flex flex-col rounded-xl border border-border bg-background shadow-2xl overflow-hidden ${className}`}
    >
      <div className="flex items-center justify-between px-4 py-2.5 bg-muted/40 border-b border-border/80 text-xs">
        <div className="flex items-center gap-2 font-medium text-foreground truncate">
          <FileText className="w-4 h-4 text-primary shrink-0" aria-hidden="true" />
          <span className="font-semibold truncate">{fileName}</span>
          <span className="text-muted-foreground font-mono text-[11px] truncate max-w-xs">
            {filePath}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => {
              handleLineClick(1);
            }}
            className="flex items-center gap-1 px-2.5 py-1 rounded bg-secondary text-secondary-foreground hover:bg-secondary/80 text-[11px] font-medium transition-colors"
            aria-label="添加行内审查批注"
          >
            <MessageSquarePlus className="w-3.5 h-3.5" aria-hidden="true" />
            <span>添加行内批注</span>
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              aria-label="关闭 Diff 审查容器"
            >
              <X className="w-4 h-4" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      {submittedFixPrompt && (
        <div className="flex items-center gap-2 px-4 py-2 bg-emerald-500/10 border-b border-emerald-500/20 text-xs text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" aria-hidden="true" />
          <span className="truncate">已成功提交定向修复指令至会话上下文！</span>
          <button
            type="button"
            onClick={() => {
              setSubmittedFixPrompt(null);
            }}
            className="ml-auto text-emerald-600 dark:text-emerald-400 hover:underline text-[11px]"
          >
            忽略
          </button>
        </div>
      )}

      <div className="relative flex-1 overflow-auto max-h-[600px] p-2">
        <DiffViewer
          diff={diff}
          filePath={filePath}
          embedded={true}
          defaultViewMode="unified"
        />

        {activeLine !== null && (
          <div className="absolute top-6 right-6 z-30 animate-in fade-in zoom-in-95 duration-150">
            <InlineReviewCommentBubble
              filePath={filePath}
              lineNumber={activeLine}
              sessionId={sessionId}
              messageId={messageId}
              onDismiss={handleDismissBubble}
              onSubmitFix={handleSubmitFix}
            />
          </div>
        )}
      </div>
    </section>
  );
};
