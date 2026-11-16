/**
 * The setting names the conflict dialog shows: one per config key in every locale, so a key added to the sync layer
 * cannot reach the user as a raw identifier, and a key removed from it leaves no label behind.
 */
import { describe, expect, it } from 'vitest';

import { ALL_CONFIG_KEYS } from '@/services/config/types';

import en from '../../../../../locales/en.json';
import zh from '../../../../../locales/zh.json';

const locales = [
  ['en', en],
  ['zh', zh],
] as const;

describe('configConflict.keys', () => {
  it.each(locales)('%s names exactly the config keys the sync layer has', (_name, bundle) => {
    const labels: Record<string, string> = bundle.configConflict.keys;

    expect(Object.keys(labels).sort()).toEqual([...ALL_CONFIG_KEYS].sort());
    for (const [key, label] of Object.entries(labels)) {
      expect(label.trim(), key).not.toBe('');
    }
  });
});
