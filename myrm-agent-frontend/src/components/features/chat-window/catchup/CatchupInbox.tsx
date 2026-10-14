'use client';

/**
 * Catchup inbox: the chats that moved on while the user was elsewhere.
 *
 * [INPUT]
 * - services/chat::getCatchupBriefs / markChatAsRead (POS: server-side inbox projection and presence stamp)
 * - store/useChatStore (POS: the chat the user has open, which is never news to them)
 * - catchup/CatchupBriefCard (POS: one chat's brief)
 * - window events `subagents_updated` / `cron_updated` / `app_resync_required` / `run-digest-updated`
 *   (POS: global SSE bridge signals that a chat's state changed)
 *
 * [OUTPUT]
 * - CatchupInbox: header popover with a badge count; renders nothing when there is nothing to catch up on
 *
 * [POS]
 * Entry point of the Catchup experience; refetches only on signals that can change the list.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Inbox, X, CheckCircle2 } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Badge } from '@/components/primitives/badge';
import { getCatchupBriefs, markChatAsRead, type CatchupBrief } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { CatchupBriefCard } from './CatchupBriefCard';

const REFETCH_DEBOUNCE_MS = 1000;

interface RunDigestEventDetail {
  chat_id?: string;
  digest?: { phase?: string };
}

export const CatchupInbox: React.FC = () => {
  const t = useTranslations('Catchup');
  const router = useRouter();
  const openChatId = useChatStore((s) => s.chatId?.trim() ?? '');
  const [briefs, setBriefs] = useState<CatchupBrief[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const lastPhaseByChat = useRef(new Map<string, string>());
  const refetchTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const previousOpenChatId = useRef(openChatId);

  const fetchBriefs = useCallback(async () => {
    try {
      const res = await getCatchupBriefs();
      setBriefs(res.briefs || []);
    } catch (error) {
      console.error('Failed to fetch catchup briefs:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const scheduleRefetch = useCallback(() => {
    clearTimeout(refetchTimer.current);
    refetchTimer.current = setTimeout(() => void fetchBriefs(), REFETCH_DEBOUNCE_MS);
  }, [fetchBriefs]);

  useEffect(() => {
    void fetchBriefs();
    // run-digest-updated fires on every tool step; only a phase change can alter the inbox.
    const handleRunDigest = (event: Event) => {
      const { chat_id: chatId, digest } = (event as CustomEvent<RunDigestEventDetail>).detail ?? {};
      if (!chatId || !digest?.phase || lastPhaseByChat.current.get(chatId) === digest.phase) {
        return;
      }
      lastPhaseByChat.current.set(chatId, digest.phase);
      scheduleRefetch();
    };
    window.addEventListener('subagents_updated', scheduleRefetch);
    window.addEventListener('cron_updated', scheduleRefetch);
    window.addEventListener('app_resync_required', scheduleRefetch);
    window.addEventListener('run-digest-updated', handleRunDigest);
    return () => {
      window.removeEventListener('subagents_updated', scheduleRefetch);
      window.removeEventListener('cron_updated', scheduleRefetch);
      window.removeEventListener('app_resync_required', scheduleRefetch);
      window.removeEventListener('run-digest-updated', handleRunDigest);
      clearTimeout(refetchTimer.current);
    };
  }, [fetchBriefs, scheduleRefetch]);

  // Leaving a chat mid-turn makes it an away chat, so the inbox must pick it up.
  useEffect(() => {
    if (previousOpenChatId.current !== openChatId) {
      previousOpenChatId.current = openChatId;
      scheduleRefetch();
    }
  }, [openChatId, scheduleRefetch]);

  // The chat the user is looking at is never news to them.
  const visibleBriefs = briefs.filter((brief) => brief.chat_id !== openChatId);

  const handleRead = async (chatId: string) => {
    try {
      await markChatAsRead(chatId);
      setBriefs((prev) => prev.filter((b) => b.chat_id !== chatId));
      if (visibleBriefs.length <= 1) {
        setIsOpen(false);
      }
      // The list is capped, so dismissing one may let an older chat in.
      scheduleRefetch();
    } catch (error) {
      console.error('Failed to mark chat as read:', error);
    }
  };

  const handleNavigate = async (chatId: string) => {
    await handleRead(chatId);
    router.push(`/${chatId}`);
    setIsOpen(false);
  };

  if (visibleBriefs.length === 0 && !isLoading) {
    return null;
  }

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          className="relative h-9 w-9 rounded-full"
          aria-label={t('openInbox', { count: visibleBriefs.length })}
        >
          <Inbox className="h-5 w-5" />
          {visibleBriefs.length > 0 && (
            <Badge
              variant="destructive"
              className="absolute -top-1.5 -right-1.5 h-5 w-5 flex items-center justify-center p-0 text-[10px] rounded-full border-2 border-background"
            >
              {visibleBriefs.length}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-96 max-w-[calc(100vw-2rem)] p-0 mr-4" align="end">
        <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/30">
          <div className="flex items-center gap-2">
            <Inbox className="h-4 w-4 text-primary" />
            <span className="font-semibold">{t('inboxTitle')}</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={() => setIsOpen(false)}
            aria-label={t('close')}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <ScrollArea className="h-[400px] p-4">
          {isLoading && visibleBriefs.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">{t('loading')}</div>
          ) : visibleBriefs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-muted-foreground text-sm gap-2">
              <CheckCircle2 className="h-8 w-8 text-muted-foreground/50" />
              {t('allCaughtUp')}
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              {visibleBriefs.map((brief) => (
                <CatchupBriefCard key={brief.chat_id} brief={brief} onRead={handleRead} onNavigate={handleNavigate} />
              ))}
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
};
