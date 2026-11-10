'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { toast as appToast } from '@/lib/utils/toast';
import { getNotificationStreamUrl } from '@/lib/deploy-mode';
import useConfigStore from '@/store/useConfigStore';
import { notificationService } from '@/services/notification';

import { dispatchGlobalEvent } from '@/hooks/globalEvents/dispatchGlobalEvent';
import type { GlobalEventDeps, PushToast, SSEPayload } from '@/hooks/globalEvents/eventTypes';

const BC_CHANNEL = 'myrm-sse-events';
const LEADER_KEY = 'myrm-sse-leader';
const HEARTBEAT_INTERVAL = 3_000;
const HEARTBEAT_TIMEOUT = 6_000;

/**
 * Cross-tab SSE sharing via BroadcastChannel + leader election.
 * Only the leader tab maintains the actual EventSource connection;
 * followers receive events through BroadcastChannel, avoiding
 * HTTP/1.1 connection pool exhaustion when multiple tabs are open.
 */
export function useGlobalEvents(): void {
  const router = useRouter();
  const t = useTranslations('notifications');
  const tIdle = useTranslations('backgroundTasks.idleStatus');
  const tKanban = useTranslations('kanban');
  const enabled = useConfigStore((s) => s.enableWebNotifications);
  const sourceRef = useRef<EventSource | null>(null);
  const isLeaderRef = useRef(false);
  const retryRef = useRef(0);
  const tabId = useRef(crypto.randomUUID());
  const debouncedRefetches = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    const bc = new BroadcastChannel(BC_CHANNEL);
    let disposed = false;
    let reconciling = false;
    let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
    let watchdogTimer: ReturnType<typeof setTimeout> | null = null;

    const pushToast: PushToast = {
      info: (...args: Parameters<typeof appToast.info>) => {
        if (enabled) {
          appToast.info(...args);
        }
      },
      success: (...args: Parameters<typeof appToast.success>) => {
        if (enabled) {
          appToast.success(...args);
        }
      },
      warning: (...args: Parameters<typeof appToast.warning>) => {
        if (enabled) {
          appToast.warning(...args);
        }
      },
      error: (...args: Parameters<typeof appToast.error>) => {
        if (enabled) {
          appToast.error(...args);
        }
      },
      dismiss: appToast.dismiss.bind(appToast),
    };

    function notifyIfLeader(title: string, body?: string, onClick?: () => void) {
      if (isLeaderRef.current && enabled) {
        notificationService.notify(title, { body, fallbackToToast: false, onClick });
      }
    }

    const deps: GlobalEventDeps = { router, t, tIdle, tKanban, pushToast, notifyIfLeader, debouncedRefetches };

    function handleEvent(payload: SSEPayload) {
      dispatchGlobalEvent(payload, deps);
    }

    function connectSSE() {
      if (disposed || !isLeaderRef.current) {
        return;
      }
      sourceRef.current?.close();

      const es = new EventSource(getNotificationStreamUrl());
      sourceRef.current = es;

      es.onopen = async () => {
        retryRef.current = 0;

        window.dispatchEvent(new CustomEvent('app_resync_required'));
        bc.postMessage({ kind: 'resync-pulse' });

        if (reconciling) {
          return;
        }
        reconciling = true;
        try {
          const { default: useChatStore } = await import('@/store/useChatStore');
          const { chatId } = useChatStore.getState();
          if (chatId) {
            // A stream reconnecting mid-turn is exactly when this onopen fires; the refresh skips
            // while a stream owns the store, so transient SSE fields are never overwritten.
            const { refreshOpenChatTranscript } = await import('@/store/chat/chatTranscriptRefresh');
            await refreshOpenChatTranscript(chatId);
          }
        } finally {
          reconciling = false;
        }
      };

      es.onmessage = (ev: MessageEvent<string>) => {
        try {
          const payload: SSEPayload = JSON.parse(ev.data);
          bc.postMessage({ kind: 'sse-event', payload });
          handleEvent(payload);
        } catch {
          /* malformed */
        }
      };

      es.onerror = () => {
        es.close();
        sourceRef.current = null;
        if (disposed || !isLeaderRef.current) {
          return;
        }
        const delay = Math.min(1000 * 2 ** retryRef.current, 30_000);
        retryRef.current += 1;
        setTimeout(connectSSE, delay);
      };
    }

    function becomeLeader() {
      if (isLeaderRef.current) {
        return;
      }
      isLeaderRef.current = true;
      localStorage.setItem(LEADER_KEY, tabId.current);
      connectSSE();
      heartbeatTimer = setInterval(() => {
        bc.postMessage({ kind: 'heartbeat', tabId: tabId.current });
      }, HEARTBEAT_INTERVAL);
    }

    function stepDown() {
      isLeaderRef.current = false;
      if (heartbeatTimer) {
        clearInterval(heartbeatTimer);
        heartbeatTimer = null;
      }
      sourceRef.current?.close();
      sourceRef.current = null;
    }

    function resetWatchdog() {
      if (watchdogTimer) {
        clearTimeout(watchdogTimer);
      }
      watchdogTimer = setTimeout(() => {
        if (!disposed) {
          becomeLeader();
        }
      }, HEARTBEAT_TIMEOUT);
    }

    bc.onmessage = (ev: MessageEvent<{ kind: string; payload?: SSEPayload; tabId?: string }>) => {
      const msg = ev.data;
      if (msg.kind === 'sse-event' && msg.payload && !isLeaderRef.current) {
        handleEvent(msg.payload);
      } else if (msg.kind === 'resync-pulse' && !isLeaderRef.current) {
        window.dispatchEvent(new CustomEvent('app_resync_required'));
      } else if (msg.kind === 'heartbeat' && msg.tabId !== tabId.current) {
        if (isLeaderRef.current) {
          stepDown();
        }
        resetWatchdog();
      } else if (msg.kind === 'leader-claim' && msg.tabId !== tabId.current) {
        if (isLeaderRef.current) {
          stepDown();
        }
        resetWatchdog();
      }
    };

    const existingLeader = localStorage.getItem(LEADER_KEY);
    if (!existingLeader) {
      becomeLeader();
      bc.postMessage({ kind: 'leader-claim', tabId: tabId.current });
    } else {
      resetWatchdog();
      bc.postMessage({ kind: 'leader-claim', tabId: tabId.current });
      setTimeout(() => {
        if (!disposed && !isLeaderRef.current) {
          const current = localStorage.getItem(LEADER_KEY);
          if (!current || current === tabId.current) {
            becomeLeader();
          }
        }
      }, HEARTBEAT_TIMEOUT);
    }

    return () => {
      disposed = true;
      stepDown();
      if (watchdogTimer) {
        clearTimeout(watchdogTimer);
      }
      if (isLeaderRef.current) {
        localStorage.removeItem(LEADER_KEY);
      }
      bc.close();
      Object.values(debouncedRefetches.current).forEach(clearTimeout);
      debouncedRefetches.current = {};
    };
  }, [router, t, tIdle, tKanban, enabled]);
}
