'use client';

import React, { useEffect, useState } from 'react';
import { Inbox, X, CheckCircle2 } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Badge } from '@/components/ui/badge';
import { getCatchupBriefs, markChatAsRead, type CatchupBrief } from '@/services/chat';
import { CatchupBriefCard } from './CatchupBriefCard';

export const CatchupInbox: React.FC = () => {
  const t = useTranslations('Catchup');
  const router = useRouter();
  const [briefs, setBriefs] = useState<CatchupBrief[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const fetchBriefs = async () => {
    try {
      setIsLoading(true);
      const res = await getCatchupBriefs();
      console.log('Catchup briefs fetched:', res);
      setBriefs(res.briefs || []);
    } catch (error) {
      console.error('Failed to fetch catchup briefs:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchBriefs();
    let timeoutId: NodeJS.Timeout;
    const handleSseEvent = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => fetchBriefs(), 1000);
    };
    window.addEventListener('subagents_updated', handleSseEvent);
    window.addEventListener('cron_updated', handleSseEvent);
    window.addEventListener('app_resync_required', handleSseEvent);
    return () => {
      window.removeEventListener('subagents_updated', handleSseEvent);
      window.removeEventListener('cron_updated', handleSseEvent);
      window.removeEventListener('app_resync_required', handleSseEvent);
      clearTimeout(timeoutId);
    };
  }, []);

  const handleRead = async (chatId: string) => {
    try {
      await markChatAsRead(chatId);
      setBriefs((prev) => prev.filter((b) => b.chat_id !== chatId));
      if (briefs.length <= 1) {
        setIsOpen(false);
      }
    } catch (error) {
      console.error('Failed to mark chat as read:', error);
    }
  };

  const handleNavigate = async (chatId: string) => {
    await handleRead(chatId);
    router.push(`/${chatId}`);
    setIsOpen(false);
  };

  if (briefs.length === 0 && !isLoading) {
    return null;
  }

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="icon" className="relative h-9 w-9 rounded-full">
          <Inbox className="h-5 w-5" />
          {briefs.length > 0 && (
            <Badge
              variant="destructive"
              className="absolute -top-1.5 -right-1.5 h-5 w-5 flex items-center justify-center p-0 text-[10px] rounded-full border-2 border-background"
            >
              {briefs.length}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-96 p-0 mr-4" align="end">
        <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/30">
          <div className="flex items-center gap-2">
            <Inbox className="h-4 w-4 text-primary" />
            <span className="font-semibold">{t('inboxTitle', { defaultValue: 'Catchup Inbox' })}</span>
          </div>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setIsOpen(false)}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <ScrollArea className="h-[400px] p-4">
          {isLoading && briefs.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
              {t('loading', { defaultValue: 'Loading...' })}
            </div>
          ) : briefs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-muted-foreground text-sm gap-2">
              <CheckCircle2 className="h-8 w-8 text-muted-foreground/50" />
              {t('allCaughtUp', { defaultValue: "You're all caught up!" })}
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              {briefs.map((brief) => (
                <CatchupBriefCard key={brief.chat_id} brief={brief} onRead={handleRead} onNavigate={handleNavigate} />
              ))}
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
};
