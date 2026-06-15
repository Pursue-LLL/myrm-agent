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
 * Renders only when the current chat is a fork. Fetches fork-info once on mount.
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

export function ParentChatLink({ chatId }: ParentChatLinkProps) {
  const t = useTranslations('chat.fork');
  const [parentChatId, setParentChatId] = useState<string | null>(null);
  const [forkPoint, setForkPoint] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadForkInfo() {
      try {
        const response = await getForkInfo(chatId);

        if (response.success && response.data.parent_chat_id) {
          setParentChatId(response.data.parent_chat_id);
          setForkPoint(response.data.fork_point);
        }
      } catch (error) {
        console.error('Failed to load fork info:', error);
      } finally {
        setLoading(false);
      }
    }

    loadForkInfo();
  }, [chatId]);

  if (loading || !parentChatId) {
    return null;
  }

  return (
    <div className="px-4 py-1.5">
      <Link
        href={`/${parentChatId}`}
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        <span>
          {forkPoint !== null
            ? t('parentLinkWithIndex', { index: forkPoint })
            : t('parentLink')}
        </span>
      </Link>
    </div>
  );
}
