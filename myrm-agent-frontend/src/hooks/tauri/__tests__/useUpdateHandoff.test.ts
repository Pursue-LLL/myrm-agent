/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

import {
  saveUpdateHandoff,
  readUpdateHandoff,
  clearUpdateHandoff,
  evaluateUpdateHandoff,
  useUpdateHandoff,
  UPDATE_HANDOFF_STORAGE_KEY,
  UPDATE_HANDOFF_TTL_MS,
  type UpdateHandoffRecord,
} from '../useUpdateHandoff';

// Mock deploy-mode
vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: vi.fn(() => true),
}));

// Mock @tauri-apps/api/app
const mockGetVersion = vi.fn();
vi.mock('@tauri-apps/api/app', () => ({
  getVersion: () => mockGetVersion(),
}));

describe('useUpdateHandoff', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  describe('Storage Helpers', () => {
    it('saves and reads handoff record correctly', () => {
      saveUpdateHandoff('0.1.39', '0.1.40');
      const record = readUpdateHandoff();
      expect(record).not.toBeNull();
      expect(record?.fromVersion).toBe('0.1.39');
      expect(record?.targetVersion).toBe('0.1.40');
      expect(typeof record?.timestamp).toBe('number');
    });

    it('returns null when storage is empty or invalid JSON', () => {
      expect(readUpdateHandoff()).toBeNull();

      window.localStorage.setItem(UPDATE_HANDOFF_STORAGE_KEY, '{invalid json');
      expect(readUpdateHandoff()).toBeNull();

      window.localStorage.setItem(UPDATE_HANDOFF_STORAGE_KEY, JSON.stringify({ fromVersion: 123 }));
      expect(readUpdateHandoff()).toBeNull();
    });

    it('clears handoff record from storage', () => {
      saveUpdateHandoff('0.1.39', '0.1.40');
      expect(readUpdateHandoff()).not.toBeNull();

      clearUpdateHandoff();
      expect(readUpdateHandoff()).toBeNull();
    });
  });

  describe('evaluateUpdateHandoff', () => {
    it('evaluates as success when currentVersion matches targetVersion', () => {
      const record: UpdateHandoffRecord = {
        fromVersion: '0.1.39',
        targetVersion: '0.1.40',
        timestamp: Date.now(),
      };

      const res = evaluateUpdateHandoff(record, '0.1.40');
      expect(res).toEqual({
        type: 'success',
        fromVersion: '0.1.39',
        targetVersion: '0.1.40',
        currentVersion: '0.1.40',
      });
    });

    it('evaluates as failure when currentVersion does not match targetVersion within TTL', () => {
      const record: UpdateHandoffRecord = {
        fromVersion: '0.1.39',
        targetVersion: '0.1.40',
        timestamp: Date.now(),
      };

      const res = evaluateUpdateHandoff(record, '0.1.39');
      expect(res).toEqual({
        type: 'failure',
        fromVersion: '0.1.39',
        targetVersion: '0.1.40',
        currentVersion: '0.1.39',
      });
    });

    it('evaluates as null when record is expired (beyond TTL)', () => {
      const record: UpdateHandoffRecord = {
        fromVersion: '0.1.39',
        targetVersion: '0.1.40',
        timestamp: 1_000_000, // old timestamp
      };

      const now = 1_000_000 + UPDATE_HANDOFF_TTL_MS + 1000;
      const res = evaluateUpdateHandoff(record, '0.1.40', now);
      expect(res).toBeNull();
    });

    it('evaluates as null when record is null', () => {
      expect(evaluateUpdateHandoff(null, '0.1.40')).toBeNull();
    });
  });

  describe('useUpdateHandoff Hook Lifecycle', () => {
    it('triggers onSuccess and cleans up storage when cold-started with matching version', async () => {
      saveUpdateHandoff('0.1.39', '0.1.40');
      mockGetVersion.mockResolvedValue('0.1.40');

      const onSuccess = vi.fn();
      const onFailure = vi.fn();

      const { result } = renderHook(() => useUpdateHandoff({ onSuccess, onFailure }));

      await waitFor(() => {
        expect(result.current.result).not.toBeNull();
      });

      expect(result.current.result?.type).toBe('success');
      expect(result.current.result?.currentVersion).toBe('0.1.40');
      expect(onSuccess).toHaveBeenCalledTimes(1);
      expect(onFailure).not.toHaveBeenCalled();

      // Ensure storage was atomically cleared immediately
      expect(readUpdateHandoff()).toBeNull();
    });

    it('triggers onFailure when cold-started with mismatched version within TTL', async () => {
      saveUpdateHandoff('0.1.39', '0.1.40');
      mockGetVersion.mockResolvedValue('0.1.39'); // Still old version!

      const onSuccess = vi.fn();
      const onFailure = vi.fn();

      const { result } = renderHook(() => useUpdateHandoff({ onSuccess, onFailure }));

      await waitFor(() => {
        expect(result.current.result).not.toBeNull();
      });

      expect(result.current.result?.type).toBe('failure');
      expect(result.current.result?.currentVersion).toBe('0.1.39');
      expect(result.current.result?.targetVersion).toBe('0.1.40');
      expect(onFailure).toHaveBeenCalledTimes(1);
      expect(onSuccess).not.toHaveBeenCalled();
    });

    it('dismisses result when dismiss is called', async () => {
      saveUpdateHandoff('0.1.39', '0.1.40');
      mockGetVersion.mockResolvedValue('0.1.40');

      const { result } = renderHook(() => useUpdateHandoff());

      await waitFor(() => {
        expect(result.current.result).not.toBeNull();
      });

      act(() => {
        result.current.dismiss();
      });

      expect(result.current.result).toBeNull();
    });
  });
});
