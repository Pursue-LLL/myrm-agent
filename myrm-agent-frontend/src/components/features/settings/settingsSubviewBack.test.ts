import { describe, it, expect, beforeEach } from 'vitest';
import { registerSettingsSubviewBack, trySettingsSubviewBack } from './settingsSubviewBack';

describe('settingsSubviewBack', () => {
  beforeEach(() => {
    registerSettingsSubviewBack(null);
  });

  it('returns false when no handler is registered', () => {
    expect(trySettingsSubviewBack()).toBe(false);
  });

  it('invokes registered handler and returns its result', () => {
    let called = false;
    registerSettingsSubviewBack(() => {
      called = true;
      return true;
    });
    expect(trySettingsSubviewBack()).toBe(true);
    expect(called).toBe(true);
  });

  it('clears handler when registered with null', () => {
    registerSettingsSubviewBack(() => true);
    registerSettingsSubviewBack(null);
    expect(trySettingsSubviewBack()).toBe(false);
  });
});
