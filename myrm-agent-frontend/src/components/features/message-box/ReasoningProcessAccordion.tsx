'use client';

/**
 * [INPUT]
 * - types::Message (POS: Chat message model with reasoning content & timestamps.)
 * - services/config/types::ReasoningDisplayMode (POS: Reasoning display mode setting.)
 * - components/features/message-box/MarkdownContent (POS: Markdown renderer for reasoning body.)
 * - lucide-react::BrainCircuit, ChevronDown, ChevronRight, Copy, Check (POS: Visual indicators.)
 * - next-intl::useTranslations (POS: Internationalization.)
 *
 * [OUTPUT]
 * - ReasoningProcessAccordion: dedicated collapsible inspector component for streaming & completed reasoning processes.
 *
 * [POS]
 * Dedicated reasoning chain inspector card supporting live breathing animation, second-by-second timer,
 * one-click copy, and token footprint estimator for o1/o3/DeepSeek-R1/Claude 3.7 thinking streams.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { BrainCircuit, ChevronDown, ChevronRight, Copy, Check, Square, Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { Message } from '@/store/useChatStore';
import type { Source } from '@/store/chat/types';
import type { ReasoningDisplayMode } from '@/services/config/types';
import MarkdownContent from './MarkdownContent';

/** 稳定的空引用：内联 `[]` 会让 MarkdownContent 的 React.memo 每秒失效一次。 */
const EMPTY_SOURCES: Source[] = [];

export interface ReasoningProcessAccordionProps {
  message: Message;
  isLast: boolean;
  loading: boolean;
  isExpanded: boolean;
  onToggle: () => void;
  displayMode: ReasoningDisplayMode;
  className?: string;
  onStopThinking?: (chatId: string) => Promise<void> | void;
}

