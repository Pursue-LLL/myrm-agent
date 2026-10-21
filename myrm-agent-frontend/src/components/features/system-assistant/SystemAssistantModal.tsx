'use client';

/**
 * [INPUT]
 * - SystemAssistantCommandResponse, SystemAssistantStatusResponse from @/services/systemAssistant
 * - executeSystemAssistantCommand, getSystemAssistantStatus from @/services/systemAssistant
 * - Translation strings from 'systemAssistant' namespace
 *
 * [OUTPUT]
 * - SystemAssistantModal: Dialog interface for natural language system control and multi-agent dispatch
 *
 * [POS]
 * Natural language modal interface for XiaoMo Unified Natural Language Control Center.
 * Strict typing: Zero `any`. File length < 350 lines. Accessible <dialog> structure.
 */

import { useState, useEffect, useCallback, useId } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconBrain,
  IconCheck,
  IconRefresh,
  IconSparkles,
  IconTerminal,
  IconX,
} from '@/components/features/icons/PremiumIcons';
import type {
  SystemAssistantCommandResponse,
  SystemAssistantStatusResponse,
} from '@/services/systemAssistant';
import {
  executeSystemAssistantCommand,
  getSystemAssistantStatus,
} from '@/services/systemAssistant';

export interface SystemAssistantModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const PRESET_PROMPTS = [
  'createProjectPrompt',
  'queryTasksPrompt',
  'terminateTasksPrompt',
  'systemHealthPrompt',
] as const;

