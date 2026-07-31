/**
 * Rewind Dialog — confirm rewinding conversation to before a user message.
 */

'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Undo2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { rewindToMessage } from '@/services/chat';
import { ApiError } from '@/lib/api';
import { useToast } from '@/hooks/shared/useToast';
import useChatStore from '@/store/useChatStore';
import { stripUserMessageDisplayText, parseExplicitSkillActivation } from '@/lib/utils/messageUtils';

interface RewindDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chatId: string;
  messageId: string;
  messageIndex: number;
}

export function RewindDialog({
  open,
  onOpenChange,
  chatId,
  messageId,
  messageIndex,
}: RewindDialogProps) {
  const { toast } = useToast();
  const t = useTranslations('chat.rewind');
  const [isRewinding, setIsRewinding] = useState(false);

  const handleRewind = async () => {
    if (useChatStore.getState().loading) {
      toast({
        title: t('failed'),
        description: t('streamingBlocked'),
        variant: 'destructive',
      });
      return;
    }

    setIsRewinding(true);
    try {
      const response = await rewindToMessage(chatId, messageId);
      const envelope = response as { data?: { composer_text?: string; goal_paused?: boolean } };
      const payload = envelope.data ?? (response as { composer_text?: string; goal_paused?: boolean });
      const composerRaw = typeof payload.composer_text === 'string' ? payload.composer_text : '';
      const activation = parseExplicitSkillActivation(composerRaw);
      const composerText = activation
        ? activation.instruction
        : stripUserMessageDisplayText(composerRaw);

      useChatStore.setState((state) => ({
        messages: state.messages.slice(0, messageIndex),
        inputMessage: composerText,
      }));

      if (payload.goal_paused) {
        toast({
          title: t('success'),
          description: t('goalPausedNotice'),
        });
      } else {
        toast({
          title: t('success'),
          description: t('successDescription'),
        });
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        toast({
          title: t('failed'),
          description: t('streamingBlocked'),
          variant: 'destructive',
        });
        return;
      }
      const message = error instanceof Error ? error.message : t('unknownError');
      toast({
        title: t('failed'),
        description: message,
        variant: 'destructive',
      });
    } finally {
      setIsRewinding(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Undo2 className="h-5 w-5" />
            {t('title')}
          </DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        <p className="text-sm text-muted-foreground">{t('sideEffectNotice')}</p>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isRewinding}>
            {t('cancel')}
          </Button>
          <Button onClick={handleRewind} disabled={isRewinding}>
            {isRewinding ? t('rewinding') : t('confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
