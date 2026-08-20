import { beforeEach, describe, expect, it, vi } from 'vitest';

import { resolveVisionConfigGapActionLabel, runVisionConfigGapAction, VISION_SETTINGS_PATH } from '../visionConfigGap';

describe('visionConfigGap', () => {
  beforeEach(() => {
    document.documentElement.lang = 'en';
  });

  it('exports default vision settings path', () => {
    expect(VISION_SETTINGS_PATH).toBe('/settings/models?sub=default');
  });

  it('resolveVisionConfigGapActionLabel uses en copy by default', () => {
    expect(resolveVisionConfigGapActionLabel(false)).toBe('Go to Settings');
  });

  it('resolveVisionConfigGapActionLabel uses zh copy when requested', () => {
    expect(resolveVisionConfigGapActionLabel(true)).toBe('前往设置');
  });

  it('runVisionConfigGapAction navigates to settings', async () => {
    const assign = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { assign },
      configurable: true,
    });

    await runVisionConfigGapAction('/settings/models?sub=default');

    expect(assign).toHaveBeenCalledWith('/settings/models?sub=default');
  });
});
