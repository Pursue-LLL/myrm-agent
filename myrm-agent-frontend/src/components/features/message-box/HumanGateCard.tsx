'use client';

/**
 * [INPUT]
 * @/services/chat::submitHumanGateResponse (POS: Dynamic Workflow human gate answer submission API)
 * @/store/chat/types::Message.humanGate (POS: human gate state)
 *
 * [OUTPUT]
 * HumanGateCard: Renders mid-run human decision gate with options, free-form text, and countdown timer.
 *
 * [POS]
 * Dynamic Workflow Mid-Run Human Gate UI. Bridges assistant decision prompts to user input.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { submitHumanGateResponse } from '@/services/chat';
import { cn } from '@/lib/utils';
import { isImeComposing } from '@/lib/utils/imeUtils';

interface HumanGateCardProps {
  messageId: string;
  question: string;
  options?: string[];
  timeoutSeconds?: number;
  defaultAction?: string;
  status: 'waiting' | 'resolved';
  answer?: string;
  timedOut?: boolean;
}

const ShieldAlertIcon = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

const CheckCircleIcon = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </svg>
);

const ClockIcon = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

export const HumanGateCard: React.FC<HumanGateCardProps> = ({
  messageId,
  question,
  options = [],
  timeoutSeconds = 300,
  defaultAction = '',
  status,
  answer,
  timedOut,
}) => {
  const t = useTranslations('chat');
  const [inputText, setInputText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [timeLeft, setTimeLeft] = useState<number>(timeoutSeconds);

  useEffect(() => {
    if (status !== 'waiting') {
      return;
    }
    setTimeLeft(timeoutSeconds);
    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [status, timeoutSeconds]);

  const handleResolve = useCallback(
    async (selectedAnswer: string) => {
      if (submitting || status !== 'waiting') {
        return;
      }
      setSubmitting(true);
      try {
        await submitHumanGateResponse(messageId, selectedAnswer);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to submit response');
      } finally {
        setSubmitting(false);
      }
    },
    [messageId, status, submitting],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (isImeComposing(e)) {
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (inputText.trim()) {
        handleResolve(inputText.trim());
      }
    }
  };

  if (status === 'resolved') {
    return (
      <div className="my-3 p-3 rounded-lg border border-border/40 bg-muted/20 text-xs text-muted-foreground flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 overflow-hidden">
          <CheckCircleIcon className="w-4 h-4 text-emerald-500 shrink-0" />
          <span className="truncate">
            {timedOut ? 'Decision timed out (default applied):' : 'Decision confirmed:'}{' '}
            <strong className="text-foreground">{answer || defaultAction || 'Completed'}</strong>
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="my-3.5 p-4 rounded-xl border border-amber-500/30 bg-amber-500/5 dark:bg-amber-950/20 shadow-sm backdrop-blur-sm">
      <div className="flex items-start justify-between gap-3 mb-2.5">
        <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 font-medium text-sm">
          <ShieldAlertIcon className="w-4 h-4 shrink-0" />
          <span>Human Decision Required</span>
        </div>
        {timeLeft > 0 && (
          <div className="flex items-center gap-1 text-xs text-amber-600/80 dark:text-amber-400/80 font-mono">
            <ClockIcon className="w-3.5 h-3.5" />
            <span>{timeLeft}s</span>
          </div>
        )}
      </div>

      <p className="text-sm text-foreground mb-3 leading-relaxed whitespace-pre-wrap">{question}</p>

      {options.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {options.map((option) => (
            <button
              key={option}
              type="button"
              disabled={submitting}
              onClick={() => handleResolve(option)}
              className={cn(
                'px-3 py-1.5 text-xs font-medium rounded-lg border transition-all duration-150',
                'bg-background hover:bg-accent hover:text-accent-foreground border-border/80 shadow-xs',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
            >
              {option}
            </button>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={submitting}
          placeholder={options.length > 0 ? 'Or enter custom response...' : 'Enter your decision / input...'}
          className="flex-1 px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground placeholder:text-muted-foreground/60 focus:outline-hidden focus:ring-1 focus:ring-amber-500"
        />
        <button
          type="button"
          disabled={submitting || !inputText.trim()}
          onClick={() => handleResolve(inputText.trim())}
          className="px-3.5 py-1.5 text-xs font-medium rounded-lg bg-amber-600 hover:bg-amber-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Submit
        </button>
      </div>
    </div>
  );
};
