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
import { BrainCircuit, ChevronDown, ChevronRight, Copy, Check } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { Message } from '@/store/useChatStore';
import type { ReasoningDisplayMode } from '@/services/config/types';
import MarkdownContent from './MarkdownContent';

export interface ReasoningProcessAccordionProps {
  message: Message;
  isLast: boolean;
  loading: boolean;
  isExpanded: boolean;
  onToggle: () => void;
  displayMode: ReasoningDisplayMode;
  className?: string;
}

export default function ReasoningProcessAccordion({
  message,
  isLast,
  loading,
  isExpanded,
  onToggle,
  displayMode,
  className = '',
}: ReasoningProcessAccordionProps) {
  const t = useTranslations('chat');
  const tContext = useTranslations('chat.contextUsage');
  const [elapsedSec, setElapsedSec] = useState(0);
  const [copied, setCopied] = useState(false);

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

  const durationSec = message.reasoningDurationMs ? Math.round(message.reasoningDurationMs / 1000) : null;

  const label = isThinking
    ? t('reasoningThinking', { seconds: elapsedSec })
    : durationSec
      ? t('reasoningCompleted', { seconds: durationSec })
      : t('reasoningTitle');

  // Rough estimation: ~4 chars per token for reasoning footprint
  const reasoningTokens = message.reasoning ? Math.round(message.reasoning.length / 4) : 0;

  return (
    <div
      data-testid="reasoning-process-accordion"
      className={`mb-4 border border-border/50 rounded-lg overflow-hidden bg-muted/20 transition-all ${className}`}
    >
      {displayMode === 'inline' ? (
        <div className="w-full flex items-center justify-between px-4 py-2 text-sm bg-muted/30">
          <div className="flex items-center gap-2 text-muted-foreground">
            <BrainCircuit className={`w-4 h-4 ${isThinking ? 'text-primary animate-pulse' : ''}`} />
            <span className="font-medium">{label}</span>
            {reasoningTokens > 0 && (
              <span className="text-[10px] text-muted-foreground/70 font-mono">
                (~{reasoningTokens} tokens)
              </span>
            )}
          </div>
          {message.reasoning && (
            <button
              type="button"
              onClick={handleCopy}
              title={copied ? tContext('copiedReasoning') : tContext('copyReasoning')}
              className="p-1 text-muted-foreground hover:text-foreground rounded transition-colors"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>
      ) : (
        <div className="w-full flex items-center justify-between px-4 py-2 hover:bg-muted/50 transition-colors text-sm">
          <button
            type="button"
            onClick={onToggle}
            className="flex-1 flex items-center gap-2 text-muted-foreground text-left"
          >
            <BrainCircuit className={`w-4 h-4 ${isThinking ? 'text-primary animate-pulse' : ''}`} />
            <span className="font-medium">{label}</span>
            {reasoningTokens > 0 && (
              <span className="text-[10px] text-muted-foreground/70 font-mono">
                (~{reasoningTokens} tokens)
              </span>
            )}
          </button>
          <div className="flex items-center gap-1.5 text-muted-foreground">
            {message.reasoning && (
              <button
                type="button"
                onClick={handleCopy}
                title={copied ? tContext('copiedReasoning') : tContext('copyReasoning')}
                className="p-1 hover:text-foreground rounded transition-colors"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            )}
            <button
              type="button"
              onClick={onToggle}
              aria-label={isExpanded ? 'Collapse' : 'Expand'}
              className="p-1 hover:text-foreground rounded transition-colors"
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              )}
            </button>
          </div>
        </div>
      )}

      {showExpanded && (
        <div className="px-4 py-3 border-t border-border/50 text-sm text-muted-foreground bg-muted/10">
          <MarkdownContent
            content={message.reasoning ?? ''}
            sources={[]}
            messageId={`${message.messageId}-reasoning`}
            isStreaming={isThinking}
          />
          {isThinking && (
            <span className="inline-flex items-center ml-1.5 gap-0.5 align-middle" aria-label="Loading">
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
