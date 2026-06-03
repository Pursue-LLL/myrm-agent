/**
 * Fork Button Component
 *
 * Button to fork conversation from specific message.
 * P0-3 implementation.
 */

'use client';

import { useState } from 'react';
import { GitFork } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { ForkDialog } from './ForkDialog';

interface ForkButtonProps {
  chatId: string;
  messageIndex: number;
  messageContent?: string;
  variant?: 'ghost' | 'outline' | 'default';
  size?: 'sm' | 'md' | 'lg';
}

export function ForkButton({ chatId, messageIndex, messageContent, variant = 'ghost', size = 'sm' }: ForkButtonProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const buttonSize = size === 'md' ? 'default' : size;

  return (
    <>
      <Button
        variant={variant}
        size={buttonSize}
        onClick={() => setDialogOpen(true)}
        aria-label="Fork conversation from this message"
        title="Fork conversation"
      >
        <GitFork className="h-4 w-4" />
      </Button>

      <ForkDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        chatId={chatId}
        messageIndex={messageIndex}
        messageSnippet={messageContent}
      />
    </>
  );
}
