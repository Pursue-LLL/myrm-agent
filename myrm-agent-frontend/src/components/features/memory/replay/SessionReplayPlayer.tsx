'use client';

/**
 * [INPUT]
 * - services/statistics::ExecutionTrace (POS: Session analytics trace types)
 * - services/chat::getMessages (POS: Cursor-paginated chat message API)
 * - memory/replayTimeline (POS: Pure timeline builders for replay)
 * - memory/ReplayMessageBubble (POS: Read-only Markdown message rendering)
 * - store/useChatStore (POS: Active chat state merge source)
 * - memory/ReplayControls | ReplayMindView | ReplayInspector (POS: Pane sub-components)
 *
 * [OUTPUT]
 * - SessionReplayPlayer: Scrubber, speed, keyboard stepping, tri-pane replay UI
 *
 * [POS]
 * Session Replay v2 player. Event-sourcing UI reconstruction without extra backend storage.
 */

import { memo, useMemo, useEffect, useRef, useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconLoader } from '@/components/features/icons/PremiumIcons';
import type {
  ExecutionTrace,
  TraceError,
  TraceHumanFeedback,
  TraceLLMCall,
  TraceMemoryEvent,
  TraceToolCall,
} from '@/services/statistics';
import { getMessages } from '@/services/chat';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import ReplayMessageBubble from '@/components/features/memory/replay/ReplayMessageBubble';
import ReplayControls from '@/components/features/memory/replay/ReplayControls';
import ReplayMindView from '@/components/features/memory/replay/ReplayMindView';
import ReplayInspector from '@/components/features/memory/replay/ReplayInspector';
import {
  buildTimeline,
  buildEventMarkers,
  computeTimelineBounds,
  findActiveEventIndex,
  isErrorLikeEvent,
  mergeMessages,
  normalizeApiMessage,
  snapToNearestEventTime,
  type ReplayEvent,
} from '@/components/features/memory/replay/replayTimeline';

interface SessionReplayPlayerProps {
  sessionId: string;
  trace: ExecutionTrace;
}

interface VisibleReplayState {
  messages: Message[];
  tools: TraceToolCall[];
  llmCalls: TraceLLMCall[];
  humanFeedback: TraceHumanFeedback[];
  memoryEvents: TraceMemoryEvent[];
  latestError: TraceError | null;
  activeEvent: ReplayEvent | null;
}

async function loadAllMessages(sessionId: string): Promise<Message[]> {
  const collected: Message[] = [];
  let cursor: string | undefined;
  let hasMore = true;

  while (hasMore) {
    const page = await getMessages(sessionId, { limit: 100, before: cursor, silent: true });
    if (page.messages.length === 0) {
      break;
    }
    collected.unshift(...page.messages.map(normalizeApiMessage));
    hasMore = page.has_more;
    cursor = page.next_cursor ?? undefined;
    if (!cursor) {
      break;
    }
  }

  return collected.sort(
    (a, b) =>
      (a.createdAt instanceof Date ? a.createdAt.getTime() : new Date(a.createdAt).getTime()) -
      (b.createdAt instanceof Date ? b.createdAt.getTime() : new Date(b.createdAt).getTime()),
  );
}

