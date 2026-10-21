/** @vitest-environment jsdom */
import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  computeStaircaseGeometry,
  useOutlineGeometry,
} from '../useOutlineGeometry';
import type { OutlineTurnItem } from '../outlineTypes';

describe('useOutlineGeometry & computeStaircaseGeometry', () => {
  const mockItems: OutlineTurnItem[] = [
    {
      turnIndex: 1,
      userMessageId: 'msg-1',
      assistantMessageId: 'asst-1',
      promptPreview: 'Initialize project structure',
      replyPreview: 'Created files and directories',
      isLoaded: true,
      messageIndex: 0,
    },
    {
      turnIndex: 2,
      userMessageId: 'msg-2',
      assistantMessageId: 'asst-2',
      promptPreview: 'Add authentication routes',
      replyPreview: 'Configured JWT auth middleware',
      isLoaded: true,
      messageIndex: 1,
    },
    {
      turnIndex: 3,
      userMessageId: 'msg-3',
      assistantMessageId: 'asst-3',
      promptPreview: 'Optimize database queries',
      replyPreview: 'Added indexed lookup',
      isLoaded: true,
      messageIndex: 2,
    },
    {
      turnIndex: 4,
      userMessageId: 'msg-4',
      assistantMessageId: 'asst-4',
      promptPreview: 'Deploy to sandbox instance',
      replyPreview: 'Deployed and running healthy',
      isLoaded: true,
      messageIndex: 3,
    },
    {
      turnIndex: 5,
      userMessageId: 'msg-5',
      assistantMessageId: 'asst-5',
      promptPreview: 'Run e2e regression tests',
      replyPreview: 'All tests green',
      isLoaded: true,
      messageIndex: 4,
    },
  ];

  it('correctly calculates staircase geometry parameters for different distances', () => {
    // Focus turn = 3
    const center = computeStaircaseGeometry(3, 3);
    expect(center.isCenter).toBe(true);
    expect(center.scale).toBe(1.0);
    expect(center.width).toBe(24);
    expect(center.height).toBe(4);
    expect(center.opacity).toBe(1.0);

    const dist1 = computeStaircaseGeometry(2, 3);
    expect(dist1.isCenter).toBe(false);
    expect(dist1.scale).toBe(0.82);
    expect(dist1.width).toBe(18);
    expect(dist1.height).toBe(3);
    expect(dist1.opacity).toBe(0.85);

    const dist2 = computeStaircaseGeometry(1, 3);
    expect(dist2.isCenter).toBe(false);
    expect(dist2.scale).toBe(0.68);
    expect(dist2.width).toBe(13);
    expect(dist2.height).toBe(2.5);
    expect(dist2.opacity).toBe(0.65);

    const dist3 = computeStaircaseGeometry(6, 3);
    expect(dist3.isCenter).toBe(false);
    expect(dist3.scale).toBeLessThan(0.68);
    expect(dist3.width).toBeLessThanOrEqual(10);
  });

  it('handles empty items array gracefully in useOutlineGeometry hook', () => {
    const { result } = renderHook(() =>
      useOutlineGeometry({
        items: [],
        activeViewportTurn: null,
      }),
    );
    expect(result.current).toEqual([]);
  });

  it('uses activeViewportTurn as focus when hoveredTurnIndex is absent', () => {
    const { result } = renderHook(() =>
      useOutlineGeometry({
        items: mockItems,
        activeViewportTurn: 2,
        hoveredTurnIndex: null,
      }),
    );

    expect(result.current).toHaveLength(5);
    // Turn 2 is center
    expect(result.current[1].isCenter).toBe(true);
    expect(result.current[1].scale).toBe(1.0);
    // Turn 1 and Turn 3 are dist 1
    expect(result.current[0].scale).toBe(0.82);
    expect(result.current[2].scale).toBe(0.82);
  });

  it('prioritizes hoveredTurnIndex over activeViewportTurn for hover fisheye effect', () => {
    const { result } = renderHook(() =>
      useOutlineGeometry({
        items: mockItems,
        activeViewportTurn: 2,
        hoveredTurnIndex: 4,
      }),
    );

    expect(result.current).toHaveLength(5);
    // Turn 4 should be center due to hover
    expect(result.current[3].isCenter).toBe(true);
    expect(result.current[3].scale).toBe(1.0);
    // Turn 2 should no longer be center
    expect(result.current[1].isCenter).toBe(false);
    expect(result.current[1].scale).toBe(0.68);
  });
});
