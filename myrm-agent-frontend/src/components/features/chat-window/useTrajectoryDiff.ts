/**
 * [INPUT]
 * @/services/chat::getSessionTrajectory, getChatHistory (POS: trajectory and recent-session reads)
 * ./trajectoryDiffModel::findDivergence (POS: the comparison rule)
 *
 * [OUTPUT]
 * useTrajectoryDiff: the current session's trajectory, the one picked to compare with, the sessions to pick from
 * and where the two diverge
 *
 * [POS]
 * Data layer of TrajectoryDiffModal: every read answers only for what is selected now.
 */

'use client';

import { useEffect, useMemo, useState } from 'react';

import {
  getChatHistory,
  getSessionTrajectory,
  type ChatHistoryResponse,
  type ChatItem,
  type SessionTrajectoryResponse,
} from '@/services/chat';

import { findDivergence } from './trajectoryDiffModel';

/** How many of the latest sessions can be picked for comparison. */
const RECENT_SESSION_LIMIT = 30;

export type LoadState<T> =
  { status: 'idle' } | { status: 'loading' } | { status: 'ready'; data: T } | { status: 'error' };

const IDLE = { status: 'idle' } as const;
const LOADING = { status: 'loading' } as const;
const ERROR = { status: 'error' } as const;

type Outcome<T> = { key: string; data: T; failed?: undefined } | { key: string; failed: true };

/**
 * Reads `key` through `load`. A read that finishes after the key changed is dropped, and what was read for another
 * key is never shown for this one.
 */
function useLoaded<T>(key: string | null, load: (key: string) => Promise<T>): LoadState<T> {
  const [outcome, setOutcome] = useState<Outcome<T> | null>(null);

  useEffect(() => {
    if (key === null) {
      return;
    }
    let stale = false;
    load(key).then(
      (data) => {
        if (!stale) {
          setOutcome({ key, data });
        }
      },
      () => {
        if (!stale) {
          setOutcome({ key, failed: true });
        }
      },
    );
    return () => {
      stale = true;
    };
  }, [key, load]);

  return useMemo<LoadState<T>>(() => {
    if (key === null) {
      return IDLE;
    }
    if (outcome?.key !== key) {
      return LOADING;
    }
    return outcome.failed ? ERROR : { status: 'ready', data: outcome.data };
  }, [key, outcome]);
}

const loadRecentSessions = (): Promise<ChatHistoryResponse> => getChatHistory(1, RECENT_SESSION_LIMIT);

export function useTrajectoryDiff(open: boolean, currentSessionId: string) {
  const [comparedSessionId, setComparedSessionId] = useState('');

  const current = useLoaded<SessionTrajectoryResponse>(
    open && currentSessionId ? currentSessionId : null,
    getSessionTrajectory,
  );
  const compared = useLoaded<SessionTrajectoryResponse>(comparedSessionId || null, getSessionTrajectory);
  const history = useLoaded<ChatHistoryResponse>(open ? 'recent' : null, loadRecentSessions);

  const sessions = useMemo<LoadState<ChatItem[]>>(
    () =>
      history.status === 'ready'
        ? { status: 'ready', data: history.data.items.filter((item) => item.id !== currentSessionId) }
        : history,
    [history, currentSessionId],
  );

  const divergenceIndex = useMemo(
    () =>
      current.status === 'ready' && compared.status === 'ready' ? findDivergence(current.data, compared.data) : null,
    [current, compared],
  );

  return { current, compared, comparedSessionId, setComparedSessionId, sessions, divergenceIndex };
}
