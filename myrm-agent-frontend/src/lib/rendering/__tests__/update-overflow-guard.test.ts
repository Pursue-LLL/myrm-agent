import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  isNestedUpdateOverflow,
  registerOverflowQuench,
  resetUpdateOverflowGuardForTest,
  swallowNestedUpdateOverflow,
  unregisterOverflowQuench,
} from '../update-overflow-guard';

const overflowError = (marker: 'minified' | 'message' = 'minified') =>
  marker === 'minified' ? new Error('Minified React error #185; visit ...') : new Error('Maximum update depth exceeded');

describe('update-overflow-guard', () => {
  beforeEach(() => {
    resetUpdateOverflowGuardForTest();
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    resetUpdateOverflowGuardForTest();
  });

  describe('isNestedUpdateOverflow', () => {
    it('matches both #185 markers', () => {
      expect(isNestedUpdateOverflow(overflowError('minified'))).toBe(true);
      expect(isNestedUpdateOverflow(overflowError('message'))).toBe(true);
    });

    it('rejects non-Error values and unrelated errors', () => {
      expect(isNestedUpdateOverflow('Maximum update depth exceeded')).toBe(false);
      expect(isNestedUpdateOverflow(null)).toBe(false);
      expect(isNestedUpdateOverflow(new Error('Some other crash'))).toBe(false);
    });
  });

  describe('swallowNestedUpdateOverflow', () => {
    it('absorbs the overflow and returns true', () => {
      expect(swallowNestedUpdateOverflow(overflowError(), 'src-a')).toBe(true);
    });

    it('rate-limits: logs once per window, counts the rest', () => {
      for (let i = 0; i < 4; i += 1) {
        swallowNestedUpdateOverflow(overflowError(), 'src-rate');
      }
      expect(console.error).toHaveBeenCalledTimes(1);
    });

    it('rethrow signal for unknown errors', () => {
      expect(swallowNestedUpdateOverflow(new Error('boom'), 'src-unknown')).toBe(false);
    });

    it('trips the quench at TRIP_THRESHOLD within one window', () => {
      const quench = vi.fn();
      registerOverflowQuench('src-trip', quench);
      for (let i = 0; i < 5; i += 1) {
        swallowNestedUpdateOverflow(overflowError(), 'src-trip');
      }
      expect(quench).toHaveBeenCalledTimes(1);
      expect(quench).toHaveBeenCalledWith(5_000);
    });

    it('escalates backoff across consecutive trips (5s → 10s) after each quench window', () => {
      vi.useFakeTimers();
      try {
        const base = Date.now();
        vi.setSystemTime(base);
        const quench = vi.fn();
        registerOverflowQuench('src-escalate', quench);
        for (let i = 0; i < 5; i += 1) {
          swallowNestedUpdateOverflow(overflowError(), 'src-escalate');
        }
        expect(quench).toHaveBeenCalledTimes(1);
        expect(quench).toHaveBeenNthCalledWith(1, 5_000);
        // Inside the quench window absorptions continue but no new trip.
        for (let i = 0; i < 5; i += 1) {
          swallowNestedUpdateOverflow(overflowError(), 'src-escalate');
        }
        expect(quench).toHaveBeenCalledTimes(1);
        // After the window expires, a sustained oscillation trips again with doubled backoff.
        vi.setSystemTime(base + 5_001);
        for (let i = 0; i < 5; i += 1) {
          swallowNestedUpdateOverflow(overflowError(), 'src-escalate');
        }
        expect(quench).toHaveBeenCalledTimes(2);
        expect(quench).toHaveBeenNthCalledWith(2, 10_000);
      } finally {
        vi.useRealTimers();
      }
    });

    it('absorbs without a registered quench (escalated log only)', () => {
      for (let i = 0; i < 5; i += 1) {
        expect(swallowNestedUpdateOverflow(overflowError(), 'src-noquench')).toBe(true);
      }
      expect(console.error).toHaveBeenCalledWith(expect.stringContaining('no quench registered'));
    });

    it('keeps per-source state independent', () => {
      for (let i = 0; i < 4; i += 1) {
        swallowNestedUpdateOverflow(overflowError(), 'src-x');
      }
      const quench = vi.fn();
      registerOverflowQuench('src-y', quench);
      swallowNestedUpdateOverflow(overflowError(), 'src-y');
      expect(quench).not.toHaveBeenCalled();
    });
  });

  describe('unregisterOverflowQuench', () => {
    it('stops quenching after unregister', () => {
      const quench = vi.fn();
      registerOverflowQuench('src-unreg', quench);
      unregisterOverflowQuench('src-unreg');
      for (let i = 0; i < 5; i += 1) {
        swallowNestedUpdateOverflow(overflowError(), 'src-unreg');
      }
      expect(quench).not.toHaveBeenCalled();
    });
  });
});