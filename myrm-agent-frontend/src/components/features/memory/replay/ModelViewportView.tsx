'use client';

/**
 * [INPUT]
 * - prompt_preview: string (Raw prompt preview from TraceLLMCall)
 * - optional className: string
 *
 * [OUTPUT]
 * - ModelViewportView: Structured, role-segregated model viewport inspection component
 *
 * [POS]
 * Session replay & trace inspector pane sub-component.
 * Visualizes the immutable event-sourced viewport of a model invocation,
 * displaying system prompt, turn history depth, tool specs, and copy actions.
 */

import { memo, useMemo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { IconCopy, IconCheck } from '@/components/features/icons/PremiumIcons';
import { parseModelViewport, type ViewportRole } from './viewportParser';

interface ModelViewportViewProps {
  promptPreview: string | null | undefined;
  className?: string;
  compact?: boolean;
}

const ROLE_STYLES: Record<ViewportRole, { badge: string; border: string; bg: string }> = {
  system: {
    badge: 'bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 border-indigo-500/30',
    border: 'border-indigo-500/20',
    bg: 'bg-indigo-500/5',
  },
  user: {
    badge: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30',
    border: 'border-emerald-500/20',
    bg: 'bg-emerald-500/5',
  },
  assistant: {
    badge: 'bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/30',
    border: 'border-blue-500/20',
    bg: 'bg-blue-500/5',
  },
  tool: {
    badge: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30',
    border: 'border-amber-500/20',
    bg: 'bg-amber-500/5',
  },
  other: {
    badge: 'bg-muted text-muted-foreground border-border/40',
    border: 'border-border/30',
    bg: 'bg-muted/10',
  },
};

export const ModelViewportView = memo<ModelViewportViewProps>(({ promptPreview, className, compact = false }) => {
  const t = useTranslations('settings.sessionAnalytics.replay');
  const [copied, setCopied] = useState(false);

  const summary = useMemo(() => parseModelViewport(promptPreview), [promptPreview]);

  const handleCopy = useCallback(async () => {
    if (!promptPreview) {
      return;
    }
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(promptPreview);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
        return;
      }
    } catch {
      // fallback below
    }

    try {
      const textarea = document.createElement('textarea');
      textarea.value = promptPreview;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      const success = document.execCommand('copy');
      document.body.removeChild(textarea);
      if (success) {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch {
      // ignore
    }
  }, [promptPreview]);

  if (!promptPreview || summary.messages.length === 0) {
    return null;
  }

  return (
    <div className={cn('flex flex-col gap-2 rounded-xl border border-border/40 bg-card/40 p-3', className)}>
      {/* Viewport Header with Metadata & Copy Button */}
      <div className="flex items-center justify-between gap-2 border-b border-border/30 pb-2">
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="font-semibold text-foreground tracking-tight">{t('modelViewportTitle')}</span>
          <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-muted/60 text-muted-foreground border border-border/40">
            {t('viewportMessageCount', { count: summary.totalMessages })}
          </span>
          {summary.hasSystemPrompt && (
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
              {t('viewportSystemPrompt')}
            </span>
          )}
          {summary.userMessageCount > 0 && (
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
              {t('viewportUserTurns', { count: summary.userMessageCount })}
            </span>
          )}
          {summary.toolCallCount > 0 && (
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
              {t('viewportToolCalls', { count: summary.toolCallCount })}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border border-border/40 hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors shrink-0"
          title={t('copyRawViewport')}
        >
          {copied ? (
            <>
              <IconCheck className="h-3 w-3 text-emerald-500" />
              <span className="text-emerald-600 dark:text-emerald-400">{t('copied')}</span>
            </>
          ) : (
            <>
              <IconCopy className="h-3 w-3" />
              <span>{t('copy')}</span>
            </>
          )}
        </button>
      </div>

      {/* Truncation Notice Warning Banner if present */}
      {summary.isGloballyTruncated && (
        <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-[10px] text-amber-700 dark:text-amber-300">
          <span>{t('viewportTruncatedNotice', { chars: summary.truncatedCharsCount })}</span>
        </div>
      )}

      {/* Structured Role Message List */}
      <div className={cn('flex flex-col gap-1.5 overflow-y-auto', compact ? 'max-h-48' : 'max-h-72')}>
        {summary.messages.map((msg) => {
          const style = ROLE_STYLES[msg.role] || ROLE_STYLES.other;
          return (
            <div
              key={msg.id}
              className={cn(
                'rounded-lg border p-2 flex flex-col gap-1 text-left transition-colors',
                style.border,
                style.bg,
              )}
            >
              <div className="flex items-center justify-between text-[10px]">
                <span className={cn('px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider border', style.badge)}>
                  {msg.role}
                </span>
                <span className="text-muted-foreground font-mono text-[9px]">
                  {msg.content.length} chars
                </span>
              </div>
              <div className="text-[11px] font-mono text-foreground/90 whitespace-pre-wrap break-all select-text leading-relaxed">
                {msg.content}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
});

ModelViewportView.displayName = 'ModelViewportView';
export default ModelViewportView;
