import { describe, it, expect } from 'vitest';

import { parsePetSlashArgs } from '@/services/companion/petSlashCommand';

describe('parsePetSlashArgs', () => {
  it('opens palette for bare /pet', () => {
    expect(parsePetSlashArgs('/pet')).toEqual({ mode: 'palette' });
  });

  it('opens palette for /pet list', () => {
    expect(parsePetSlashArgs('/pet list')).toEqual({ mode: 'palette' });
  });

  it('parses toggle', () => {
    expect(parsePetSlashArgs('/pet toggle')).toEqual({ mode: 'toggle' });
  });

  it('parses slug install', () => {
    expect(parsePetSlashArgs('/pet nous-girl')).toEqual({ mode: 'install', slug: 'nous-girl' });
  });

  it('uses first token when extra args present', () => {
    expect(parsePetSlashArgs('/pet nous-girl extra')).toEqual({ mode: 'install', slug: 'nous-girl' });
  });
});
