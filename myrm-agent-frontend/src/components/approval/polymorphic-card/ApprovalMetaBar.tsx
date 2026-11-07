'use client';

import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { MessageSquare } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import useApprovalStore from '@/store/useApprovalStore';
import { ExpiryCountdown } from './ExpiryCountdown';

/** The strip above an approval: the way back to the chat that raised it and the time left to decide. */
export function ApprovalMetaBar({ chatId, expiresAt }: { chatId?: string; expiresAt?: string }) {
  const tNotifications = useTranslations('notifications');
  const router = useRouter();
  const hideDrawer = useApprovalStore((s) => s.hideDrawer);

  if (!chatId && !expiresAt) {
    return null;
  }

  const handleJumpToChat = () => {
    hideDrawer();
    router.push(`/chat/${chatId}`);
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/30 px-3 py-2">
      <div className="flex items-center gap-2 min-w-0">
        {chatId && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1 px-2 text-xs"
            onClick={handleJumpToChat}
            aria-label={tNotifications('jumpToChatAria')}
          >
            <MessageSquare className="h-3 w-3" aria-hidden="true" />
            <span>{tNotifications('jumpToChat')}</span>
          </Button>
        )}
      </div>
      {expiresAt && <ExpiryCountdown expiresAt={expiresAt} />}
    </div>
  );
}
