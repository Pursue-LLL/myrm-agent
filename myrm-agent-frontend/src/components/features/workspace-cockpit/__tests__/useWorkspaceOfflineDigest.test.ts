import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  useWorkspaceOfflineDigest,
  formatTimeDuration,
  readLastActiveTimestamp,
  writeLastActiveTimestamp,
} from '../useWorkspaceOfflineDigest';
import type { WorkspaceTaskItem } from '../workspaceCockpitTypes';

describe('useWorkspaceOfflineDigest', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  describe('formatTimeDuration', () => {
    it('formats seconds, minutes, hours, and days correctly', () => {
      expect(formatTimeDuration(5000)).toBe('5s');
      expect(formatTimeDuration(120 * 1000)).toBe('2m');
      expect(formatTimeDuration(3600 * 1000 * 2 + 1800 * 1000)).toBe('2h 30m');
      expect(formatTimeDuration(86400 * 1000 * 3 + 3600 * 1000 * 4)).toBe('3d 4h');
    });
  });

  describe('localStorage persistence', () => {
    it('reads and writes last active timestamp correctly', () => {
      const ts = 1700000000000;
      writeLastActiveTimestamp(ts);
      expect(readLastActiveTimestamp()).toBe(ts);
    });
  });

  describe('summary calculation and highlights', () => {
    const baseTime = 1000000;
    const mockTasks: WorkspaceTaskItem[] = [
      {
        id: 't-1',
        title: 'Gate approval for production deployment',
        swimlane: 'needs-you',
        status: 'waiting_approval',
        chatId: 'chat-1',
        updatedAt: baseTime + 5000,
        waitingDurationMs: 60000,
      },
      {
        id: 't-2',
        title: 'Background test runner failed on step 3',
        swimlane: 'in-progress',
        status: 'failed',
        chatId: 'chat-2',
        updatedAt: baseTime + 8000,
        errorReason: 'OOM killed',
      },
      {
        id: 't-3',
        title: 'Full refactoring of navigation bar',
        swimlane: 'in-progress',
        status: 'success',
        chatId: 'chat-3',
        updatedAt: baseTime + 12000,
      },
      {
        id: 't-4',
        title: 'API endpoint health watchdog probe',
        swimlane: 'observing',
        status: 'running',
        chatId: 'chat-4',
        updatedAt: baseTime + 1000,
      },
      {
        id: 't-5',
        title: 'Nightly backup snapshot',
        swimlane: 'scheduled',
        status: 'pending',
        chatId: 'chat-5',
        scheduleCron: '0 2 * * *',
        updatedAt: baseTime,
      },
      {
        id: 't-6',
        title: 'Ongoing code generation workflow',
        swimlane: 'in-progress',
        status: 'running',
        chatId: 'chat-6',
        updatedAt: baseTime + 2000,
      },
    ];

    it('aggregates offline digest metrics correctly', () => {
      const { result } = renderHook(() =>
        useWorkspaceOfflineDigest(mockTasks, baseTime),
      );

      const summary = result.current.summary;
      expect(summary.pendingDecisionsCount).toBe(1);
      expect(summary.failedTasksCount).toBe(1);
      expect(summary.completedGoalsCount).toBe(1);
      expect(summary.inProgressCount).toBe(2);
      expect(summary.highlights.length).toBeGreaterThan(0);
    });

    it('dismisses digest and updates lastActive timestamp', () => {
      const { result } = renderHook(() =>
        useWorkspaceOfflineDigest(mockTasks, baseTime),
      );

      expect(result.current.shouldShowDigest).toBe(true);

      act(() => {
        result.current.dismissDigest();
      });

      expect(result.current.shouldShowDigest).toBe(false);
    });
  });
});
