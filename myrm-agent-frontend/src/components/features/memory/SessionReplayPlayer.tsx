'use client';

/**
 * [INPUT]
 * - services/statistics::ExecutionTrace (POS: Session analytics trace types)
 * - services/chat::getMessages (POS: Cursor-paginated chat message API)
 * - memory/replayTimeline (POS: Pure timeline builders for replay)
 * - memory/ReplayMessageBubble (POS: Read-only Markdown message rendering)
 * - store/useChatStore (POS: Active chat state merge source)
 *
 * [OUTPUT]
 * - SessionReplayPlayer: Scrubber, speed, keyboard stepping, tri-pane replay UI
 *
 * [POS]
 * Session Replay v2 player. Event-sourcing UI reconstruction without extra backend storage.
 */

import { memo, useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconPlay,
  IconStop,
  IconAlertTriangle,
  IconWrench,
  IconLoader,
  IconCpu,
  IconShieldCheck,
  IconShieldAlert,
  IconBrain,
} from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import type {
  ExecutionTrace,
  TraceToolCall,
  TraceLLMCall,
  TraceHumanFeedback,
  TraceMemoryEvent,
  TraceError,
} from '@/services/statistics';
import { getMessages } from '@/services/chat';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import ReplayMessageBubble from '@/components/features/memory/ReplayMessageBubble';
import {
  buildTimeline,
  buildEventMarkers,
  computeTimelineBounds,
  findActiveEventIndex,
  isErrorLikeEvent,
  mergeMessages,
  messageReasoning,
  normalizeApiMessage,
  snapToNearestEventTime,
  type ReplayEvent,
  type ReplayEventMarker,
} from '@/components/features/memory/replayTimeline';

interface SessionReplayPlayerProps {
  sessionId: string;
  trace: ExecutionTrace;
}

const MARKER_COLORS: Record<ReplayEventMarker['kind'], string> = {
  tool: 'bg-amber-500',
  llm: 'bg-violet-500',
  message: 'bg-blue-500',
  memory: 'bg-teal-500',
  error: 'bg-rose-500',
};

async function loadAllMessages(sessionId: string): Promise<Message[]> {
  const collected: Message[] = [];
  let cursor: string | undefined;
  let hasMore = true;

  while (hasMore) {
    const page = await getMessages(sessionId, { limit: 100, before: cursor, silent: true });
    if (page.messages.length === 0) break;
    collected.unshift(...page.messages.map(normalizeApiMessage));
    hasMore = page.has_more;
    cursor = page.next_cursor ?? undefined;
    if (!cursor) break;
  }

  return collected.sort(
    (a, b) =>
      (a.createdAt instanceof Date ? a.createdAt.getTime() : new Date(a.createdAt).getTime()) -
      (b.createdAt instanceof Date ? b.createdAt.getTime() : new Date(b.createdAt).getTime()),
  );
}

