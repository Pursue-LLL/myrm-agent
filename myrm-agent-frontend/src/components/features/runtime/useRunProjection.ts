'use client';

/**
 * Pure Functional React Hook: UI = Project(RunState, Events).
 * Manages monotonic run projection state across multi-surface views.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  RunStateSnapshot,
  SurfaceViewType,
} from './runtimeProjectionTypes';
import { runtimeProjectionService } from './runtimeProjectionService';

export interface UseRunProjectionReturn {
  snapshot: RunStateSnapshot | null;
  activeSurface: SurfaceViewType;
  setSurface: (surface: SurfaceViewType) => Promise<void>;
  refresh: () => Promise<void>;
  isLoading: boolean;
  error: string | null;
}

export function useRunProjection(
  runId: string,
  initialSurface: SurfaceViewType = 'runtime_console',
  enabled: boolean = true
): UseRunProjectionReturn {
  const [snapshot, setSnapshot] = useState<RunStateSnapshot | null>(null);
  const [activeSurface, setActiveSurface] = useState<SurfaceViewType>(initialSurface);
  const [isLoading, setIsLoading] = useState<boolean>(enabled);
  const [error, setError] = useState<string | null>(null);

  const loadSnapshot = useCallback(async () => {
    if (!runId || !enabled) {
      return;
    }
    try {
      setIsLoading(true);
      setError(null);
      const data = await runtimeProjectionService.getRunProjection(runId);
      setSnapshot(data);
      if (data.active_surface) {
        setActiveSurface(data.active_surface);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to project run state';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [runId, enabled]);

  useEffect(() => {
    if (enabled) {
      loadSnapshot();
    }
  }, [enabled, loadSnapshot]);

  const setSurface = useCallback(
    async (surface: SurfaceViewType) => {
      setActiveSurface(surface);
      if (snapshot) {
        setSnapshot((prev) => (prev ? { ...prev, active_surface: surface } : null));
      }
      try {
        await runtimeProjectionService.switchSurface(runId, surface);
      } catch {
        // Optimistic update retained
      }
    },
    [runId, snapshot]
  );

  return {
    snapshot,
    activeSurface,
    setSurface,
    refresh: loadSnapshot,
    isLoading,
    error,
  };
}
