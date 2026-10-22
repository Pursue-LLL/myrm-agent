'use client';

/**
 * [INPUT]
 * - groupChatTypes: DeliberationThreadBubbleProps, DeliberationMessage
 * - lucide-react icons
 * - next-intl: useTranslations
 *
 * [OUTPUT]
 * - DeliberationThreadBubble: Message bubble supporting multi-agent threading and PASS folding
 *
 * [POS]
 * Group Chat deliberation message component collapsing silent PASS turns to reduce room noise.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Bot,
  ChevronDown,
  ChevronUp,
  ShieldAlert,
  ArrowRightCircle,
  EyeOff,
} from 'lucide-react';
import {
  DeliberationThreadBubbleProps,
} from './groupChatTypes';

export const DeliberationThreadBubble: React.FC<DeliberationThreadBubbleProps> = ({
  message,
  onSelectOption,
  className = '',
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('groupChat.deliberation');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback for tests
  }

  const [passExpanded, setPassExpanded] = useState<boolean>(false);
  const isPass = message.status === 'pass';
  const badgeColor = message.colorBadge || '#3b82f6';

  // 1. Silent PASS collapsed capsule
  if (isPass) {
    return (
      <div
        data-testid={`deliberation-pass-${message.id}`}
        className={`my-1.5 flex flex-col items-start px-2 ${className}`}
      >
        <button
          type="button"
          onClick={() => {
            setPassExpanded(!passExpanded);
          }}
          className="inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-muted/40 px-3 py-1 text-xs text-muted-foreground transition-all hover:bg-muted hover:text-foreground"
        >
          <EyeOff className="h-3 w-3" style={{ color: badgeColor }} />
          <span className="font-semibold text-foreground/80">{message.agentName}</span>
          <span>({message.role}):</span>
          <span className="font-medium text-muted-foreground/90">
            {t('passBadge')}
          </span>
          {passExpanded ? (
            <ChevronUp className="h-3 w-3 ml-0.5" />
          ) : (
            <ChevronDown className="h-3 w-3 ml-0.5" />
          )}
        </button>

        {passExpanded ? (
          <div
            data-testid={`deliberation-pass-details-${message.id}`}
            className="mt-1.5 max-w-lg rounded-xl border border-border/50 bg-muted/20 p-2.5 text-xs text-muted-foreground animate-in fade-in duration-150"
          >
            <div className="font-mono text-[11px] mb-1 text-foreground/70">
              判定理由：
            </div>
            <div>{message.passReason || message.content}</div>
          </div>
        ) : null}
      </div>
    );
  }

  // 2. Active Speaking / Deliberation Message Bubble
  return (
    <div
      data-testid={`deliberation-bubble-${message.id}`}
      className={`my-2 flex items-start gap-3 px-2 ${className}`}
    >
      <div
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border text-white shadow-sm mt-0.5"
        style={{ backgroundColor: badgeColor }}
      >
        <Bot className="h-5 w-5" />
      </div>

      <div className="flex-1 min-w-0 max-w-2xl">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-bold text-foreground">
            {message.agentName}
          </span>
          <span
            className="rounded-full px-2 py-0.5 text-[10px] font-semibold border"
            style={{
              borderColor: `${badgeColor}40`,
              backgroundColor: `${badgeColor}15`,
              color: badgeColor,
            }}
          >
            {message.role}
          </span>
          <span className="text-[10px] text-muted-foreground ml-auto font-mono">
            {message.timestamp}
          </span>
        </div>

        <div className="rounded-2xl rounded-tl-sm border border-border/70 bg-card p-3.5 shadow-sm text-sm text-foreground space-y-2">
          <div className="whitespace-pre-wrap leading-relaxed">
            {message.content}
          </div>

          {message.status === 'needs-you' ? (
            <div className="flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-600 dark:text-amber-400">
              <ShieldAlert className="h-3.5 w-3.5 shrink-0" />
              <span>当前发言请求人类协同裁决 (Needs You)</span>
            </div>
          ) : null}

          {message.options && message.options.length > 0 ? (
            <div className="pt-1.5 border-t border-border/40 space-y-1.5">
              <span className="text-[11px] font-semibold text-muted-foreground block">
                备选协同方案：
              </span>
              <div className="flex flex-wrap gap-1.5">
                {message.options.map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => {
                      if (onSelectOption) {
                        onSelectOption(option);
                      }
                    }}
                    className="inline-flex items-center gap-1 rounded-xl border border-primary/30 bg-primary/5 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/10 active:scale-95 transition-all"
                  >
                    <ArrowRightCircle className="h-3 w-3" />
                    <span>{option}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};
