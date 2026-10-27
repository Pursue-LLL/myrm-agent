/**
 * [INPUT]
 * - @/lib/utils/classnameUtils::cn (POS: className merge helper)
 * - next-intl::useLocale, useTranslations (POS: i18n)
 *
 * [OUTPUT]
 * - PastedTextCard: the collapsed form of a very long pasted text inside a user bubble.
 *
 * [POS]
 * Shows the character count and the opening lines instead of the whole text. A history message keeps its full text
 * in a file, so the card offers to open it; a message still in memory unfolds in place.
 */
import { useState } from 'react';
import { CaretDown, ClipboardText } from '@phosphor-icons/react';
import { useLocale, useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';

interface PastedTextCardProps {
  chars: number;
  preview: string;
  /** The full text is stored apart from the chat: open it in the side panel. */
  onOpen?: () => void;
  /** The full text is still at hand: unfold it in place. */
  fullText?: string;
  failed?: boolean;
}

const ACTION_CLASS =
  'shrink-0 inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-primary ' +
  'transition-colors hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40';

export function PastedTextCard({ chars, preview, onOpen, fullText, failed = false }: PastedTextCardProps) {
  const t = useTranslations('chat');
  const locale = useLocale();
  const [expanded, setExpanded] = useState(false);

  return (
    <section
      data-testid="pasted-text-card"
      className={cn(
        'min-w-0 grow basis-full lg:basis-0 lg:w-9/12 overflow-hidden rounded-2xl border bg-secondary/50',
        failed ? 'border-destructive/40' : 'border-border',
      )}
    >
      <div className="flex items-center gap-3 px-4 py-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <ClipboardText size={20} weight="duotone" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground">{t('pastedText.title')}</p>
          <p className="text-xs text-muted-foreground">
            {t('pastedText.meta', { chars: new Intl.NumberFormat(locale).format(chars) })}
          </p>
        </div>
        {onOpen ? (
          <button type="button" onClick={onOpen} className={ACTION_CLASS}>
            {t('pastedText.viewFull')}
          </button>
        ) : null}
        {fullText ? (
          <button
            type="button"
            onClick={() => setExpanded((open) => !open)}
            aria-expanded={expanded}
            className={ACTION_CLASS}
          >
            {expanded ? t('pastedText.collapse') : t('pastedText.expand')}
            <CaretDown
              size={12}
              weight="bold"
              aria-hidden
              className={cn('transition-transform', expanded && 'rotate-180')}
            />
          </button>
        ) : null}
      </div>
      {expanded && fullText ? (
        <div className="max-h-80 overflow-y-auto border-t border-border px-4 py-3 text-sm text-foreground whitespace-pre-wrap break-words">
          {fullText}
        </div>
      ) : preview ? (
        <div className="border-t border-border px-4 py-3">
          <p className="line-clamp-3 text-sm text-muted-foreground whitespace-pre-wrap break-words">{preview}</p>
        </div>
      ) : null}
    </section>
  );
}
