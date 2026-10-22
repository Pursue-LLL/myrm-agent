'use client';

/**
 * [INPUT]
 * - mobileCockpitTypes: MobileAgentActionBarProps
 * - lucide-react icons
 * - next-intl: useTranslations
 *
 * [OUTPUT]
 * - MobileAgentActionBar: Fixed bottom quick action bar for mobile companion
 *
 * [POS]
 * Mobile Remote Companion thumb-reachable bottom persistent action surface.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import { Mic, Square, Sparkles, MessagesSquare, Loader2 } from 'lucide-react';
import { MobileAgentActionBarProps } from './mobileCockpitTypes';

export const MobileAgentActionBar: React.FC<MobileAgentActionBarProps> = ({
  onOpenVoice,
  onOpenSkills,
  onStopAgent,
  onToggleSessions,
  isRunning = false,
  isStopping = false,
  className = '',
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('mobileCockpit.actionBar');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback for tests
  }

  return (
    <div
      data-testid="mobile-agent-action-bar"
      className={`fixed bottom-0 left-0 right-0 z-40 border-t border-border/80 bg-background/90 px-3 pt-2 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-md shadow-lg ${className}`}
    >
      <div className="mx-auto flex max-w-md items-center justify-around gap-1.5">
        <button
          type="button"
          data-testid="action-voice-btn"
          aria-label={t('quickVoice')}
          onClick={onOpenVoice}
          className="flex h-12 flex-1 flex-col items-center justify-center rounded-2xl bg-card border border-border/70 text-foreground hover:bg-muted active:scale-95 transition-all"
        >
          <Mic className="h-4 w-4 text-primary mb-0.5" />
          <span className="text-[10px] font-semibold text-muted-foreground">
            {t('quickVoice')}
          </span>
        </button>

        <button
          type="button"
          data-testid="action-skills-btn"
          aria-label={t('skills')}
          onClick={onOpenSkills}
          className="flex h-12 flex-1 flex-col items-center justify-center rounded-2xl bg-card border border-border/70 text-foreground hover:bg-muted active:scale-95 transition-all"
        >
          <Sparkles className="h-4 w-4 text-amber-500 mb-0.5" />
          <span className="text-[10px] font-semibold text-muted-foreground">
            {t('skills')}
          </span>
        </button>

        <button
          type="button"
          data-testid="action-stop-btn"
          aria-label={isStopping ? t('stopping') : t('stop')}
          onClick={onStopAgent}
          disabled={!isRunning || isStopping}
          className={`flex h-12 flex-1 flex-col items-center justify-center rounded-2xl border transition-all active:scale-95 ${
            isRunning
              ? 'border-destructive/40 bg-destructive/10 text-destructive hover:bg-destructive/20 shadow-sm'
              : 'border-border/40 bg-muted/30 text-muted-foreground/40 cursor-not-allowed'
          }`}
        >
          {isStopping ? (
            <Loader2 className="h-4 w-4 animate-spin mb-0.5" />
          ) : (
            <Square className="h-4 w-4 fill-current mb-0.5" />
          )}
          <span className="text-[10px] font-semibold">
            {isStopping ? t('stopping') : t('stop')}
          </span>
        </button>

        <button
          type="button"
          data-testid="action-sessions-btn"
          aria-label={t('sessions')}
          onClick={onToggleSessions}
          className="flex h-12 flex-1 flex-col items-center justify-center rounded-2xl bg-card border border-border/70 text-foreground hover:bg-muted active:scale-95 transition-all"
        >
          <MessagesSquare className="h-4 w-4 text-muted-foreground mb-0.5" />
          <span className="text-[10px] font-semibold text-muted-foreground">
            {t('sessions')}
          </span>
        </button>
      </div>
    </div>
  );
};
