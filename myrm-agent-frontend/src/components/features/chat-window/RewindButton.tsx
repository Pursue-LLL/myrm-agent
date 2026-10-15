/**
 * [INPUT]
 * @/store/chat/useRewindStore::useRewindStore (POS: UI state manager for rewind dialog target)
 *
 * [OUTPUT]
 * RewindButton: Action button triggering singleton RewindDialog
 *
 * [POS]
 * Per-message action button rendered in UserMessage toolbar. Sets target in useRewindStore.
 */

'use client';

import { useTranslations } from 'next-intl';
import { Undo2 } from 'lucide-react';
import { useRewindStore } from '@/store/chat/useRewindStore';

interface RewindButtonProps {
  chatId: string;
  messageId: string;
  messageIndex: number;
  disabled?: boolean;
}

export function RewindButton({ chatId, messageId, messageIndex, disabled = false }: RewindButtonProps) {
  const openRewind = useRewindStore((s) => s.openRewind);
  const t = useTranslations('chat.rewind');

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    openRewind({ chatId, messageId, messageIndex });
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled}
      className="p-1.5 text-black/50 dark:text-white/50 rounded-lg hover:bg-secondary dark:hover:bg-secondary transition duration-200 hover:text-black dark:hover:text-white disabled:opacity-40 disabled:pointer-events-none"
      title={disabled ? t('streamingBlocked') : t('buttonTitle')}
      aria-label={t('buttonLabel')}
      data-testid="rewind-message-button"
    >
      <Undo2 size={16} />
    </button>
  );
}
