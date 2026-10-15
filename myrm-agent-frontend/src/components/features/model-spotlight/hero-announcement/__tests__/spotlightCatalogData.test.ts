import { describe, it, expect } from 'vitest';
import {
  computeMountComparison,
  filterAvailableSpotlights,
  formatTokenCount,
  isSpotlightDismissed,
  SPOTLIGHT_CATALOG,
} from '../spotlightCatalogData';
import { DismissRecord } from '../modelSpotlightTypes';

describe('spotlightCatalogData pure functions', () => {
  it('formats token count correctly for various magnitudes', () => {
    expect(formatTokenCount(1_000_000)).toBe('1M');
    expect(formatTokenCount(2_500_000)).toBe('2.5M');
    expect(formatTokenCount(500_000)).toBe('500K');
    expect(formatTokenCount(128_000)).toBe('128K');
    expect(formatTokenCount(500)).toBe('500');
  });

  it('computes mount comparison between current model and target spotlight model', () => {
    const astraSpotlight = SPOTLIGHT_CATALOG.find(
      (m) => m.id === 'spotlight-gpt-6-astra'
    );
    expect(astraSpotlight).toBeDefined();
    if (!astraSpotlight) {
      throw new Error('astraSpotlight not found');
    }

    const comparison = computeMountComparison('openai/gpt-4o', astraSpotlight);

    expect(comparison.currentModelId).toBe('openai/gpt-4o');
    expect(comparison.targetModelId).toBe('openai/gpt-6-astra');
    expect(comparison.currentContextWindow).toBe(128_000);
    expect(comparison.targetContextWindow).toBe(1_000_000);
    expect(comparison.contextDeltaTokens).toBe(872_000);
    expect(comparison.supportsVision).toBe(true);
    expect(comparison.supportsReasoning).toBe(true);
  });

  it('handles fallback model specifications when computing comparison', () => {
    const deepseekSpotlight = SPOTLIGHT_CATALOG.find(
      (m) => m.id === 'spotlight-deepseek-v3'
    );
    expect(deepseekSpotlight).toBeDefined();
    if (!deepseekSpotlight) {
      throw new Error('deepseekSpotlight not found');
    }

    const comparison = computeMountComparison('unknown/custom-model', deepseekSpotlight);

    expect(comparison.currentContextWindow).toBe(128_000);
    expect(comparison.targetContextWindow).toBe(128_000);
    expect(comparison.contextDeltaTokens).toBe(0);
  });

  it('identifies dismissed spotlights correctly based on TTL and permanence', () => {
    expect(isSpotlightDismissed(undefined)).toBe(false);

    const permanentRecord: DismissRecord = {
      spotlightId: 'spot-1',
      dismissedAt: 1000,
      permanent: true,
    };
    expect(isSpotlightDismissed(permanentRecord, 1_000_000)).toBe(true);

    const recentRecord: DismissRecord = {
      spotlightId: 'spot-2',
      dismissedAt: 1000,
      permanent: false,
    };
    // Within 24 hours (86_400_000 ms)
    expect(isSpotlightDismissed(recentRecord, 1000 + 3600_000)).toBe(true);
    // After 24 hours
    expect(isSpotlightDismissed(recentRecord, 1000 + 86_400_000 + 10)).toBe(false);
  });

  it('filters available spotlights eliminating dismissed items', () => {
    const record: DismissRecord = {
      spotlightId: SPOTLIGHT_CATALOG[0].id,
      dismissedAt: 1000,
      permanent: true,
    };

    const dismissedMap = { [record.spotlightId]: record };
    const available = filterAvailableSpotlights(SPOTLIGHT_CATALOG, dismissedMap, 2000);

    expect(available.length).toBe(SPOTLIGHT_CATALOG.length - 1);
    expect(available.some((m) => m.id === record.spotlightId)).toBe(false);
  });
});