export default function ReasoningProcessAccordion({
  message,
  isLast,
  loading,
  isExpanded,
  onToggle,
  displayMode,
  className = '',
  onStopThinking,
}: ReasoningProcessAccordionProps) {
  const t = useTranslations('chat');
  const tContext = useTranslations('chat.contextUsage');
  const [elapsedSec, setElapsedSec] = useState(0);
  const [copied, setCopied] = useState(false);
  const [isStopping, setIsStopping] = useState(false);

  const isThinking = isLast && loading && !message.content;
  const forceExpanded = displayMode === 'inline';
  const showExpanded = forceExpanded || isExpanded;

  useEffect(() => {
    if (!isThinking || !message.reasoningStartedAt) {
      setElapsedSec(0);
      return;
    }
    const startedAt = message.reasoningStartedAt;
    setElapsedSec(Math.floor((Date.now() - startedAt) / 1000));
    const timer = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [isThinking, message.reasoningStartedAt]);

  const handleCopy = useCallback(
    async (event: React.MouseEvent) => {
      event.stopPropagation();
      if (!message.reasoning) {
        return;
      }
      try {
        await navigator.clipboard.writeText(message.reasoning);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch {
        // Fallback or ignore clipboard failure
      }
    },
    [message.reasoning],
  );

  const handleStopThinking = useCallback(
    async (event: React.MouseEvent) => {
      event.stopPropagation();
      if (isStopping || !message.chatId) {
        return;
      }
      setIsStopping(true);
      // 后端无响应时不允许按钮永久停在「收敛中…」：10s 上限后 abort，finally 会恢复可点状态。
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10_000);
      try {
        if (onStopThinking) {
          await onStopThinking(message.chatId);
        } else {
          await fetch(`/api/v1/chats/${message.chatId}/stop-thinking`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              reason: 'user_interrupted',
              force_immediate_answer: true,
            }),
            signal: controller.signal,
          });
        }
      } catch (err) {
        // Fallback or log failure
        console.error('Failed to trigger stop-thinking:', err);
      } finally {
        clearTimeout(timeout);
        setIsStopping(false);
      }
    },
    [isStopping, message.chatId, onStopThinking],
  );

  const durationSec = message.reasoningDurationMs ? Math.round(message.reasoningDurationMs / 1000) : null;

  const stepCount = message.thinkingItems?.length ?? 0;
  const stepLabel = stepCount > 0 ? t('reasoningSteps', { count: stepCount }) : '';

  const label = isThinking
    ? `${t('reasoningThinking', { seconds: elapsedSec })}${stepLabel}`
    : durationSec
      ? `${t('reasoningCompleted', { seconds: durationSec })}${stepLabel}`
      : t('reasoningTitle');

  // 优先使用后端返回的真实 reasoning token；缺失时才回落到字符估算（并显式标注 ≈）。
  const exactReasoningTokens =
    typeof message.usage?.reasoning_tokens === 'number' && message.usage.reasoning_tokens > 0
      ? message.usage.reasoning_tokens
      : null;
  const estimatedReasoningTokens = message.reasoning ? Math.round(message.reasoning.length / 4) : 0;
  const reasoningTokens = exactReasoningTokens ?? estimatedReasoningTokens;

  const renderStopThinkingButton = () => {
    if (!isThinking) {
      return null;
    }
    return (
      <button
        type="button"
        data-testid="stop-thinking-button"
        onClick={handleStopThinking}
        disabled={isStopping}
        title={t('stopThinkingHint')}
        className="inline-flex min-h-10 items-center gap-1 rounded border border-amber-500/30 bg-amber-500/10 px-3 text-xs font-medium text-amber-600 transition-colors hover:bg-amber-500/20 disabled:opacity-50 dark:text-amber-400"
      >
        {isStopping ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Square className="h-3 w-3 fill-current" />}
        <span>{isStopping ? t('stoppingThinking') : t('stopThinking')}</span>
      </button>
    );
  };

  return (
    <div
      data-testid="reasoning-process-accordion"
      className={`mb-4 border border-border/50 rounded-lg overflow-hidden bg-muted/20 transition-all ${className}`}
    >
      {displayMode === 'inline' ? (
        <div className="flex w-full items-center justify-between gap-2 px-4 py-2 text-sm bg-muted/30">
          <div className="flex min-w-0 items-center gap-2 text-muted-foreground">
            <BrainCircuit className={`h-4 w-4 shrink-0 ${isThinking ? 'animate-pulse text-primary' : ''}`} />
            <span className="truncate font-medium" title={label}>
              {label}
            </span>
            {reasoningTokens > 0 && (
              <span className="font-mono text-[10px] text-muted-foreground/70">
                {exactReasoningTokens === null
                  ? t('reasoningTokensEstimated', { count: reasoningTokens })
                  : t('reasoningTokens', { count: reasoningTokens })}
              </span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {renderStopThinkingButton()}
            {message.reasoning && (
              <button
                type="button"
                onClick={handleCopy}
                aria-label={copied ? tContext('copiedReasoning') : tContext('copyReasoning')}
                title={copied ? tContext('copiedReasoning') : tContext('copyReasoning')}
                className="inline-flex h-10 w-10 items-center justify-center rounded text-muted-foreground transition-colors hover:text-foreground"
              >
                {copied ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="w-full flex items-center justify-between px-4 py-2 hover:bg-muted/50 transition-colors text-sm">
          <button
            type="button"
            onClick={onToggle}
            title={label}
            aria-expanded={showExpanded}
            aria-controls={`reasoning-body-${message.messageId}`}
            className="flex min-w-0 flex-1 self-stretch items-center gap-2 text-left text-muted-foreground"
          >
            <BrainCircuit className={`h-4 w-4 shrink-0 ${isThinking ? 'animate-pulse text-primary' : ''}`} />
            <span className="truncate font-medium" title={label}>
              {label}
            </span>
            {reasoningTokens > 0 && (
              <span className="font-mono text-[10px] text-muted-foreground/70">
                {exactReasoningTokens === null
                  ? t('reasoningTokensEstimated', { count: reasoningTokens })
                  : t('reasoningTokens', { count: reasoningTokens })}
              </span>
            )}
          </button>
          <div className="flex shrink-0 items-center gap-1.5 text-muted-foreground">
            {renderStopThinkingButton()}
            {message.reasoning && (
              <button
                type="button"
                onClick={handleCopy}
                aria-label={copied ? tContext('copiedReasoning') : tContext('copyReasoning')}
                title={copied ? tContext('copiedReasoning') : tContext('copyReasoning')}
                className="inline-flex h-10 w-10 items-center justify-center rounded transition-colors hover:text-foreground"
              >
                {copied ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
              </button>
            )}
            <button
              type="button"
              onClick={onToggle}
              aria-label={isExpanded ? t('collapseReasoning') : t('expandReasoning')}
              aria-expanded={showExpanded}
              aria-controls={`reasoning-body-${message.messageId}`}
              className="inline-flex h-10 w-10 items-center justify-center rounded transition-colors hover:text-foreground"
            >
              {isExpanded ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
            </button>
          </div>
        </div>
      )}

      {showExpanded && (
        <div
          id={`reasoning-body-${message.messageId}`}
          className="px-4 py-3 border-t border-border/50 text-sm text-muted-foreground bg-muted/10"
        >
          <MarkdownContent
            content={message.reasoning ?? ''}
            sources={EMPTY_SOURCES}
            messageId={`${message.messageId}-reasoning`}
            isStreaming={isThinking}
          />
          {isThinking && (
            <span className="ml-1.5 inline-flex items-center gap-0.5 align-middle" aria-label={t('reasoningLoading')}>
              <span className="w-1 h-1 rounded-full bg-muted-foreground/50 animate-[pulse_1s_ease-in-out_infinite]" />
              <span className="w-1 h-1 rounded-full bg-muted-foreground/50 animate-[pulse_1s_ease-in-out_0.2s_infinite]" />
              <span className="w-1 h-1 rounded-full bg-muted-foreground/50 animate-[pulse_1s_ease-in-out_0.4s_infinite]" />
            </span>
          )}
        </div>
      )}
    </div>
  );
}
