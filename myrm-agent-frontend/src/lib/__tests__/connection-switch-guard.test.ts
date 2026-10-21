import { describe, it, expect, beforeEach } from 'vitest';
import {
  PENDING_SWITCH_TTL_MS,
  clearPendingSwitch,
  getLastGood,
  getPendingSwitch,
  isPendingFresh,
  setLastGood,
  setPendingSwitch,
} from '../connection-switch-guard';

describe('connection-switch-guard', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('round-trips last-good snapshots', () => {
    expect(getLastGood()).toBeNull();
    setLastGood({ activeId: 'p1', url: 'https://pi:8080' });
    expect(getLastGood()).toEqual({ activeId: 'p1', url: 'https://pi:8080' });
    setLastGood({ activeId: null, url: null });
    expect(getLastGood()).toEqual({ activeId: null, url: null });
  });

  it('rejects corrupt last-good payloads', () => {
    localStorage.setItem('myrm-connection-last-good', 'not-json');
    expect(getLastGood()).toBeNull();
    localStorage.setItem('myrm-connection-last-good', '{"activeId":42}');
    expect(getLastGood()).toBeNull();
    localStorage.setItem('myrm-connection-last-good', '{"activeId":"p1","url":7}');
    expect(getLastGood()).toBeNull();
  });

  it('round-trips pending switches', () => {
    expect(getPendingSwitch()).toBeNull();
    setPendingSwitch({ url: 'https://pi:8080', at: 123 });
    expect(getPendingSwitch()).toEqual({ url: 'https://pi:8080', at: 123 });
    setPendingSwitch({ url: null, at: 456 });
    expect(getPendingSwitch()).toEqual({ url: null, at: 456 });
    clearPendingSwitch();
    expect(getPendingSwitch()).toBeNull();
  });

  it('expires stale pending switches from crashed sessions', () => {
    expect(isPendingFresh({ url: 'x', at: Date.now() })).toBe(true);
    expect(isPendingFresh({ url: 'x', at: Date.now() - PENDING_SWITCH_TTL_MS - 1 })).toBe(false);
  });
});
