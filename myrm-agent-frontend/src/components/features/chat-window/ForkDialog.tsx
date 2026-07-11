/**
 * Fork Dialog — confirmation dialog for forking conversation from a specific message.
 *
 * I: open, onOpenChange, chatId, messageIndex
 * O: renders Dialog; on confirm calls POST /fork then navigates to new chat
 */

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { GitFork } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { forkConversation } from '@/services/fork-api';
import { useToast } from '@/hooks/useToast';
import useChatStore from '@/store/useChatStore';

interface ForkDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chatId: string;
  messageIndex: number;
}

export function ForkDialog({ open, onOpenChange, chatId, messageIndex }: ForkDialogProps) {
  const router = useRouter();
  const { toast } = useToast();
  const t = useTranslations('chat.fork');
  const [title, setTitle] = useState('');
  const [isForking, setIsForking] = useState(false);

  const handleFork = async () => {
    if (useChatStore.getState().loading) {
      toast({
        title: t('failed'),
        description: t('streamingBlocked'),
        variant: 'destructive',
      });
      return;
    }

    setIsForking(true);

    try {
      const response = await forkConversation(chatId, messageIndex, title || undefined);

      if (response.success && response.data.new_chat_id) {
        toast({
          title: t('success'),
          description: t('successDescription', { index: messageIndex }),
        });

        router.push(`/${response.data.new_chat_id}`);
        onOpenChange(false);
      } else {
        throw new Error(t('failed'));
      }
    } catch (error) {
      toast({
        title: t('failed'),
        description: error instanceof Error ? error.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsForking(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitFork className="h-5 w-5" />
            {t('title')}
          </DialogTitle>
          <DialogDescription>
            {t('description', { index: messageIndex })}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="fork-title">{t('titleLabel')}</Label>
            <Input
              id="fork-title"
              placeholder={t('titlePlaceholder')}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !isForking) handleFork(); }}
              maxLength={255}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isForking}>
            {t('cancel')}
          </Button>
          <Button onClick={handleFork} disabled={isForking}>
            {isForking ? t('creating') : t('create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
