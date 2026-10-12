/**
 * Memory Citation Badge Component for Chat Message Bubbles.
 *
 * [INPUT] MemoryCitationBadgeProps (memories, sessionId, onClick)
 * [OUTPUT] JSX.Element - Interactive capsule displaying citation counts & epistemic dot breakdown
 * [POS] Item 30 chat message decoration. Strictly under 120 lines. Zero `any`.
 */

import React from 'react';
import { Brain, ChevronRight } from 'lucide-react';
import type { MemoryCitationBadgeProps } from './memoryInspectorTypes';
import { useMemoryInspectorStore } from '@/store/useMemoryInspectorStore';

export const MemoryCitationBadge: React.FC<MemoryCitationBadgeProps> = ({
  memories,
  sessionId = 'default_session',
  onClick,
  className = '',
}) => {
  const openInspector = useMemoryInspectorStore((state) => state.openInspector);

  if (!memories || memories.length === 0) {
    return null;
  }

  const assertionCount = memories.filter((m) => m.epistemic_tier === 'assertion').length;
  const observationCount = memories.filter((m) => m.epistemic_tier === 'observation').length;
  const beliefCount = memories.filter((m) => m.epistemic_tier === 'belief').length;

  const handleClick = () => {
    if (onClick) {
      onClick();
    } else {
      openInspector(sessionId, memories);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-label={`查看引用 ${memories.length} 条记忆`}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border border-violet-500/20 bg-violet-50/60 dark:bg-violet-950/20 text-violet-700 dark:text-violet-300 hover:bg-violet-100/80 dark:hover:bg-violet-900/40 transition-colors shadow-2xs group cursor-pointer ${className}`}
    >
      <Brain className="w-3.5 h-3.5 text-violet-600 dark:text-violet-400 shrink-0 group-hover:scale-110 transition-transform" />
      <span>引用 {memories.length} 条记忆</span>

      <span className="inline-flex items-center gap-1 pl-1 border-l border-violet-200 dark:border-violet-800">
        {assertionCount > 0 && (
          <span
            title={`断言: ${assertionCount}`}
            className="w-2 h-2 rounded-full bg-emerald-500 shrink-0 inline-block"
          />
        )}
        {observationCount > 0 && (
          <span
            title={`观察: ${observationCount}`}
            className="w-2 h-2 rounded-full bg-sky-500 shrink-0 inline-block"
          />
        )}
        {beliefCount > 0 && (
          <span
            title={`信念: ${beliefCount}`}
            className="w-2 h-2 rounded-full bg-amber-500 shrink-0 inline-block"
          />
        )}
      </span>

      <ChevronRight className="w-3 h-3 opacity-60 group-hover:translate-x-0.5 transition-transform" />
    </button>
  );
};
