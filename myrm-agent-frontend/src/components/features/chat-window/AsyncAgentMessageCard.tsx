// @orphan-ok Dedicated UI card for non-blocking asynchronous agent communication entries
/**
 * [INPUT]
 * - lucide-react (POS: UI 矢量图标库)
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind 样式合并纯函数)
 *
 * [OUTPUT]
 * - AsyncAgentMessageCard: 智能体长任务执行中主动异步汇报与非阻塞交互卡片
 * - AsyncAgentMessageCardProps: 卡片属性类型定义
 * - AsyncMessageCategory: 消息类别枚举类型 ('progress' | 'milestone' | 'question')
 *
 * [POS]
 * 聊天窗口内专用的异步消息卡片。支持进度、里程碑与带预案澄清提问呈现，
 * 支持一键采纳预案或自定义回复，无感驱动 SteeringToken 注入。
 */
import React, { useState } from 'react';
import {
  Radio,
  Milestone,
  HelpCircle,
  Check,
  CheckCircle2,
  CornerDownLeft,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export type AsyncMessageCategory = 'progress' | 'milestone' | 'question';

export interface AsyncAgentMessageCardProps {
  callId: string;
  message: string;
  category?: AsyncMessageCategory;
  recommendation?: string | null;
  suggestedReplies?: string[];
  suggested_replies?: string[];
  onSteerReply?: (reply: string, callId: string, questionContext?: string) => Promise<void> | void;
  className?: string;
}

export const AsyncAgentMessageCard: React.FC<AsyncAgentMessageCardProps> = ({
  callId,
  message,
  category = 'progress',
  recommendation,
  suggestedReplies,
  suggested_replies,
  onSteerReply,
  className,
}) => {
  const [resolved, setResolved] = useState(false);
  const [resolvedText, setResolvedText] = useState<string | null>(null);
  const [customReply, setCustomReply] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showCustomInput, setShowCustomInput] = useState(false);

  const effectiveReplies = (suggestedReplies ?? suggested_replies)?.filter(
    (item): item is string => typeof item === 'string' && item.trim().length > 0,
  );

  const handleSelectSuggestedReply = async (reply: string) => {
    if (!reply || isSubmitting) return;
    setIsSubmitting(true);
    try {
      if (onSteerReply) {
        await onSteerReply(reply, callId, message);
      }
      setResolved(true);
      setResolvedText(reply);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAdoptRecommendation = async () => {
    if (!recommendation || isSubmitting) return;
    setIsSubmitting(true);
    try {
      if (onSteerReply) {
        await onSteerReply(recommendation, callId, message);
      }
      setResolved(true);
      setResolvedText(recommendation);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCustomSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = customReply.trim();
    if (!text || isSubmitting) return;
    setIsSubmitting(true);
    try {
      if (onSteerReply) {
        await onSteerReply(text, callId, message);
      }
      setResolved(true);
      setResolvedText(text);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (resolved) {
    return (
      <div
        role="status"
        aria-live="polite"
        className={cn(
          'my-2 flex items-center justify-between rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-xs transition-all duration-200 dark:border-emerald-500/20 dark:bg-emerald-500/10',
          className,
        )}
      >
        <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
          <CheckCircle2 className="h-3.5 w-3.5" />
          <span className="font-medium">已确认决策：</span>
          <span className="line-clamp-1 opacity-90">{resolvedText}</span>
        </div>
        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">RESOLVED</span>
      </div>
    );
  }

  const isQuestion = category === 'question';
  const isMilestone = category === 'milestone';

  return (
    <div
      role="region"
      aria-label={`Agent ${category} update`}
      className={cn(
        'group relative my-2 w-full rounded-xl border p-3.5 transition-all duration-200 text-xs shadow-xs',
        isQuestion && 'border-amber-500/30 bg-amber-500/5 dark:border-amber-500/20 dark:bg-amber-500/5',
        isMilestone && 'border-emerald-500/30 bg-emerald-500/5 dark:border-emerald-500/20 dark:bg-emerald-500/5',
        !isQuestion && !isMilestone && 'border-blue-500/30 bg-blue-500/5 dark:border-blue-500/20 dark:bg-blue-500/5',
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-2">
          {isQuestion && (
            <div className="flex h-5 w-5 items-center justify-center rounded-md bg-amber-500/15 text-amber-600 dark:bg-amber-500/20 dark:text-amber-400">
              <HelpCircle className="h-3 w-3" />
            </div>
          )}
          {isMilestone && (
            <div className="flex h-5 w-5 items-center justify-center rounded-md bg-emerald-500/15 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400">
              <Milestone className="h-3 w-3" />
            </div>
          )}
          {!isQuestion && !isMilestone && (
            <div className="flex h-5 w-5 items-center justify-center rounded-md bg-blue-500/15 text-blue-600 dark:bg-blue-500/20 dark:text-blue-400">
              <Radio className="h-3 w-3 animate-pulse" />
            </div>
          )}
          <span
            className={cn(
              'font-semibold uppercase tracking-wider text-[11px]',
              isQuestion && 'text-amber-700 dark:text-amber-300',
              isMilestone && 'text-emerald-700 dark:text-emerald-300',
              !isQuestion && !isMilestone && 'text-blue-700 dark:text-blue-300',
            )}
          >
            {isQuestion ? '非阻塞决策征询' : isMilestone ? '阶段性成果' : '实时进度通报'}
          </span>
        </div>
        <span className="text-[10px] text-muted-foreground font-mono opacity-80">ID: {callId.slice(-6)}</span>
      </div>

      <div className="text-foreground/90 font-normal leading-relaxed pl-7">{message}</div>

      {isQuestion && recommendation && (
        <div className="mt-2.5 ml-7 rounded-lg border border-border/60 bg-background/50 p-2.5 backdrop-blur-xs">
          <div className="flex items-center justify-between gap-2">
            <div>
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block mb-0.5">
                推荐采纳预案
              </span>
              <p className="text-foreground/80 leading-snug">{recommendation}</p>
            </div>
            <button
              type="button"
              disabled={isSubmitting}
              onClick={handleAdoptRecommendation}
              className="inline-flex shrink-0 items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-[11px] font-medium text-primary-foreground shadow-xs hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              <Check className="h-3 w-3" />
              <span>采纳</span>
            </button>
          </div>

          <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-[11px]">
            <button
              type="button"
              onClick={() => setShowCustomInput((prev) => !prev)}
              className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
            >
              <span>{showCustomInput ? '收起自定义' : '自定义回复'}</span>
              {showCustomInput ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
          </div>

          {showCustomInput && (
            <form onSubmit={handleCustomSubmit} className="mt-2 flex gap-2">
              <input
                type="text"
                value={customReply}
                onChange={(e) => setCustomReply(e.target.value)}
                placeholder="输入指导或补充说明..."
                className="flex-1 rounded-md border border-input bg-background px-2.5 py-1 text-xs focus:outline-hidden focus:ring-1 focus:ring-ring"
              />
              <button
                type="submit"
                disabled={isSubmitting || !customReply.trim()}
                className="inline-flex items-center gap-1 rounded-md bg-secondary px-2.5 py-1 text-xs font-medium text-secondary-foreground hover:bg-secondary/80 disabled:opacity-50 transition-colors"
              >
                <CornerDownLeft className="h-3 w-3" />
                <span>发送</span>
              </button>
            </form>
          )}
        </div>
      )}

      {effectiveReplies && effectiveReplies.length > 0 && (
        <div className="mt-2.5 ml-7 flex flex-wrap gap-1.5 items-center">
          {effectiveReplies.map((replyText, idx) => (
            <button
              key={`${idx}-${replyText}`}
              type="button"
              disabled={isSubmitting}
              onClick={() => handleSelectSuggestedReply(replyText)}
              className="inline-flex items-center rounded-md border border-border/80 bg-background/80 px-2 py-1 text-[11px] font-medium text-foreground hover:bg-accent hover:text-accent-foreground disabled:opacity-50 transition-colors shadow-2xs cursor-pointer"
            >
              <span>{replyText}</span>
            </button>
          ))}
        </div>
      )}

      {isQuestion && !recommendation && (
        <div className="mt-2.5 ml-7">
          <div className="flex items-center justify-between text-[11px]">
            <button
              type="button"
              onClick={() => setShowCustomInput((prev) => !prev)}
              className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
            >
              <span>{showCustomInput ? '收起自定义回复' : '自定义回复'}</span>
              {showCustomInput ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
          </div>

          {showCustomInput && (
            <form onSubmit={handleCustomSubmit} className="mt-2 flex gap-2">
              <input
                type="text"
                value={customReply}
                onChange={(e) => setCustomReply(e.target.value)}
                placeholder="输入指导或补充说明..."
                className="flex-1 rounded-md border border-input bg-background px-2.5 py-1 text-xs focus:outline-hidden focus:ring-1 focus:ring-ring"
              />
              <button
                type="submit"
                disabled={isSubmitting || !customReply.trim()}
                className="inline-flex items-center gap-1 rounded-md bg-secondary px-2.5 py-1 text-xs font-medium text-secondary-foreground hover:bg-secondary/80 disabled:opacity-50 transition-colors"
              >
                <CornerDownLeft className="h-3 w-3" />
                <span>发送</span>
              </button>
            </form>
          )}
        </div>
      )}
    </div>
  );
};
