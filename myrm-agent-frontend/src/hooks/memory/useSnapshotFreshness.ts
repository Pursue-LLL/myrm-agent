/**
 * [INPUT]
 * @/services/memory/snapshotFreshness::DTOs and API methods
 * React::useState, useCallback
 *
 * [OUTPUT]
 * useSnapshotFreshness: React hook managing session memory snapshot digests,
 *   staleness/dirty tracking, direct-disk hints, and append-only delta patch injection.
 *
 * [POS]
 * Hook module for Item 157 SnapshotLagAwareMemoryFreshnessAndDiskVerificationContractSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { useCallback, useState } from 'react';
import {
  DeltaPatchBlockDTO,
  DirectDiskReadHintDTO,
  InitSnapshotRequest,
  MemorySnapshotDigestDTO,
  RecordWriteRequest,
  SnapshotFreshnessStateDTO,
  getDeltaPatch,
  getDiskReadHint,
  getSnapshotFreshnessState,
  initSessionSnapshot,
  recordSessionWrite,
  resetSessionFreshness,
} from '@/services/memory/snapshotFreshness';

export interface UseSnapshotFreshnessState {
  isLoading: boolean;
  digest: MemorySnapshotDigestDTO | null;
  state: SnapshotFreshnessStateDTO | null;
  diskHint: DirectDiskReadHintDTO | null;
  deltaPatch: DeltaPatchBlockDTO | null;
  error: string | null;
}

export interface UseSnapshotFreshnessReturn extends UseSnapshotFreshnessState {
  initSnapshot: (req: InitSnapshotRequest) => Promise<MemorySnapshotDigestDTO | null>;
  recordWrite: (req: RecordWriteRequest) => Promise<SnapshotFreshnessStateDTO | null>;
  fetchState: (sessionId: string) => Promise<SnapshotFreshnessStateDTO | null>;
  fetchDiskHint: (sessionId: string) => Promise<DirectDiskReadHintDTO | null>;
  fetchDeltaPatch: (sessionId: string) => Promise<DeltaPatchBlockDTO | null>;
  resetSession: (sessionId: string) => Promise<boolean>;
  clearLocalState: () => void;
}

export function useSnapshotFreshness(): UseSnapshotFreshnessReturn {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [digest, setDigest] = useState<MemorySnapshotDigestDTO | null>(null);
  const [state, setState] = useState<SnapshotFreshnessStateDTO | null>(null);
  const [diskHint, setDiskHint] = useState<DirectDiskReadHintDTO | null>(null);
  const [deltaPatch, setDeltaPatch] = useState<DeltaPatchBlockDTO | null>(null);
  const [error, setError] = useState<string | null>(null);

  const initSnapshot = useCallback(
    async (req: InitSnapshotRequest): Promise<MemorySnapshotDigestDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const res = await initSessionSnapshot(req);
        setDigest(res);
        return res;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to init memory snapshot';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const recordWrite = useCallback(
    async (req: RecordWriteRequest): Promise<SnapshotFreshnessStateDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const updated = await recordSessionWrite(req);
        setState(updated);
        return updated;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to record memory write';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const fetchState = useCallback(
    async (sessionId: string): Promise<SnapshotFreshnessStateDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const fetched = await getSnapshotFreshnessState(sessionId);
        setState(fetched);
        return fetched;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : `Failed to fetch freshness state for ${sessionId}`;
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const fetchDiskHint = useCallback(
    async (sessionId: string): Promise<DirectDiskReadHintDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const hint = await getDiskReadHint(sessionId);
        setDiskHint(hint);
        return hint;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : `Failed to fetch disk hint for ${sessionId}`;
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const fetchDeltaPatch = useCallback(
    async (sessionId: string): Promise<DeltaPatchBlockDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const patch = await getDeltaPatch(sessionId);
        setDeltaPatch(patch);
        return patch;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : `Failed to fetch delta patch for ${sessionId}`;
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const resetSession = useCallback(
    async (sessionId: string): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        await resetSessionFreshness(sessionId);
        setState(null);
        setDiskHint(null);
        setDeltaPatch(null);
        return true;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : `Failed to reset session freshness for ${sessionId}`;
        setError(message);
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const clearLocalState = useCallback(() => {
    setIsLoading(false);
    setDigest(null);
    setState(null);
    setDiskHint(null);
    setDeltaPatch(null);
    setError(null);
  }, []);

  return {
    isLoading,
    digest,
    state,
    diskHint,
    deltaPatch,
    error,
    initSnapshot,
    recordWrite,
    fetchState,
    fetchDiskHint,
    fetchDeltaPatch,
    resetSession,
    clearLocalState,
  };
}
