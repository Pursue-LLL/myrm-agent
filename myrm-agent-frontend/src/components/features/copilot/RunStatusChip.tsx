'use client';

import { useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronDown, ChevronUp, MessageCircleQuestion } from 'lucide-react';
import { useRunDigest } from '@/hooks/copilot/useRunDigest';
import useChatStore from '@/store/useChatStore';
import { Button } from '@/components/primitives/button';
import { resolveRunDigestHeadline } from '@/lib/copilot/runHeadline';

interface RunStatusChipProps {
  chatId: string;
}

export default function RunStatusChip({ chatId }: RunStatusChipProps) {
  const t = useTranslations('copilot');
  const loading = useChatStore((s) => s.loading);
  const { digest } = useRunDigest(chatId);
  const [expanded, setExpanded] = useState(false);

  const active =
    loading ||
    digest?.phase === 'running' ||
    digest?.phase === 'waiting_approval';

  if (!active && (!digest || digest.phase === 'idle')) {
    return null;
  }

  const headline = useMemo(() => resolveRunDigestHeadline(digest, t), [digest, t]);

  const openAdvisor = (question = '') => {
    window.dispatchEvent(
      new CustomEvent('copilot-open-advisor', {
        detail: { question },
      }),
    );
  };

  return (
    <>
      <div
        data-testid="copilot-run-status-chip"
        className="flex flex-wrap items-center gap-2 border-b border-border/60 bg-muted/30 px-3 py-1.5 text-xs"
      >
        <button
          type="button"
          data-testid="copilot-run-headline-toggle"
          className="inline-flex min-w-0 flex-1 items-center gap-2 text-left text-foreground/90"
          onClick={() => setExpanded((v) => !v)}
        >
          <span
            className={`inline-block h-2 w-2 shrink-0 rounded-full ${
              digest?.phase === 'waiting_approval' ? 'bg-amber-500' : 'bg-primary animate-pulse'
            }`}
          />
          <span data-testid="copilot-run-headline" className="truncate font-medium">
            {headline}
          </span>
          {typeof digest?.elapsed_seconds === 'number' && digest.elapsed_seconds > 0 && (
            <span className="shrink-0 text-muted-foreground">{digest.elapsed_seconds}s</span>
          )}
          {expanded ? (
            <ChevronUp className="ml-auto h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronDown className="ml-auto h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          )}
        </button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          data-testid="copilot-run-ask-button"
          className="h-7 shrink-0 gap-1 px-2 text-xs"
          onClick={() => openAdvisor()}
        >
          <MessageCircleQuestion className="h-3.5 w-3.5" />
          {t('askButton')}
        </Button>
      </div>
      {expanded && digest?.recent_steps && digest.recent_steps.length > 0 && (
        <div
          data-testid="copilot-run-steps"
          className="border-b border-border/40 bg-muted/20 px-3 py-2 text-xs text-muted-foreground"
        >
          <ul className="space-y-1">
            {digest.recent_steps.map((step) => (
              <li key={`${step.step_key}-${step.index}`} className="truncate">
                {step.index}. {step.tool_name}
                {step.status ? ` · ${step.status}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
