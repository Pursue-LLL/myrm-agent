import { describe, expect, it } from 'vitest';

import { getSpeciesAsset } from '../companionAssets';
import { SPECIES } from '../companionGenerator';

describe('companionAssets', () => {
  describe('getSpeciesAsset', () => {
    it('returns correct label for every known species', () => {
      for (const species of SPECIES) {
        const asset = getSpeciesAsset(species);
        expect(asset.emoji).toBe(species);
        expect(asset.label).not.toBe('Custom');
        expect(asset.label.length).toBeGreaterThan(0);
      }
    });

    it('returns Custom label for unknown species', () => {
      const asset = getSpeciesAsset('🦄');
      expect(asset.emoji).toBe('🦄');
      expect(asset.label).toBe('Custom');
    });

    it('returns Custom label for empty string', () => {
      const asset = getSpeciesAsset('');
      expect(asset.label).toBe('Custom');
    });
  });
});
