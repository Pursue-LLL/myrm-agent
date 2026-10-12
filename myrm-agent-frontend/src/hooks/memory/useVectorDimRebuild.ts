/**
 * [INPUT]
 * @/services/memory/vectorDimGuard::inspectCollectionDim, startVectorRebuild, getRebuildTaskStatus, DTOs
 * React::useState, useCallback
 *
 * [OUTPUT]
 * useVectorDimRebuild: React hook managing vector dimension inspection and task-based rebuild execution.
 *
 * [POS]
 * Hook module for Item 151 VectorDimGuardAndRebuildTaskSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { useCallback, useState } from 'react';
import {
  DimGuardInspectResponseDTO,
  RebuildTaskStatusResponseDTO,
  StartRebuildRequestDTO,
  getRebuildTaskStatus,
  inspectCollectionDim,
  startVectorRebuild,
} from '@/services/memory/vectorDimGuard';

export interface UseVectorDimRebuildState {
  isInspecting: boolean;
  isRebuilding: boolean;
  inspectResult: DimGuardInspectResponseDTO | null;
  taskStatus: RebuildTaskStatusResponseDTO | null;
  error: string | null;
}

export interface UseVectorDimRebuildReturn extends UseVectorDimRebuildState {
  inspect: (collection: string, expectedDim: number) => Promise<DimGuardInspectResponseDTO | null>;
  rebuild: (request: StartRebuildRequestDTO) => Promise<RebuildTaskStatusResponseDTO | null>;
  refreshStatus: (taskId: string) => Promise<RebuildTaskStatusResponseDTO | null>;
  reset: () => void;
}

export function useVectorDimRebuild(): UseVectorDimRebuildReturn {
  const [isInspecting, setIsInspecting] = useState<boolean>(false);
  const [isRebuilding, setIsRebuilding] = useState<boolean>(false);
  const [inspectResult, setInspectResult] = useState<DimGuardInspectResponseDTO | null>(null);
  const [taskStatus, setTaskStatus] = useState<RebuildTaskStatusResponseDTO | null>(null);
  const [error, setError] = useState<string | null>(null);

  const inspect = useCallback(
    async (collection: string, expectedDim: number): Promise<DimGuardInspectResponseDTO | null> => {
      setIsInspecting(true);
      setError(null);
      try {
        const result = await inspectCollectionDim({ collection, expected_dim: expectedDim });
        setInspectResult(result);
        return result;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to inspect collection dimension';
        setError(msg);
        return null;
      } finally {
        setIsInspecting(false);
      }
    },
    []
  );

  const rebuild = useCallback(
    async (request: StartRebuildRequestDTO): Promise<RebuildTaskStatusResponseDTO | null> => {
      setIsRebuilding(true);
      setError(null);
      try {
        const status = await startVectorRebuild(request);
        setTaskStatus(status);
        return status;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to start rebuild task';
        setError(msg);
        return null;
      } finally {
        setIsRebuilding(false);
      }
    },
    []
  );

  const refreshStatus = useCallback(
    async (taskId: string): Promise<RebuildTaskStatusResponseDTO | null> => {
      try {
        const status = await getRebuildTaskStatus(taskId);
        setTaskStatus(status);
        return status;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to refresh rebuild status';
        setError(msg);
        return null;
      }
    },
    []
  );

  const reset = useCallback(() => {
    setIsInspecting(false);
    setIsRebuilding(false);
    setInspectResult(null);
    setTaskStatus(null);
    setError(null);
  }, []);

  return {
    isInspecting,
    isRebuilding,
    inspectResult,
    taskStatus,
    error,
    inspect,
    rebuild,
    refreshStatus,
    reset,
  };
}
