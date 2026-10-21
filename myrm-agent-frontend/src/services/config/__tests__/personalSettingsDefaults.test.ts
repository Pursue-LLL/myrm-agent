import { describe, it, expect } from 'vitest';

import { DEFAULT_PERSONAL_SETTINGS } from '@/services/config/types';

describe('DEFAULT_PERSONAL_SETTINGS', () => {
  it('defaults enableMemory to true for new users', () => {
    expect(DEFAULT_PERSONAL_SETTINGS.enableMemory).toBe(true);
  });
});
