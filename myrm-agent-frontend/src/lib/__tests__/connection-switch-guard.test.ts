import { describe, it, expect, beforeEach } from 'vitest';
import {
  clearPendingSwitch,
  getLastGood,
  getPendingSwitch,
  setLastGood,
  setPendingSwitch,
} from '../connection-switch-guard';

describe('connection-switch-guard', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('round-trips last-good snapshots', () => {
    expect(getLastGood()).toBeNull();
    setLastGood({ enabled: true, url: 'https://pi:8080' });
    expect(getLastGood()).toEqual({ enabled: true, url: 'https://pi:8080' });
    setLastGood({ enabled: false, url: null });
    expect(getLastGood()).toEqual({ enabled: false, url: null });
  });

  it('rejects corrupt last-good payloads', () => {
    localStorage.setItem('myrm-connection-last-good', 'not-json');
    expect(getLastGood()).toBeNull();
    localStorage.setItem('myrm-connection-last-good', '{"enabled":"yes"}');
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
});
