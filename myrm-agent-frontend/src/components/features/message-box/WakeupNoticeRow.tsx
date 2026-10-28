/**
 * [INPUT]
 * - next-intl::useTranslations (POS: Locale copy of the chat namespace)
 * - @/store/chat/types::WakeupNoticeKind (POS: what the server did with a settled background task)
 *
 * [OUTPUT]
 * - WakeupNoticeRow: one quiet, centered line telling the user that a finished background task waits for them.
 *
 * [POS]
 * Transcript line for a settled background task that did not wake the agent (the follow-up limit was reached, or the
 * chat had been stopped). It names no task and no internals: it says that the work is done and what to do next.
 */
import { useTranslations } from 'next-intl';
import type { WakeupNoticeKind } from '@/store/chat/types';

interface WakeupNoticeRowProps {
  kind: Exclude<WakeupNoticeKind, 'followup'>;
}

export function WakeupNoticeRow({ kind }: WakeupNoticeRowProps) {
  const t = useTranslations('chat');

  return (
    <output
      data-testid="wakeup-notice"
      data-kind={kind}
      className="my-3 flex items-center gap-3 px-1 text-xs text-muted-foreground"
    >
      <span aria-hidden="true" className="h-px min-w-4 flex-1 bg-border" />
      <p className="max-w-xl text-balance text-center leading-relaxed">
        {kind === 'degraded' ? t('wakeupNotice.degraded') : t('wakeupNotice.suppressed')}
      </p>
      <span aria-hidden="true" className="h-px min-w-4 flex-1 bg-border" />
    </output>
  );
}
