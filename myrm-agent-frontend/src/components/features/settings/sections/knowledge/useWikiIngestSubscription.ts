/**
 * [INPUT]
 * @/services/wikiService::{wikiService, QueueStatus, CompileRunStatus} (POS: Wiki REST client with agent scope)
 *
 * [OUTPUT]
 * useWikiIngestSubscription: EventSource hook for wiki ingest SSE snapshots
 * WikiIngestSnapshot: SSE payload typing for queue stats + compile_run
 *
 * [POS]
 * Settings Wiki live ingest updates. Replaces interval polling when SSE is connected.
 */

import { useEffect, useMemo, useState } from 'react';
import type { CompileRunStatus } from '@/services/wikiService';

export interface WikiIngestSnapshotStats {
  pending: number;
  processing: number;
  completed: number;
  failed: number;
}

export interface WikiIngestSnapshot {
  agent_id?: string | null;
  stats: WikiIngestSnapshotStats;
  synthesis_pending_count?: number;
  compile_run?: CompileRunStatus | null;
  sync_required?: boolean;
  tree_sync_required?: boolean;
  stats_refresh_required?: boolean;
}

function buildIngestStreamUrl(agentScopeId?: string | null): string {
  if (!agentScopeId) {
    return '/api/v1/wiki/ingest/stream';
  }
  return `/api/v1/wiki/ingest/stream?agent_id=${encodeURIComponent(agentScopeId)}`;
}

function parseIngestSnapshot(raw: unknown): WikiIngestSnapshot | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const candidate = raw as WikiIngestSnapshot;
  if (!candidate.stats || typeof candidate.stats !== 'object') {
    return null;
  }
  return candidate;
}

export function useWikiIngestSubscription(
  agentScopeId?: string | null,
  options?: {
    enabled?: boolean;
    onSnapshot?: (snapshot: WikiIngestSnapshot) => void;
  },
) {
  const [connected, setConnected] = useState(false);
  const [snapshot, setSnapshot] = useState<WikiIngestSnapshot | null>(null);
  const enabled = options?.enabled ?? true;
  const onSnapshot = options?.onSnapshot;
  const streamUrl = useMemo(() => buildIngestStreamUrl(agentScopeId), [agentScopeId]);

  useEffect(() => {
    if (!enabled) {
      setConnected(false);
      return;
    }

    let disposed = false;
    const eventSource = new EventSource(streamUrl);

    const handleOpen = () => {
      if (!disposed) {
        setConnected(true);
      }
    };

    const handleSnapshot = (event: MessageEvent<string>) => {
      try {
        const parsed = parseIngestSnapshot(JSON.parse(event.data) as unknown);
        if (!parsed || disposed) {
          return;
        }
        setSnapshot(parsed);
        onSnapshot?.(parsed);
      } catch (error) {
        console.warn('Failed to parse wiki ingest SSE payload.', error);
      }
    };

    eventSource.addEventListener('open', handleOpen);
    eventSource.addEventListener('ingest_snapshot', handleSnapshot as EventListener);
    eventSource.onerror = () => {
      if (!disposed) {
        setConnected(false);
      }
    };

    return () => {
      disposed = true;
      setConnected(false);
      eventSource.removeEventListener('open', handleOpen);
      eventSource.removeEventListener('ingest_snapshot', handleSnapshot as EventListener);
      eventSource.close();
    };
  }, [enabled, onSnapshot, streamUrl]);

  return { connected, snapshot };
}
