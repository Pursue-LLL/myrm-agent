/**
 * Parent Chat Link Component
 *
 * Shows link to parent chat if current chat is a fork.
 * P0-3 implementation.
 */

'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { getForkInfo } from '@/services/fork-api';

interface ParentChatLinkProps {
  chatId: string;
}

export function ParentChatLink({ chatId }: ParentChatLinkProps) {
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
    <Link
      href={`/${parentChatId}`}
      className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
    >
      <ArrowLeft className="h-4 w-4" />
      <span>
        Forked from parent conversation
        {forkPoint !== null && ` (from message #${forkPoint})`}
      </span>
    </Link>
  );
}

/**
 * Integration TODO:
 *
 * Add to ChatHeader component:
 *
 * ```tsx
 * import { ParentChatLink } from './ParentChatLink';
 *
 * // Inside ChatHeader component:
 * <div className="flex items-center gap-4">
 *   <ParentChatLink chatId={chatId} />
 *   {/ ...other header content /}
 * </div>
 * ```
 */
