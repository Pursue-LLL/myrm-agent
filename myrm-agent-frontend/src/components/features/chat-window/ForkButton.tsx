/**
 * Fork Button — triggers ForkDialog to create a conversation branch from a message.
 *
 * I: chatId, messageIndex, variant, size
 * O: renders ghost button with GitFork icon + ForkDialog
 */

'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { GitFork } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { ForkDialog } from './ForkDialog';

interface ForkButtonProps {
  chatId: string;
  messageIndex: number;
  variant?: 'ghost' | 'outline' | 'default';
  size?: 'sm' | 'md' | 'lg';
}

export function ForkButton({ chatId, messageIndex, variant = 'ghost', size = 'sm' }: ForkButtonProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const t = useTranslations('chat.fork');
  const buttonSize = size === 'md' ? 'default' : size;

  return (
    <>
      <Button
        variant={variant}
        size={buttonSize}
        onClick={() => setDialogOpen(true)}
        aria-label={t('buttonLabel')}
        title={t('buttonTitle')}
      >
        <GitFork className="h-4 w-4" />
      </Button>

      {dialogOpen && (
        <ForkDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          chatId={chatId}
          messageIndex={messageIndex}
        />
      )}
    </>
  );
}
