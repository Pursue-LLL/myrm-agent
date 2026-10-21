/**
 * [INPUT]
 * React hooks (useState, useRef, useCallback, useEffect)
 *
 * [OUTPUT]
 * useDividerSelfLimiting, UseDividerSelfLimitingOptions, UseDividerSelfLimitingReturn
 *
 * [POS]
 * Resizable divider iteration-bounded negotiation hook inspired by DSH TUI Commit e992914.
 * Prevents layout feedback loops (Maximum update depth exceeded / React #185 crash)
 * in narrow viewports or non-converging nested resizable panels by bounding measurement
 * to at most 3 iterations before locking safe fallback dimensions.
 */

'use client';

import { useCallback, useRef, useState } from 'react';

export const MAX_MEASURE_ITERATIONS = 3;
export const EPSILON_CONVERGENCE_PX = 1.0;
export const SIGNIFICANT_EXPAND_THRESHOLD_PX = 16.0;

export interface UseDividerSelfLimitingOptions {
  /** Minimum permissible clamped dimension in px (default: 180). */
  minDimension?: number;
  /** Maximum permissible clamped dimension in px (default: 600). */
  maxDimension?: number;
  /** Maximum negotiation cycles allowed per render burst (default: 3). */
  maxIterations?: number;
  /** Callback fired when negotiation fails to converge and lock is engaged. */
  onLockEngaged?: (lockedDimension: number, iterations: number) => void;
}

export interface NegotiateResult {
  dimension: number;
  converged: boolean;
  iteration: number;
  locked: boolean;
}

export interface UseDividerSelfLimitingReturn {
  currentDimension: number;
  isLocked: boolean;
  iterationCount: number;
  negotiate: (candidateDimension: number, availableViewportSpace?: number) => NegotiateResult;
  resetNegotiation: (forcedDimension?: number) => void;
  notifyViewportResize: (newViewportDimension: number) => void;
}

export function useDividerSelfLimiting(
  initialDimension: number,
  options?: UseDividerSelfLimitingOptions,
): UseDividerSelfLimitingReturn {
  const minDimension = options?.minDimension ?? 180;
  const maxDimension = options?.maxDimension ?? 600;
  const maxIterations = options?.maxIterations ?? MAX_MEASURE_ITERATIONS;

  const [currentDimension, setCurrentDimension] = useState<number>(initialDimension);
  const [isLocked, setIsLocked] = useState<boolean>(false);
  const [iterationCount, setIterationCount] = useState<number>(0);

  const iterationRef = useRef<number>(0);
  const lastCandidateRef = useRef<number>(initialDimension);
  const lastViewportRef = useRef<number | null>(null);
  const lockedRef = useRef<boolean>(false);

  const resetNegotiation = useCallback(
    (forcedDimension?: number) => {
      iterationRef.current = 0;
      setIterationCount(0);
      lockedRef.current = false;
      setIsLocked(false);
      if (typeof forcedDimension === 'number') {
        const clamped = Math.max(minDimension, Math.min(maxDimension, forcedDimension));
        lastCandidateRef.current = clamped;
        setCurrentDimension(clamped);
      }
    },
    [minDimension, maxDimension],
  );

  const notifyViewportResize = useCallback(
    (newViewportDimension: number) => {
      if (lastViewportRef.current !== null) {
        // Reset bounding counter when viewport grows noticeably
        if (newViewportDimension - lastViewportRef.current > SIGNIFICANT_EXPAND_THRESHOLD_PX) {
          resetNegotiation();
        }
      }
      lastViewportRef.current = newViewportDimension;
    },
    [resetNegotiation],
  );

  const negotiate = useCallback(
    (candidateDimension: number, availableViewportSpace?: number): NegotiateResult => {
      // 1. Bound candidate within absolute boundaries
      let effectiveMax = maxDimension;
      if (typeof availableViewportSpace === 'number' && availableViewportSpace > 0) {
        effectiveMax = Math.min(maxDimension, Math.max(minDimension, availableViewportSpace));
      }
      const clamped = Math.max(minDimension, Math.min(effectiveMax, candidateDimension));

      // 2. If already locked, return safely without incrementing or oscillating
      if (lockedRef.current) {
        return {
          dimension: lastCandidateRef.current,
          converged: false,
          iteration: iterationRef.current,
          locked: true,
        };
      }

      // 3. Convergence test: if change is within sub-pixel threshold, mark converged
      const delta = Math.abs(clamped - lastCandidateRef.current);
      if (delta <= EPSILON_CONVERGENCE_PX && iterationRef.current > 0) {
        iterationRef.current = 0;
        setIterationCount(0);
        return {
          dimension: clamped,
          converged: true,
          iteration: 0,
          locked: false,
        };
      }

      // 4. Increment negotiation counter
      iterationRef.current += 1;
      setIterationCount(iterationRef.current);

      // 5. Exceeded iteration bound: lock safe dimension and break oscillation loop
      if (iterationRef.current >= maxIterations) {
        lockedRef.current = true;
        setIsLocked(true);
        console.warn(
          `[DividerSelfLimiting] Non-converging layout oscillation detected (${iterationRef.current} cycles). Locking dimension to ${clamped}px.`,
        );
        options?.onLockEngaged?.(clamped, iterationRef.current);
        setCurrentDimension(clamped);
        lastCandidateRef.current = clamped;
        return {
          dimension: clamped,
          converged: false,
          iteration: iterationRef.current,
          locked: true,
        };
      }

      // 6. Normal candidate update
      lastCandidateRef.current = clamped;
      setCurrentDimension(clamped);
      return {
        dimension: clamped,
        converged: false,
        iteration: iterationRef.current,
        locked: false,
      };
    },
    [minDimension, maxDimension, maxIterations, options],
  );

  return {
    currentDimension,
    isLocked,
    iterationCount,
    negotiate,
    resetNegotiation,
    notifyViewportResize,
  };
}
