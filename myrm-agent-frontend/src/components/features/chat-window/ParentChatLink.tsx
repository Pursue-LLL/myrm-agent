/**
 * Parent Chat Link Component
 *
 * Shows link to parent chat if current chat is a fork.
 *
 * [INPUT]
 * - @/services/fork-api::getForkInfo (POS: Fetch fork relationship metadata)
 *
 * [OUTPUT]
 * - ParentChatLink: Conditional navigation link back to parent conversation.
 *
 * [POS]
 * Renders only when the current chat is a fork. Reads fork-info for the chat it is given and never shows
 * the link (or a late answer) of another chat.
 */

'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { getForkInfo } from '@/services/fork-api';

interface ParentChatLinkProps {
  chatId: string;
}

interface ParentOfChat {
  chatId: string;
  parentChatId: string;
  /** Position of the message the fork was made at, counted from 0 like the fork request. */
  forkPoint: number | null;
}

export function ParentChatLink({ chatId }: ParentChatLinkProps) {
  const t = useTranslations('chat.fork');
  const [parent, setParent] = useState<ParentOfChat | null>(null);

  useEffect(() => {
    let cancelled = false;
    getForkInfo(chatId)
      .then(({ success, data }) => {
        if (!cancelled) {
          setParent(
            success && data.parent_chat_id
              ? { chatId, parentChatId: data.parent_chat_id, forkPoint: data.fork_point }
              : null,
          );
        }
      })
      .catch((error: unknown) => {
        console.error('Failed to load fork info:', error);
      });
    return () => {
      cancelled = true;
    };
  }, [chatId]);

  if (parent?.chatId !== chatId) {
    return null;
  }

  return (
    <div className="px-4 py-1.5">
      <Link
        href={`/${parent.parentChatId}`}
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        <span>
          {parent.forkPoint !== null ? t('parentLinkWithIndex', { index: parent.forkPoint + 1 }) : t('parentLink')}
        </span>
      </Link>
    </div>
  );
}