export function SystemAssistantModal({ isOpen, onClose }: SystemAssistantModalProps) {
  const t = useTranslations('systemAssistant');
  const titleId = useId();
  const descId = useId();

  const [prompt, setPrompt] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isListening, setIsListening] = useState<boolean>(false);
  const [history, setHistory] = useState<SystemAssistantCommandResponse[]>([]);
  const [statusOverview, setStatusOverview] = useState<SystemAssistantStatusResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Load telemetry status upon opening
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    let cancelled = false;

    getSystemAssistantStatus()
      .then((res) => {
        if (!cancelled) {
          setStatusOverview(res);
        }
      })
      .catch(() => {
        // Non-critical fallback
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const handleSendCommand = useCallback(
    async (textToSend?: string) => {
      const targetPrompt = (textToSend ?? prompt).trim();
      if (!targetPrompt) {
        return;
      }

      setIsSubmitting(true);
      setErrorMessage(null);

      try {
        const response = await executeSystemAssistantCommand({
          user_prompt: targetPrompt,
        });
        setHistory((prev) => [response, ...prev]);
        setPrompt('');
      } catch (err) {
        setErrorMessage(
          err instanceof Error ? err.message : 'Failed to execute system command',
        );
      } finally {
        setIsSubmitting(false);
      }
    },
    [prompt],
  );

  const toggleVoiceListening = useCallback(() => {
    if (isListening) {
      setIsListening(false);
      return;
    }

    if (
      typeof window !== 'undefined' &&
      ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)
    ) {
      setIsListening(true);
      // Native Web Speech recognition support can be attached here
    } else {
      // Fallback voice simulation / hint
      setIsListening(true);
      setTimeout(() => {
        setIsListening(false);
        setPrompt(t('voiceMockInput'));
      }, 1500);
    }
  }, [isListening, t]);

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <dialog
        open
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="w-full max-w-xl rounded-2xl bg-card border border-border shadow-2xl p-6 text-foreground flex flex-col gap-4 m-0 max-h-[85vh] overflow-y-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/60 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center font-bold">
              <IconBrain className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id={titleId} className="text-base font-semibold">
                  {t('hubTitle')}
                </h2>
                {statusOverview && (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                    {statusOverview.running_tasks_count} {t('tasksRunningBadge')}
                  </span>
                )}
              </div>
              <p id={descId} className="text-xs text-muted-foreground">
                {t('hubSubtitle')}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label={t('closeAriaLabel')}
          >
            <IconX className="w-5 h-5" />
          </button>
        </div>

        {/* Input Bar with Voice Toggle */}
        <div className="flex items-center gap-2 rounded-xl bg-background border border-border p-2 focus-within:ring-2 focus-within:ring-primary/40 transition-all">
          <IconTerminal className="w-4 h-4 text-muted-foreground ml-1.5 shrink-0" />
          <input
            type="text"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendCommand();
              }
            }}
            placeholder={isListening ? t('listeningPlaceholder') : t('inputPlaceholder')}
            className="w-full bg-transparent text-xs text-foreground placeholder:text-muted-foreground focus:outline-none"
          />
          <button
            type="button"
            onClick={toggleVoiceListening}
            className={`p-1.5 rounded-lg text-xs font-medium transition-colors ${
              isListening
                ? 'bg-rose-500 text-white animate-pulse'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
            title={t('voiceButtonTitle')}
            aria-label={t('voiceButtonTitle')}
          >
            <IconSparkles className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => handleSendCommand()}
            disabled={isSubmitting || !prompt.trim()}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 shrink-0"
          >
            {isSubmitting ? t('executingAction') : t('sendAction')}
          </button>
        </div>

        {/* Quick Suggestion Pills */}
        <div className="flex flex-wrap gap-1.5">
          {PRESET_PROMPTS.map((presetKey) => (
            <button
              key={presetKey}
              type="button"
              onClick={() => handleSendCommand(t(presetKey))}
              className="px-2.5 py-1 rounded-full text-[11px] bg-muted/50 text-muted-foreground border border-border/60 hover:bg-muted hover:text-foreground transition-colors"
            >
              {t(presetKey)}
            </button>
          ))}
        </div>

        {/* Error notification */}
        {errorMessage && (
          <div className="rounded-lg bg-destructive/10 text-destructive text-xs p-2.5 border border-destructive/20">
            {errorMessage}
          </div>
        )}

        {/* Action Results Stream / History */}
        <div className="flex flex-col gap-3 min-h-[140px] max-h-[360px] overflow-y-auto pr-1">
          {history.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center text-muted-foreground">
              <IconBrain className="w-8 h-8 opacity-40 mb-2" />
              <p className="text-xs font-medium">{t('emptyHistoryNotice')}</p>
              <p className="text-[11px] opacity-80 mt-0.5">{t('emptyHistoryHint')}</p>
            </div>
          ) : (
            history.map((item) => (
              <div
                key={item.command_id}
                className="rounded-xl bg-muted/40 border border-border/70 p-3.5 flex flex-col gap-2 text-xs"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-primary capitalize flex items-center gap-1.5">
                    <IconCheck className="w-3.5 h-3.5 text-emerald-500" />
                    {item.intent.replace('_', ' ')}
                  </span>
                  <span className="text-[10px] font-mono text-muted-foreground">
                    {item.command_id}
                  </span>
                </div>
                <p className="text-foreground leading-relaxed">{item.summary}</p>

                {/* Structured Details Card */}
                {Object.keys(item.action.details).length > 0 && (
                  <div className="rounded-lg bg-background/80 p-2 border border-border/40 grid grid-cols-2 gap-2 text-[11px] font-mono">
                    {Object.entries(item.action.details).map(([key, val]) => (
                      <div key={key} className="flex flex-col">
                        <span className="text-muted-foreground text-[10px]">{key}</span>
                        <span className="font-medium text-foreground truncate">{val}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Suggested follow-up buttons */}
                {item.suggested_followups.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-1 border-t border-border/30">
                    {item.suggested_followups.map((followup) => (
                      <button
                        key={followup}
                        type="button"
                        onClick={() => handleSendCommand(followup)}
                        className="px-2 py-0.5 rounded text-[10px] bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                      >
                        {followup} &rarr;
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </dialog>
    </div>
  );
}
