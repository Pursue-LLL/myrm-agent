'use client';

/**
 * [INPUT]
 * - groupChatTypes: InteractiveNeedsYouBannerProps, NeedsYouIntervention
 * - lucide-react icons
 * - next-intl: useTranslations
 *
 * [OUTPUT]
 * - InteractiveNeedsYouBanner: Pulsing highlight banner prompting user intervention in multi-agent group chats
 *
 * [POS]
 * Group Chat needs-you banner stopping deadlock and letting humans steer multi-agent deliberation.
 */

import React, { useState, useCallback, ChangeEvent } from 'react';
import { useTranslations } from 'next-intl';
import {
  Sparkles,
  Send,
  X,
  Compass,
  AlertCircle,
} from 'lucide-react';
import {
  InteractiveNeedsYouBannerProps,
} from './groupChatTypes';

export const InteractiveNeedsYouBanner: React.FC<InteractiveNeedsYouBannerProps> = ({
  intervention,
  onIntervene,
  onDismiss,
  className = '',
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('groupChat.needsYou');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback for tests
  }

  const [customText, setCustomText] = useState<string>('');

  const handleChipClick = useCallback(
    (option: string) => {
      onIntervene(option);
      setCustomText('');
    },
    [onIntervene],
  );

  const handleSubmitCustom = useCallback(() => {
    const trimmed = customText.trim();
    if (!trimmed) {
      return;
    }
    onIntervene(trimmed);
    setCustomText('');
  }, [customText, onIntervene]);

  if (!intervention) {
    return null;
  }

  return (
    <section
      aria-label={t('needsYouTitle')}
      data-testid="interactive-needs-you-banner"
      className={`relative mx-2 my-2 overflow-hidden rounded-2xl border border-amber-500/40 bg-gradient-to-r from-amber-500/10 via-amber-500/5 to-purple-500/10 p-3.5 shadow-lg backdrop-blur-md animate-in slide-in-from-bottom-2 duration-200 ring-1 ring-amber-500/20 ${className}`}
    >
      <div className="flex items-start justify-between gap-3 pb-2 border-b border-amber-500/20">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/20 text-amber-600 dark:text-amber-400">
            <Compass className="h-4 w-4 animate-pulse" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
              <span>{t('needsYouTitle')}</span>
              <span className="inline-flex h-2 w-2 rounded-full bg-amber-500 animate-ping" />
            </h4>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {t('resolveNotice')}
            </p>
          </div>
        </div>

        {onDismiss ? (
          <button
            type="button"
            aria-label="关闭提示"
            onClick={onDismiss}
            className="flex h-6 w-6 items-center justify-center rounded-full text-muted-foreground hover:bg-muted/60 hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </div>

      <div className="my-2.5 space-y-1.5 text-xs">
        <div className="flex items-center gap-1.5 font-semibold text-foreground">
          <AlertCircle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
          <span>{intervention.issueTitle}</span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed pl-5">
          {intervention.contextSummary}
        </p>
      </div>

      {/* Suggested Options Chips */}
      {intervention.suggestedOptions && intervention.suggestedOptions.length > 0 ? (
        <div className="my-2.5 space-y-1.5">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
            {t('suggestedChips')}
          </span>
          <div className="flex flex-wrap gap-1.5">
            {intervention.suggestedOptions.map((option) => (
              <button
                key={option}
                type="button"
                data-testid={`needs-you-chip-${option}`}
                onClick={() => {
                  handleChipClick(option);
                }}
                className="inline-flex items-center gap-1 rounded-xl border border-amber-500/30 bg-card/80 px-2.5 py-1 text-xs font-semibold text-foreground shadow-sm hover:bg-amber-500/10 hover:border-amber-500/60 active:scale-95 transition-all"
              >
                <Sparkles className="h-3 w-3 text-amber-500" />
                <span>{option}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {/* Custom Steer Input Form */}
      <div className="mt-2.5 flex items-center gap-2 pt-2 border-t border-amber-500/20">
        <input
          type="text"
          value={customText}
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            setCustomText(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              handleSubmitCustom();
            }
          }}
          placeholder={t('customResponse')}
          className="flex-1 rounded-xl border border-border/80 bg-background/90 px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500/30"
        />
        <button
          type="button"
          data-testid="needs-you-submit-btn"
          disabled={!customText.trim()}
          onClick={handleSubmitCustom}
          className="flex h-8 items-center gap-1 rounded-xl bg-amber-600 px-3 text-xs font-bold text-white shadow hover:bg-amber-700 active:scale-95 transition-all disabled:opacity-40"
        >
          <Send className="h-3.5 w-3.5" />
          <span>{t('submitDecision')}</span>
        </button>
      </div>
    </section>
  );
};
