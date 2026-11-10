'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Timer } from 'lucide-react';
import { countChatCronJobs } from '@/services/cron';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';

interface ChatCronLinkProps {
  chatId: string;
}

interface ChatCronCount {
  chatId: string;
  count: number;
}

export function ChatCronLink({ chatId }: ChatCronLinkProps) {
  const t = useTranslations('cron');
  const [counted, setCounted] = useState<ChatCronCount | null>(null);

  useEffect(() => {
    let cancelled = false;
    countChatCronJobs(chatId)
      .then((count) => {
        if (!cancelled) {
          setCounted({ chatId, count });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCounted(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [chatId]);

  // A count read for another chat is never shown for this one.
  if (counted?.chatId !== chatId || counted.count <= 0) {
    return null;
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href={`/settings/cron?chat_id=${encodeURIComponent(chatId)}`}
          className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-muted/40 px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:text-foreground hover:border-primary/30"
        >
          <Timer className="h-3 w-3" />
          <span>{t('chatLinkedTasks', { count: counted.count })}</span>
        </Link>
      </TooltipTrigger>
      <TooltipContent>{t('chatLinkedTasksTooltip')}</TooltipContent>
    </Tooltip>
  );
}
