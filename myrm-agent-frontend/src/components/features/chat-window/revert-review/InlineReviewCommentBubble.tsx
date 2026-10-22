/**
 * [INPUT]
 * - ./revertReviewTypes::InlineReviewComment, SurgicalFixPayload
 * - ./useTurnRevertReviewStore::buildSurgicalFixPrompt
 * - lucide-react::MessageSquareCode, Sparkles, X, CornerDownLeft
 *
 * [OUTPUT]
 * - InlineReviewCommentBubble: Diff 视图行内划词/行号浮动批注气泡组件
 *
 * [POS]
 * 会话流 Diff 行内划词批注与一键定向修复的浮动气泡组件。
 */

'use client';

import React, { useState, useCallback } from 'react';
import { MessageSquareCode, Sparkles, X, CornerDownLeft } from 'lucide-react';
import type { InlineReviewComment, SurgicalFixPayload } from './revertReviewTypes';
import { buildSurgicalFixPrompt } from './useTurnRevertReviewStore';

export interface InlineReviewCommentBubbleProps {
  filePath: string;
  lineNumber: number;
  lineType?: 'addition' | 'deletion' | 'context';
  selectedCode?: string;
  sessionId: string;
  messageId?: string;
  onDismiss: () => void;
  onSubmitFix: (comment: InlineReviewComment, prompt: string) => void;
  className?: string;
}

const PRESET_COMMENTS: readonly string[] = [
  '防御性判空处理',
  '符合单一职责与语义重命名',
  '补全类型收敛（禁用 any）',
  '增加边界异常兜底',
];

export const InlineReviewCommentBubble: React.FC<InlineReviewCommentBubbleProps> = ({
  filePath,
  lineNumber,
  lineType = 'context',
  selectedCode = '',
  sessionId,
  messageId,
  onDismiss,
  onSubmitFix,
  className = '',
}) => {
  const [commentText, setCommentText] = useState('');

  const handleApplyPreset = useCallback((preset: string) => {
    setCommentText((prev) => (prev ? `${prev}；${preset}` : preset));
  }, []);

  const handleSubmit = useCallback(() => {
    const trimmed = commentText.trim();
    if (!trimmed) {
      return;
    }

    const comment: InlineReviewComment = {
      id: `comment-${Date.now()}`,
      filePath,
      lineNumber,
      lineType,
      selectedCode,
      comment: trimmed,
      createdAt: Date.now(),
    };

    const payload: SurgicalFixPayload = {
      filePath,
      lineNumber,
      selectedCode,
      comment: trimmed,
      sessionId,
      messageId,
    };

    const prompt = buildSurgicalFixPrompt(payload);
    onSubmitFix(comment, prompt);
  }, [commentText, filePath, lineNumber, lineType, selectedCode, sessionId, messageId, onSubmitFix]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        handleSubmit();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onDismiss();
      }
    },
    [handleSubmit, onDismiss]
  );

  const fileName = filePath.split('/').pop() || filePath;

  return (
    <section
      aria-label="行内代码审查批注"
      className={`rounded-lg border border-border/80 bg-background/95 p-3 shadow-xl backdrop-blur-md text-xs w-80 max-w-full ${className}`}
    >
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-border/50">
        <div className="flex items-center gap-1.5 font-medium text-foreground truncate">
          <MessageSquareCode className="w-3.5 h-3.5 text-primary shrink-0" aria-hidden="true" />
          <span className="truncate">{fileName}</span>
          <span className="px-1.5 py-0.2 rounded bg-muted text-[10px] text-muted-foreground shrink-0">
            L{lineNumber}
          </span>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="text-muted-foreground hover:text-foreground p-0.5 rounded transition-colors"
          aria-label="关闭批注气泡"
        >
          <X className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      </div>

      {selectedCode ? (
        <div className="mb-2 p-1.5 rounded bg-muted/60 font-mono text-[11px] text-muted-foreground truncate max-h-12 border border-border/30">
          <code>{selectedCode.trim()}</code>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-1 mb-2">
        {PRESET_COMMENTS.map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => {
              handleApplyPreset(preset);
            }}
            className="text-[10px] px-1.5 py-0.5 rounded bg-secondary/80 text-secondary-foreground hover:bg-secondary transition-colors"
          >
            {preset}
          </button>
        ))}
      </div>

      <textarea
        value={commentText}
        onChange={(e) => {
          setCommentText(e.target.value);
        }}
        onKeyDown={handleKeyDown}
        placeholder="输入审查意见，按 Cmd+Enter 快速提交..."
        rows={3}
        className="w-full resize-none rounded-md border border-input bg-transparent px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary mb-2 font-sans"
        aria-label="代码审查批注内容"
      />

      <div className="flex items-center justify-between pt-1">
        <span className="text-[10px] text-muted-foreground/70 flex items-center gap-1">
          <CornerDownLeft className="w-3 h-3" aria-hidden="true" />
          <span>Cmd+Enter 发送</span>
        </span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onDismiss}
            className="px-2 py-1 rounded text-[11px] text-muted-foreground hover:bg-muted transition-colors"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!commentText.trim()}
            className="flex items-center gap-1 px-2.5 py-1 rounded bg-primary text-primary-foreground text-[11px] font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors shadow-sm"
          >
            <Sparkles className="w-3 h-3" aria-hidden="true" />
            <span>定向修复</span>
          </button>
        </div>
      </div>
    </section>
  );
};