const SessionReplayPlayer = memo<SessionReplayPlayerProps>(({ sessionId, trace }) => {
  const t = useTranslations('settings.sessionAnalytics.replay');
  const storeMessages = useChatStore((state) =>
    state.chatId === sessionId ? state.messages.filter((m) => m.chatId === sessionId) : [],
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
        if (!cancelled) setRemoteMessages(loaded);
      } catch {
        if (!cancelled) setRemoteMessages([]);
      } finally {
        if (!cancelled) setMessagesLoading(false);
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
    if (initializedTimeRef.current || startTime <= 0 || timeline.length === 0) return;
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
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
      lastUpdateRef.current = undefined;
      return;
    }

    const animate = (now: number) => {
      if (!lastUpdateRef.current) lastUpdateRef.current = now;
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
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [isPlaying, playbackSpeed, endTime]);

  const visibleState = useMemo(() => {
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
      if (e.type === 'message') activeMessages.push(e.data);
      else if (e.type === 'tool_start' || e.type === 'tool_end') {
        activeTools.set(`${e.data.sequence}-${e.data.tool_name}`, e.data);
      } else if (e.type === 'llm_call') activeLlmCalls.push(e.data);
      else if (e.type === 'human_feedback') activeHumanFeedback.push(e.data);
      else if (e.type === 'memory') activeMemoryEvents.push(e.data);
      else if (e.type === 'error') latestError = e.data;
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
    if (currentTime >= endTime) setCurrentTime(startTime);
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

  const handleScrubEnd = useCallback(
    (rawTime: number) => {
      setIsScrubbing(false);
      setCurrentTime(snapToNearestEventTime(timeline, rawTime));
      setIsPlaying(false);
    },
    [timeline],
  );

  useEffect(() => {
    if (!keyboardActive) return;
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

  const renderInspector = () => {
    const { activeEvent } = visibleState;

    if (activeEvent?.type === 'error') {
      return (
        <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-full text-xs text-rose-600 dark:text-rose-400 font-mono break-all whitespace-pre-wrap">
          {activeEvent.data.error}
        </div>
      );
    }

    if (activeEvent?.type === 'tool_end' && !activeEvent.data.success) {
      return (
        <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-full text-xs text-rose-600 dark:text-rose-400 font-mono break-all whitespace-pre-wrap">
          {activeEvent.data.error ?? t('toolFailed')}
        </div>
      );
    }

    if (activeEvent?.type === 'human_feedback') {
      const fb = activeEvent.data;
      return (
        <div className="flex flex-col gap-2">
          <div className="text-xs font-medium text-foreground">{t('humanFeedbackTitle')}</div>
          <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-full whitespace-pre-wrap break-all">
            {JSON.stringify(fb, null, 2)}
          </div>
        </div>
      );
    }

    if (activeEvent?.type === 'memory') {
      const me = activeEvent.data;
      return (
        <div className="flex flex-col gap-2">
          <div className="text-xs font-medium text-foreground">{t('memoryEventTitle', { phase: me.phase })}</div>
          <div className="text-[10px] text-muted-foreground">
            {me.title === 'pre_compact' ? t('preCompactEventTitle') : me.title}
          </div>
          <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-full whitespace-pre-wrap break-all max-h-[200px] overflow-y-auto">
            {me.summary}
          </div>
        </div>
      );
    }

    if (activeEvent?.type === 'llm_call') {
      const lc = activeEvent.data;
      return (
        <div className="flex flex-col gap-2">
          <div className="text-xs font-medium text-foreground">
            {t('llmCallTitle', { model: lc.model_name ?? 'unknown' })}
          </div>
          {lc.prompt_preview && (
            <>
              <div className="text-xs font-medium text-foreground">{t('promptPreview')}</div>
              <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-full whitespace-pre-wrap break-all max-h-[160px] overflow-y-auto">
                {lc.prompt_preview}
              </div>
            </>
          )}
          <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-full whitespace-pre-wrap break-all">
            {JSON.stringify(
              {
                prompt_tokens: lc.prompt_tokens,
                completion_tokens: lc.completion_tokens,
                total_tokens: lc.total_tokens,
                duration_ms: lc.duration_ms,
                ttft_ms: lc.ttft_ms,
                message_count: lc.message_count,
              },
              null,
              2,
            )}
          </div>
        </div>
      );
    }

    if (activeEvent?.type === 'tool_start' || activeEvent?.type === 'tool_end') {
      const tool = activeEvent.data;
      return (
        <div className="flex flex-col gap-2">
          <div className="text-xs font-medium text-foreground">{t('latestTool', { name: tool.tool_name })}</div>
          <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-full overflow-x-auto whitespace-pre-wrap break-all">
            {JSON.stringify(tool.input_data ?? {}, null, 2)}
          </div>
          {tool.end_time && (
            <>
              <div className="text-xs font-medium text-foreground mt-1">{t('result')}</div>
              <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 p-2 rounded-full overflow-x-auto whitespace-pre-wrap break-all max-h-[180px] overflow-y-auto">
                {typeof tool.output_data === 'object'
                  ? JSON.stringify(tool.output_data, null, 2)
                  : String(tool.output_data ?? tool.output_summary ?? '')}
              </div>
            </>
          )}
        </div>
      );
    }

    if (activeEvent?.type === 'message') {
      const m = activeEvent.data;
      return (
        <div className="flex flex-col gap-2">
          <div className="text-xs font-medium text-foreground">
            {m.role === 'user' ? t('userMessage') : t('assistantMessage')}
          </div>
          <div className="max-h-[200px] overflow-y-auto">
            <ReplayMessageBubble message={m} />
          </div>
        </div>
      );
    }

    return <p className="text-xs text-muted-foreground">{t('noPayload')}</p>;
  };

  if (messagesLoading && messages.length === 0) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground border border-border/40 rounded-xl">
        <IconLoader className="h-4 w-4 animate-spin" />
        {t('loading')}
      </div>
    );
  }

  const activeIdx = findActiveEventIndex(timeline, currentTime);

  return (
    <div
      ref={containerRef}
      tabIndex={0}
      onFocus={() => setKeyboardActive(true)}
      onBlur={() => setKeyboardActive(false)}
      onMouseDown={() => containerRef.current?.focus()}
      className="flex flex-col gap-4 bg-background border border-border/40 rounded-xl overflow-hidden outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
    >
      <div className="p-3 sm:p-4 border-b border-border/40 bg-muted/10 flex flex-col gap-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">{t('title')}</h3>
            <span className="text-[10px] text-muted-foreground bg-muted px-2 py-0.5 rounded-full uppercase tracking-wide">
              v2
            </span>
            {activeIdx >= 0 && (
              <span className="text-[10px] text-muted-foreground font-mono">
                {activeIdx + 1}/{timeline.length}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={jumpToError}
              disabled={errorMarkers.length === 0}
              className="text-xs text-rose-500 hover:bg-rose-500/10 disabled:opacity-40 disabled:pointer-events-none px-2 py-1 rounded transition-colors flex items-center gap-1"
            >
              <IconAlertTriangle className="w-3 h-3" />
              {t('seekToError')}
            </button>
            <select
              value={playbackSpeed}
              onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
              className="bg-muted/50 text-xs text-foreground border border-border/40 rounded-full px-2 py-1 outline-none focus:ring-1 focus:ring-blue-500/40 cursor-pointer"
              aria-label={t('speed')}
            >
              <option value={0.5}>0.5x</option>
              <option value={1}>1.0x</option>
              <option value={2}>2.0x</option>
              <option value={4}>4.0x</option>
            </select>
          </div>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <button
            type="button"
            onClick={togglePlay}
            className="p-2 hover:bg-muted/50 rounded-full transition-colors text-foreground shrink-0"
            aria-label={isPlaying ? t('pause') : t('play')}
          >
            {isPlaying ? <IconStop className="w-4 h-4" /> : <IconPlay className="w-4 h-4" />}
          </button>

          <div className="flex-1 relative h-8 flex items-center">
            <div className="absolute inset-x-0 flex items-center">
              <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden relative">
                <div className="h-full bg-blue-500 transition-none" style={{ width: `${progressPercent}%` }} />
                {eventMarkers.map((marker, i) => (
                  <div
                    key={`marker-${marker.kind}-${i}`}
                    className={cn(
                      'absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full border border-background',
                      MARKER_COLORS[marker.kind],
                    )}
                    style={{ left: `${Math.max(0, Math.min(100, marker.percent))}%` }}
                    title={t(`marker.${marker.kind}`)}
                  />
                ))}
              </div>
            </div>
            <input
              type="range"
              min={startTime}
              max={endTime}
              value={currentTime}
              onChange={(e) => {
                setIsScrubbing(true);
                setCurrentTime(Number(e.target.value));
                setIsPlaying(false);
              }}
              onMouseUp={(e) => handleScrubEnd(Number((e.target as HTMLInputElement).value))}
              onTouchEnd={(e) => {
                const target = e.target as HTMLInputElement;
                handleScrubEnd(Number(target.value));
              }}
              className="absolute inset-0 w-full opacity-0 cursor-pointer h-full"
              aria-label={t('scrubber')}
            />
          </div>

          <div className="text-[10px] sm:text-xs font-mono text-muted-foreground w-16 sm:w-20 text-right shrink-0">
            {((currentTime - startTime) / 1000).toFixed(1)}s / {(totalDuration / 1000).toFixed(1)}s
          </div>
        </div>

        <p className="text-[10px] text-muted-foreground hidden sm:block">
          {isScrubbing ? t('scrubSnapHint') : t('keyboardHint')}
        </p>
      </div>

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
          <div className="flex-1 flex flex-col gap-2">
            {visibleState.llmCalls.map((lc) => (
              <div
                key={`llm-${lc.sequence}`}
                className="flex items-center gap-2 text-xs p-2 rounded-full border border-border/40 bg-violet-500/5"
              >
                <IconCpu className="w-3.5 h-3.5 shrink-0 text-violet-500" />
                <span className="font-medium text-foreground truncate">{lc.model_name ?? 'LLM'}</span>
                <span className="text-muted-foreground ml-auto shrink-0 font-mono">
                  {lc.total_tokens.toLocaleString()} tok
                </span>
              </div>
            ))}
            {visibleState.memoryEvents.map((me) => (
              <div
                key={`mem-${me.id}`}
                className="flex items-center gap-2 text-xs p-2 rounded-full border border-teal-500/30 bg-teal-500/5"
              >
                <IconBrain className="w-3.5 h-3.5 shrink-0 text-teal-500" />
                <span className="font-medium text-foreground truncate">
                  {me.title === 'pre_compact' ? t('preCompactEventTitle') : me.title}
                </span>
                <span className="text-muted-foreground ml-auto shrink-0 text-[10px] uppercase">{me.phase}</span>
              </div>
            ))}
            {visibleState.humanFeedback.map((fb, idx) => {
              const approved = fb.approved;
              const Icon = approved ? IconShieldCheck : IconShieldAlert;
              return (
                <div
                  key={`fb-${idx}-${fb.timestamp}`}
                  className={cn(
                    'flex items-center gap-2 text-xs p-2 rounded-full border',
                    approved ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-rose-500/30 bg-rose-500/5',
                  )}
                >
                  <Icon className={cn('w-3.5 h-3.5 shrink-0', approved ? 'text-emerald-500' : 'text-rose-500')} />
                  <span className="font-medium text-foreground truncate">{fb.tool_name ?? t('humanFeedback')}</span>
                  <span className={cn('ml-auto shrink-0', approved ? 'text-emerald-600' : 'text-rose-600')}>
                    {approved ? t('approved') : t('rejected')}
                  </span>
                </div>
              );
            })}
            {visibleState.messages.map((m) => {
              const reasoning = messageReasoning(m);
              if (!reasoning) return null;
              return (
                <div
                  key={`reasoning-${m.messageId}`}
                  className="text-xs text-muted-foreground font-mono bg-muted/30 p-2 rounded-full whitespace-pre-wrap"
                >
                  {reasoning}
                </div>
              );
            })}
            {visibleState.tools.map((tc) => (
              <div
                key={`tool-${tc.sequence}-${tc.tool_name}`}
                className="flex items-center gap-2 text-xs p-2 rounded-full border border-border/40 bg-muted/10"
              >
                <IconWrench
                  className={cn(
                    'w-3.5 h-3.5 shrink-0',
                    tc.end_time ? (tc.success ? 'text-emerald-500' : 'text-rose-500') : 'text-amber-500 animate-pulse',
                  )}
                />
                <span className="font-medium text-foreground truncate">{tc.tool_name}</span>
                {!tc.end_time && <span className="text-muted-foreground ml-auto shrink-0">{t('running')}</span>}
              </div>
            ))}
          </div>
        </div>

        <div className="bg-background flex flex-col p-3 sm:p-4 overflow-y-auto border-t lg:border-t-0 border-border/40">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 shrink-0">
            {t('inspector')}
          </h4>
          <div className="flex-1 flex flex-col gap-3">{renderInspector()}</div>
        </div>
      </div>
    </div>
  );
});

SessionReplayPlayer.displayName = 'SessionReplayPlayer';
export default SessionReplayPlayer;
