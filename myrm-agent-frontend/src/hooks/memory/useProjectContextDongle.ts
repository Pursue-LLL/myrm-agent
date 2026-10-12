/**
 * [INPUT]
 * @/services/memory/projectDongle::DTOs, initProjectDongle, getDongleState, getDonglePromptContext, syncDongleBlocks
 * React::useState, useCallback
 *
 * [OUTPUT]
 * useProjectContextDongle: React hook managing workspace 4-tier markdown dongle lifecycle and zero-loss relay.
 *
 * [POS]
 * Hook module for Item 152 ProjectContextUsbDongleAndCrossAgentRelaySuite.
 * Strict typing applied: 0 any types allowed.
 */

import { useCallback, useState } from 'react';
import {
  DongleBlockDTO,
  DongleInitResponseDTO,
  DongleStateDTO,
  DongleSyncResponseDTO,
  getDonglePromptContext,
  getDongleState,
  initProjectDongle,
  syncDongleBlocks,
} from '@/services/memory/projectDongle';

export interface UseProjectContextDongleState {
  isLoading: boolean;
  isSyncing: boolean;
  dongleState: DongleStateDTO | null;
  promptContext: string | null;
  lastSyncResult: DongleSyncResponseDTO | null;
  error: string | null;
}

export interface UseProjectContextDongleReturn extends UseProjectContextDongleState {
  loadState: (workspaceDir: string) => Promise<DongleStateDTO | null>;
  initWorkspace: (workspaceDir: string) => Promise<DongleInitResponseDTO | null>;
  loadPromptContext: (workspaceDir: string) => Promise<string | null>;
  syncBlocks: (workspaceDir: string, blocks: DongleBlockDTO[]) => Promise<DongleSyncResponseDTO | null>;
  reset: () => void;
}

export function useProjectContextDongle(): UseProjectContextDongleReturn {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [dongleState, setDongleState] = useState<DongleStateDTO | null>(null);
  const [promptContext, setPromptContext] = useState<string | null>(null);
  const [lastSyncResult, setLastSyncResult] = useState<DongleSyncResponseDTO | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadState = useCallback(async (workspaceDir: string): Promise<DongleStateDTO | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const state = await getDongleState(workspaceDir);
      setDongleState(state);
      return state;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load project dongle state';
      setError(msg);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const initWorkspace = useCallback(async (workspaceDir: string): Promise<DongleInitResponseDTO | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await initProjectDongle({ workspace_dir: workspaceDir });
      // Reload state after initializing
      const refreshedState = await getDongleState(workspaceDir);
      setDongleState(refreshedState);
      return resp;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to initialize project dongle';
      setError(msg);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadPromptContext = useCallback(async (workspaceDir: string): Promise<string | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await getDonglePromptContext(workspaceDir);
      setPromptContext(resp.prompt_context);
      return resp.prompt_context;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to render prompt context';
      setError(msg);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const syncBlocks = useCallback(
    async (workspaceDir: string, blocks: DongleBlockDTO[]): Promise<DongleSyncResponseDTO | null> => {
      setIsSyncing(true);
      setError(null);
      try {
        const resp = await syncDongleBlocks({ workspace_dir: workspaceDir, blocks });
        setLastSyncResult(resp);
        // Refresh state
        const refreshedState = await getDongleState(workspaceDir);
        setDongleState(refreshedState);
        return resp;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to sync dongle blocks';
        setError(msg);
        return null;
      } finally {
        setIsSyncing(false);
      }
    },
    [],
  );

  const reset = useCallback((): void => {
    setIsLoading(false);
    setIsSyncing(false);
    setDongleState(null);
    setPromptContext(null);
    setLastSyncResult(null);
    setError(null);
  }, []);

  return {
    isLoading,
    isSyncing,
    dongleState,
    promptContext,
    lastSyncResult,
    error,
    loadState,
    initWorkspace,
    loadPromptContext,
    syncBlocks,
    reset,
  };
}
