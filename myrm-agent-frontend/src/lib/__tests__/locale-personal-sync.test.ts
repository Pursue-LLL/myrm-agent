import { describe, it, expect, vi, beforeEach } from 'vitest';

const updatePersonalSettings = vi.fn(async () => undefined);

let personalSettings: { locale?: string } = {};

vi.mock('@/store/useConfigStore', () => ({
  default: {
    getState: () => ({
      personalSettings,
      updatePersonalSettings,
    }),
  },
}));

import { persistLocaleToPersonalSettings } from '../locale-personal-sync';

describe('persistLocaleToPersonalSettings', () => {
  beforeEach(() => {
    updatePersonalSettings.mockClear();
    personalSettings = {};
  });

  it('writes normalized locale when personalSettings differs', async () => {
    personalSettings = { locale: 'zh-CN' };
    await persistLocaleToPersonalSettings('en');
    expect(updatePersonalSettings).toHaveBeenCalledWith({ locale: 'en' });
  });

  it('skips update when backend locale already matches', async () => {
    personalSettings = { locale: 'en' };
    await persistLocaleToPersonalSettings('en');
    expect(updatePersonalSettings).not.toHaveBeenCalled();
  });

  it('skips update for empty locale input', async () => {
    await persistLocaleToPersonalSettings(null);
    expect(updatePersonalSettings).not.toHaveBeenCalled();
  });
});
