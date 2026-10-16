'use client';

/**
 * [INPUT]
 * @/store/useChatStore (POS: incognitoMode flag)
 * ../message-input-actions/IncognitoIcon (POS: shared incognito glyph)
 *
 * [OUTPUT]
 * IncognitoNotice: explanation shown on the empty chat while incognito mode is on.
 *
 * [POS]
 * The toggle explains itself only through a hover tooltip (never shown on touch) and sits in a bottom sheet
 * on phones, so once it is on nothing on the page says what it does. This states the terms in place.
 */

import { useTranslations } from 'next-intl';

import useChatStore from '@/store/useChatStore';
import IncognitoIcon from '../message-input-actions/IncognitoIcon';

export default function IncognitoNotice() {
  const t = useTranslations('memory');
  const incognitoMode = useChatStore((s) => s.incognitoMode);

  if (!incognitoMode) {
    return null;
  }

  return (
    <output
      data-testid="incognito-notice"
      className="flex w-full items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 dark:border-destructive/25 dark:bg-destructive/15"
    >
      <IncognitoIcon size={18} className="mt-0.5 text-destructive" />
      <span className="min-w-0">
        <span className="block text-sm font-medium text-foreground">{t('incognitoMode')}</span>
        <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">{t('incognitoModeDesc')}</span>
      </span>
    </output>
  );
}
