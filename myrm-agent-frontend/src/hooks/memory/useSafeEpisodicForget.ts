/**
 * [INPUT]
 * @/services/memory/safeForget::probeMemoryParents, executeSafeForget, DTOs
 * React::useState, useCallback
 *
 * [OUTPUT]
 * useSafeEpisodicForget: State-driven React hook for parent probing and safe episodic forget execution.
 *
 * [POS]
 * Hook module for Item 149 SafeEpisodicForgetSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { useCallback, useState } from 'react';
import {
  ParentProbeResponseDTO,
  SafeForgetRequestDTO,
  SafeForgetResponseDTO,
  executeSafeForget,
  probeMemoryParents,
} from '@/services/memory/safeForget';

export interface UseSafeEpisodicForgetState {
  isProbing: boolean;
  isForgetting: boolean;
  probeResult: ParentProbeResponseDTO | null;
  lastResult: SafeForgetResponseDTO | null;
  error: string | null;
}

export interface UseSafeEpisodicForgetReturn extends UseSafeEpisodicForgetState {
  probe: (
    memoryId: string,
    callerSessionId: string,
    allowGlobal?: boolean
  ) => Promise<ParentProbeResponseDTO | null>;
  forget: (request: SafeForgetRequestDTO) => Promise<SafeForgetResponseDTO | null>;
  reset: () => void;
}

export function useSafeEpisodicForget(): UseSafeEpisodicForgetReturn {
  const [isProbing, setIsProbing] = useState<boolean>(false);
  const [isForgetting, setIsForgetting] = useState<boolean>(false);
  const [probeResult, setProbeResult] = useState<ParentProbeResponseDTO | null>(null);
  const [lastResult, setLastResult] = useState<SafeForgetResponseDTO | null>(null);
  const [error, setError] = useState<string | null>(null);

  const probe = useCallback(
    async (
      memoryId: string,
      callerSessionId: string,
      allowGlobal = true
    ): Promise<ParentProbeResponseDTO | null> => {
      setIsProbing(true);
      setError(null);
      try {
        const result = await probeMemoryParents(memoryId, callerSessionId, allowGlobal);
        setProbeResult(result);
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to probe memory parents';
        setError(message);
        return null;
      } finally {
        setIsProbing(false);
      }
    },
    []
  );

  const forget = useCallback(
    async (request: SafeForgetRequestDTO): Promise<SafeForgetResponseDTO | null> => {
      setIsForgetting(true);
      setError(null);
      try {
        const result = await executeSafeForget(request);
        setLastResult(result);
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to safely forget memory';
        setError(message);
        return null;
      } finally {
        setIsForgetting(false);
      }
    },
    []
  );

  const reset = useCallback(() => {
    setIsProbing(false);
    setIsForgetting(false);
    setProbeResult(null);
    setLastResult(null);
    setError(null);
  }, []);

  return {
    isProbing,
    isForgetting,
    probeResult,
    lastResult,
    error,
    probe,
    forget,
    reset,
  };
}
