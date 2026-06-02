'use client';

/**
 * [INPUT]
 * @/services/chat::switchSibling, getSiblings (POS: Chat API service layer)
 * @/store/useChatStore (POS: Chat state store and message state façade)
 *
 * [OUTPUT]
 * SiblingNav: Renders "1/3 ← →" navigation for sibling message groups.
 *
 * [POS]
 * Sibling message navigation control. Allows switching between regenerated response variants.
 */

import { useCallback, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { switchSibling, getSiblings } from '@/services/chat';
import useChatStore from '@/store/useChatStore';

interface SiblingNavProps {
  chatId: string;
  siblingGroupId: string;
  siblingIndex: number;
  siblingCount: number;
}

export default function SiblingNav({ chatId, siblingGroupId, siblingIndex, siblingCount }: SiblingNavProps) {
  const [loading, setLoading] = useState(false);
  const reloadMessages = useChatStore((s) => s.loadMessages);

  const handleSwitch = useCallback(
    async (direction: 'prev' | 'next') => {
      if (loading) return;
      setLoading(true);
      try {
        const { siblings } = await getSiblings(chatId, siblingGroupId);
        if (!siblings.length) return;

        const activeIdx = siblings.findIndex((s) => s.is_active);
        const targetIdx = direction === 'prev' ? activeIdx - 1 : activeIdx + 1;
        if (targetIdx < 0 || targetIdx >= siblings.length) return;

        const target = siblings[targetIdx];
        const result = await switchSibling(chatId, siblingGroupId, target.id);
        if (result.success) {
          await reloadMessages(chatId);
        }
      } catch (err) {
        console.error('Switch sibling failed:', err);
      } finally {
        setLoading(false);
      }
    },
    [chatId, siblingGroupId, loading, reloadMessages],
  );

  if (siblingCount <= 1) return null;

  return (
    <div className="inline-flex items-center gap-0.5 text-xs text-muted-foreground select-none">
      <button
        onClick={() => handleSwitch('prev')}
        disabled={loading || siblingIndex <= 1}
        className="p-0.5 rounded hover:bg-secondary disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        aria-label="Previous sibling"
      >
        <ChevronLeft className="w-3.5 h-3.5" />
      </button>
      <span className="min-w-[2rem] text-center tabular-nums font-medium">
        {siblingIndex}/{siblingCount}
      </span>
      <button
        onClick={() => handleSwitch('next')}
        disabled={loading || siblingIndex >= siblingCount}
        className="p-0.5 rounded hover:bg-secondary disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        aria-label="Next sibling"
      >
        <ChevronRight className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
