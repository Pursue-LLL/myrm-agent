'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Timer } from 'lucide-react';
import { listCronJobs } from '@/services/cron';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';

interface ChatCronLinkProps {
  chatId: string;
}

export function ChatCronLink({ chatId }: ChatCronLinkProps) {
  const t = useTranslations('cron');
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listCronJobs({ chat_id: chatId, limit: 50 })
      .then((res) => {
        if (!cancelled) setCount(res.total);
      })
      .catch(() => {
        if (!cancelled) setCount(0);
      });
    return () => {
      cancelled = true;
    };
  }, [chatId]);

  if (count <= 0) return null;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href={`/settings/cron?chat_id=${encodeURIComponent(chatId)}`}
          className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-muted/40 px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:text-foreground hover:border-primary/30"
        >
          <Timer className="h-3 w-3" />
          <span>{t('chatLinkedTasks', { count })}</span>
        </Link>
      </TooltipTrigger>
      <TooltipContent>{t('chatLinkedTasksTooltip')}</TooltipContent>
    </Tooltip>
  );
}
