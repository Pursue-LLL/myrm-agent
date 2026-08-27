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
import { GitFork, ShieldCheck } from 'lucide-react';
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
import { Textarea } from '@/components/primitives/textarea';
import { forkConversation } from '@/services/fork-api';
import { useToast } from '@/hooks/shared/useToast';
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
  const [forkMode, setForkMode] = useState<'full_clone' | 'acceptance_verifier'>('full_clone');
  const [acceptanceScope, setAcceptanceScope] = useState('');
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
      const response = await forkConversation(
        chatId,
        messageIndex,
        title || undefined,
        forkMode,
        forkMode === 'acceptance_verifier' ? acceptanceScope || undefined : undefined,
      );

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
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitFork className="h-5 w-5 text-primary" />
            {t('title')}
          </DialogTitle>
          <DialogDescription>{t('description', { index: messageIndex })}</DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-3">
          {/* Mode Selector */}
          <div className="grid gap-2">
            <Label className="text-xs font-semibold text-muted-foreground">{t('modeLabel')}</Label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setForkMode('full_clone')}
                className={`flex flex-col items-start gap-1 p-3 rounded-lg border text-left transition-all ${
                  forkMode === 'full_clone'
                    ? 'border-primary bg-primary/5 shadow-xs'
                    : 'border-border/60 hover:border-border hover:bg-muted/40'
                }`}
              >
                <div className="flex items-center gap-1.5 font-medium text-sm">
                  <GitFork className="h-4 w-4 text-muted-foreground" />
                  {t('modeFullClone')}
                </div>
                <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">{t('modeFullCloneDesc')}</p>
              </button>

              <button
                type="button"
                onClick={() => setForkMode('acceptance_verifier')}
                className={`flex flex-col items-start gap-1 p-3 rounded-lg border text-left transition-all ${
                  forkMode === 'acceptance_verifier'
                    ? 'border-primary bg-primary/5 shadow-xs'
                    : 'border-border/60 hover:border-border hover:bg-muted/40'
                }`}
              >
                <div className="flex items-center gap-1.5 font-medium text-sm text-primary">
                  <ShieldCheck className="h-4 w-4" />
                  {t('modeAcceptance')}
                </div>
                <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">{t('modeAcceptanceDesc')}</p>
              </button>
            </div>
          </div>

          {/* Title input */}
          <div className="grid gap-2">
            <Label htmlFor="fork-title">{t('titleLabel')}</Label>
            <Input
              id="fork-title"
              placeholder={t('titlePlaceholder')}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !isForking && forkMode !== 'acceptance_verifier') {
                  handleFork();
                }
              }}
              maxLength={255}
            />
          </div>

          {/* Acceptance Scope (Only in acceptance_verifier mode) */}
          {forkMode === 'acceptance_verifier' && (
            <div className="grid gap-2">
              <Label htmlFor="fork-acceptance-scope">{t('acceptanceScopeLabel')}</Label>
              <Textarea
                id="fork-acceptance-scope"
                placeholder={t('acceptanceScopePlaceholder')}
                value={acceptanceScope}
                onChange={(e) => setAcceptanceScope(e.target.value)}
                rows={3}
                className="resize-none text-xs"
              />
            </div>
          )}
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
