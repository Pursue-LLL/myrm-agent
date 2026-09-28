/**
 * Rewind Button — triggers RewindDialog to roll back conversation and/or files to before a message.
 *
 * I: chatId, messageId, messageIndex, disabled
 * O: renders button with Undo2 icon + RewindDialog
 */

'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Undo2 } from 'lucide-react';
import { RewindDialog } from './RewindDialog';

interface RewindButtonProps {
  chatId: string;
  messageId: string;
  messageIndex: number;
  disabled?: boolean;
}

export function RewindButton({ chatId, messageId, messageIndex, disabled = false }: RewindButtonProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const t = useTranslations('chat.rewind');

  if (typeof window !== 'undefined') {
    const g = window as unknown as Record<string, unknown>;
    g.__REWIND_BTN_RENDERED__ = {
      dialogOpen,
      chatId,
      messageId,
      messageIndex,
      disabled,
      time: Date.now(),
    };
  }

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (typeof window !== 'undefined') {
      const g = window as unknown as Record<string, unknown>;
      g.__REWIND_BTN_CLICKED__ = {
        time: Date.now(),
        chatId,
        messageId,
        messageIndex,
        disabled,
      };
    }
    setDialogOpen(true);
  };

  return (
    <>
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

      {dialogOpen && (
        <RewindDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          chatId={chatId}
          messageId={messageId}
          messageIndex={messageIndex}
        />
      )}
    </>
  );
}
