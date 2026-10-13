/**
 * [INPUT]
 * - next-intl::useTranslations (POS: Locale copy of the chat namespace)
 * - lucide-react::RotateCw (POS: Retry glyph)
 *
 * [OUTPUT]
 * - SendFailedNotice: connection hint with a retry action, shown under a user bubble whose request got no reply.
 *
 * [POS]
 * Failed-send line of a user bubble. The line wraps and the retry button keeps its size, so a hint that fills the
 * line cannot break the button label apart on a narrow screen.
 */
import { RotateCw } from 'lucide-react';
import { useTranslations } from 'next-intl';

interface SendFailedNoticeProps {
  onRetry: () => void;
}

export function SendFailedNotice({ onRetry }: SendFailedNoticeProps) {
  const t = useTranslations('chat');

  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1.5">
      <span className="text-sm text-destructive/80">{t('messageFailed.networkError')}</span>
      <button
        onClick={onRetry}
        className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap px-3 py-1 text-sm font-medium rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
      >
        <RotateCw size={14} />
        {t('retry')}
      </button>
    </div>
  );
}
