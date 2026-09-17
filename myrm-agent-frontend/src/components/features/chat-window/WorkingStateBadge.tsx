'use client';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { getWorkingState, type WorkingStateLiveState } from '@/services/memory';
import useChatStore from '@/store/useChatStore';
import { WorkingMemoryBoard } from '@/components/chat/WorkingMemoryBoard';

/**
 * WorkingStateBadge
 *
 * Integrated top-level workbench container in ChatWindow.
 * Renders the full interactive WorkingMemoryBoard if live state or active content exists.
 */
const WorkingStateBadge = memo(() => {
  const [liveState, setLiveState] = useState<WorkingStateLiveState | null>(null);
  const [fallbackContent, setFallbackContent] = useState<string | null>(null);
  const loading = useChatStore((s) => s.loading);
  const prevLoadingRef = useRef(loading);

  const fetchState = useCallback(async () => {
    try {
      const res = await getWorkingState();
      if (res.live_state) {
        setLiveState(res.live_state);
        setFallbackContent(null);
      } else if (res.content && !res.expired) {
        setFallbackContent(res.content);
        setLiveState(null);
      } else {
        setLiveState(null);
        setFallbackContent(null);
      }
    } catch {
      /* non-critical: network failure or degraded memory service */
    }
  }, []);

  useEffect(() => {
    fetchState();
  }, [fetchState]);

  useEffect(() => {
    if (prevLoadingRef.current && !loading) {
      fetchState();
    }
    prevLoadingRef.current = loading;
  }, [loading, fetchState]);

  // If liveState has structured content, render the full board
  if (liveState && (liveState.goal || liveState.subtasks.length > 0 || liveState.traps.length > 0)) {
    return (
      <div className="w-full max-w-3xl mx-auto px-4 py-1">
        <WorkingMemoryBoard
          goal={liveState.goal}
          subtasks={liveState.subtasks}
          traps={liveState.traps}
          activeTurn={liveState.active_turn}
          consolidated={liveState.consolidated}
        />
      </div>
    );
  }

  // Fallback for simple legacy text working state
  if (fallbackContent) {
    return (
      <div className="w-full max-w-3xl mx-auto px-4 py-1">
        <WorkingMemoryBoard
          goal={fallbackContent}
          subtasks={[]}
          traps={[]}
          activeTurn={1}
          consolidated={false}
        />
      </div>
    );
  }

  return null;
});

WorkingStateBadge.displayName = 'WorkingStateBadge';
export default WorkingStateBadge;