const SessionReplayPlayer = memo<SessionReplayPlayerProps>(({ sessionId, trace }) => {
  const t = useTranslations('settings.sessionAnalytics.replay');
  // Selectors must return stable references: an inline `.filter()` inside the
  // selector allocates a fresh array each render, which makes useSyncExternalStore
  // re-render forever ("Maximum update depth exceeded") once chatId matches.
  const activeChatId = useChatStore((state) => state.chatId);
  const chatMessages = useChatStore((state) => state.messages);
  const storeMessages = useMemo(
    () => (activeChatId === sessionId ? chatMessages.filter((m) => m.chatId === sessionId) : []),
    [activeChatId, sessionId, chatMessages],
  );

  const [remoteMessages, setRemoteMessages] = useState<Message[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);
  const [keyboardActive, setKeyboardActive] = useState(false);
  const [isScrubbing, setIsScrubbing] = useState(false);
  const animationRef = useRef<number | null>(null);
  const lastUpdateRef = useRef<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const initializedTimeRef = useRef(false);

  const messages = useMemo(() => mergeMessages(storeMessages, remoteMessages), [storeMessages, remoteMessages]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setMessagesLoading(true);
      try {
        const loaded = await loadAllMessages(sessionId);
        if (!cancelled) {
          setRemoteMessages(loaded);
        }
      } catch {
        if (!cancelled) {
          setRemoteMessages([]);
        }
      } finally {
        if (!cancelled) {
          setMessagesLoading(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const timeline = useMemo(() => buildTimeline(messages, trace), [messages, trace]);
  const { startTime, endTime, totalDuration } = useMemo(
    () => computeTimelineBounds(timeline, trace),
    [timeline, trace],
  );

  const eventMarkers = useMemo(
    () => buildEventMarkers(timeline, startTime, totalDuration),
    [timeline, startTime, totalDuration],
  );

  const errorMarkers = useMemo(() => eventMarkers.filter((m) => m.kind === 'error'), [eventMarkers]);

  useEffect(() => {
    if (initializedTimeRef.current || startTime <= 0 || timeline.length === 0) {
      return;
    }
    initializedTimeRef.current = true;
    if (trace.outcome === 'failure') {
      const firstError = timeline.find(isErrorLikeEvent);
      setCurrentTime(firstError ? Math.max(startTime, firstError.time - 1000) : startTime);
    } else {
      setCurrentTime(startTime);
    }
  }, [startTime, trace.outcome, timeline]);

  useEffect(() => {
    if (!isPlaying) {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
      lastUpdateRef.current = null;
      return;
    }

    const animate = (now: number) => {
      if (!lastUpdateRef.current) {
        lastUpdateRef.current = now;
      }
      const deltaMs = now - lastUpdateRef.current;
      lastUpdateRef.current = now;

      setCurrentTime((prev) => {
        const next = prev + deltaMs * playbackSpeed;
        if (next >= endTime) {
          setIsPlaying(false);
          return endTime;
        }
        return next;
      });
      animationRef.current = requestAnimationFrame(animate);
    };

    animationRef.current = requestAnimationFrame(animate);
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isPlaying, playbackSpeed, endTime]);

  const visibleState = useMemo<VisibleReplayState>(() => {
    const visibleEvents = timeline.filter((e) => e.time <= currentTime);
    const activeMessages: Message[] = [];
    const activeTools = new Map<string, TraceToolCall>();
    const activeLlmCalls: TraceLLMCall[] = [];
    const activeHumanFeedback: TraceHumanFeedback[] = [];
    const activeMemoryEvents: TraceMemoryEvent[] = [];
    let latestError: TraceError | null = null;
    let activeEvent: ReplayEvent | null = null;

    visibleEvents.forEach((e) => {
      activeEvent = e;
      if (e.type === 'message') {
        activeMessages.push(e.data);
      } else if (e.type === 'tool_start' || e.type === 'tool_end') {
        activeTools.set(`${e.data.sequence}-${e.data.tool_name}`, e.data);
      } else if (e.type === 'llm_call') {
        activeLlmCalls.push(e.data);
      } else if (e.type === 'human_feedback') {
        activeHumanFeedback.push(e.data);
      } else if (e.type === 'memory') {
        activeMemoryEvents.push(e.data);
      } else if (e.type === 'error') {
        latestError = e.data;
      }
    });

    return {
      messages: activeMessages,
      tools: Array.from(activeTools.values()).sort((a, b) => a.start_time - b.start_time),
      llmCalls: activeLlmCalls,
      humanFeedback: activeHumanFeedback,
      memoryEvents: activeMemoryEvents,
      latestError,
      activeEvent,
    };
  }, [timeline, currentTime]);

  const progressPercent = Math.max(0, Math.min(100, ((currentTime - startTime) / totalDuration) * 100));

  const togglePlay = useCallback(() => {
    if (currentTime >= endTime) {
      setCurrentTime(startTime);
    }
    setIsPlaying((prev) => !prev);
  }, [currentTime, endTime, startTime]);

  const jumpToError = useCallback(() => {
    const firstError = timeline.find(isErrorLikeEvent);
    if (firstError) {
      setCurrentTime(Math.max(startTime, firstError.time - 1000));
      setIsPlaying(false);
    }
  }, [timeline, startTime]);

  const stepFrame = useCallback(
    (direction: -1 | 1) => {
      const idx = timeline.findIndex((e) => e.time > currentTime);
      const currentIdx = idx === -1 ? timeline.length - 1 : idx - 1;
      const targetIdx = Math.max(0, Math.min(timeline.length - 1, currentIdx + direction));
      if (timeline[targetIdx]) {
        setCurrentTime(timeline[targetIdx].time);
        setIsPlaying(false);
      }
    },
    [timeline, currentTime],
  );

  const handleScrubChange = useCallback((rawTime: number) => {
    setIsScrubbing(true);
    setCurrentTime(rawTime);
    setIsPlaying(false);
  }, []);

  const handleScrubEnd = useCallback(
    (rawTime: number) => {
      setIsScrubbing(false);
      setCurrentTime(snapToNearestEventTime(timeline, rawTime));
      setIsPlaying(false);
    },
    [timeline],
  );

  useEffect(() => {
    if (!keyboardActive) {
      return;
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === ' ' || e.key === 'Spacebar') {
        e.preventDefault();
        togglePlay();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        stepFrame(-1);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        stepFrame(1);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [keyboardActive, togglePlay, stepFrame]);

  if (messagesLoading && messages.length === 0) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground border border-border/40 rounded-xl">
        <IconLoader className="h-4 w-4 animate-spin" />
        {t('loading')}
      </div>
    );
  }

  const activeIdx = findActiveEventIndex(timeline, currentTime);

  /* oxlint-disable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex -- keyboard-capture container with application role */
  return (
    <div
      ref={containerRef}
      role="application"
      tabIndex={0}
      onFocus={() => setKeyboardActive(true)}
      onBlur={() => setKeyboardActive(false)}
      onMouseDown={() => containerRef.current?.focus()}
      className="flex flex-col gap-4 bg-background border border-border/40 rounded-xl overflow-hidden outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
    >
      <ReplayControls
        activeIndex={activeIdx}
        timelineLength={timeline.length}
        currentTime={currentTime}
        startTime={startTime}
        endTime={endTime}
        totalDuration={totalDuration}
        progressPercent={progressPercent}
        isPlaying={isPlaying}
        isScrubbing={isScrubbing}
        playbackSpeed={playbackSpeed}
        errorCount={errorMarkers.length}
        eventMarkers={eventMarkers}
        onTogglePlay={togglePlay}
        onSeekToError={jumpToError}
        onSpeedChange={setPlaybackSpeed}
        onScrubChange={handleScrubChange}
        onScrubEnd={handleScrubEnd}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-px bg-border/40 min-h-[360px] lg:h-[480px]">
        <div className="bg-background flex flex-col p-3 sm:p-4 overflow-y-auto">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 shrink-0">
            {t('chatView')}
          </h4>
          <div className="flex-1 flex flex-col gap-3">
            {visibleState.messages.length === 0 && <p className="text-xs text-muted-foreground">{t('emptyState')}</p>}
            {visibleState.messages.map((m) => (
              <ReplayMessageBubble key={m.messageId} message={m} />
            ))}
          </div>
        </div>

        <div className="bg-background flex flex-col p-3 sm:p-4 overflow-y-auto border-t lg:border-t-0 border-border/40">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 shrink-0">
            {t('mindView')}
          </h4>
          <ReplayMindView
            llmCalls={visibleState.llmCalls}
            memoryEvents={visibleState.memoryEvents}
            humanFeedback={visibleState.humanFeedback}
            messages={visibleState.messages}
            tools={visibleState.tools}
          />
        </div>

        <div className="bg-background flex flex-col p-3 sm:p-4 overflow-y-auto border-t lg:border-t-0 border-border/40">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 shrink-0">
            {t('inspector')}
          </h4>
          <div className="flex-1 flex flex-col gap-3">
            <ReplayInspector activeEvent={visibleState.activeEvent} />
          </div>
        </div>
      </div>
    </div>
  );
  /* oxlint-enable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */
});

SessionReplayPlayer.displayName = 'SessionReplayPlayer';
export default SessionReplayPlayer;
