import { describe, it, expect, beforeEach } from 'vitest';
import {
  clearDeferredVersion,
  getDeferredVersion,
  getQuietHours,
  isDeferred,
  isQuietNow,
  setDeferredVersion,
  setQuietHours,
} from '../update-prefs';

describe('update-prefs', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('tracks deferred versions', () => {
    expect(getDeferredVersion()).toBeNull();
    expect(isDeferred('v0.2.0')).toBe(false);
    setDeferredVersion('v0.2.0');
    expect(isDeferred('v0.2.0')).toBe(true);
    expect(isDeferred('v0.3.0')).toBe(false);
    clearDeferredVersion();
    expect(isDeferred('v0.2.0')).toBe(false);
  });

  it('validates quiet hours strictly', () => {
    expect(getQuietHours()).toBeNull();
    setQuietHours({ startHour: 23, endHour: 7 });
    expect(getQuietHours()).toEqual({ startHour: 23, endHour: 7 });
    setQuietHours(null);
    expect(getQuietHours()).toBeNull();
    localStorage.setItem('myrm-update-quiet-hours', 'not-json');
    expect(getQuietHours()).toBeNull();
    localStorage.setItem('myrm-update-quiet-hours', '{"startHour":9,"endHour":9}');
    expect(getQuietHours()).toBeNull();
  });

  it('detects quiet windows across midnight', () => {
    const overnight = { startHour: 23, endHour: 7 };
    const day = new Date(2026, 0, 1, 2, 0, 0);
    day.setHours(2);
    expect(isQuietNow(overnight, day)).toBe(true);
    const noon = new Date(2026, 0, 1, 12, 0, 0);
    noon.setHours(12);
    expect(isQuietNow(overnight, noon)).toBe(false);
    expect(isQuietNow(null, noon)).toBe(false);
    expect(isQuietNow({ startHour: 9, endHour: 18 }, noon)).toBe(true);
  });

});
