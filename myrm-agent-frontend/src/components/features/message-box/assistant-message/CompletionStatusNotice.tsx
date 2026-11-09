'use client';

/**
 * [INPUT]
 * @/store/chat/types::CompletionStatus (POS: How the reply of the model ended)
 * next-intl::useTranslations (POS: Localized banner text)
 * lucide-react::{AlertTriangle,Ban,ShieldAlert} (POS: Banner icons)
 *
 * [OUTPUT]
 * CompletionStatusNotice: The banner under a finished answer that says why it stopped short.
 *
 * [POS]
 * The four abnormal endings of a reply (cut off, cancelled, filtered, budget blocked), each with its own banner.
 * A reply that ended normally, or one that is still streaming, shows nothing.
 */

import { AlertTriangle, Ban, ShieldAlert, type LucideIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { CompletionStatus } from '@/store/chat/types';

type NoticeSpec = {
  Icon: LucideIcon;
  container: string;
  iconClass: string;
  /** Left unset for the neutral banner, which takes its text tone from the container. */
  textClass?: string;
  labelKey: 'message.truncated' | 'message.cancelled' | 'message.contentFiltered' | 'message.budgetBlocked';
};

const NOTICES: ReadonlyMap<CompletionStatus, NoticeSpec> = new Map<CompletionStatus, NoticeSpec>([
  [
    'truncated',
    {
      Icon: AlertTriangle,
      container:
        'flex items-center gap-2 mt-2 px-3 py-2 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg text-sm',
      iconClass: 'w-4 h-4 text-amber-500 shrink-0',
      textClass: 'text-amber-700 dark:text-amber-300',
      labelKey: 'message.truncated',
    },
  ],
  [
    'cancelled',
    {
      Icon: Ban,
      container:
        'flex items-center gap-2 mt-2 px-3 py-2 bg-muted/40 border border-border/50 rounded-lg text-sm text-muted-foreground',
      iconClass: 'w-4 h-4 text-muted-foreground/70 shrink-0',
      labelKey: 'message.cancelled',
    },
  ],
  [
    'filtered',
    {
      Icon: ShieldAlert,
      container:
        'flex items-center gap-2 mt-2 px-3 py-2 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg text-sm',
      iconClass: 'w-4 h-4 text-red-500 shrink-0',
      textClass: 'text-red-700 dark:text-red-300',
      labelKey: 'message.contentFiltered',
    },
  ],
  [
    'budget_blocked',
    {
      Icon: Ban,
      container:
        'flex items-center gap-2 mt-2 px-3 py-2 bg-orange-50 dark:bg-orange-950/30 border border-orange-200 dark:border-orange-800 rounded-lg text-sm',
      iconClass: 'w-4 h-4 text-orange-500 shrink-0',
      textClass: 'text-orange-700 dark:text-orange-300',
      labelKey: 'message.budgetBlocked',
    },
  ],
]);

export function CompletionStatusNotice({
  status,
  streaming,
}: {
  status: CompletionStatus | undefined;
  /** The answer is still being written, so how it will end is not known yet. */
  streaming: boolean;
}) {
  const t = useTranslations('chat');
  const notice = status && !streaming ? NOTICES.get(status) : undefined;
  if (!notice) {
    return null;
  }

  const { Icon, container, iconClass, textClass, labelKey } = notice;
  return (
    <div className={container}>
      <Icon className={iconClass} />
      <span className={textClass}>{t(labelKey)}</span>
    </div>
  );
}
