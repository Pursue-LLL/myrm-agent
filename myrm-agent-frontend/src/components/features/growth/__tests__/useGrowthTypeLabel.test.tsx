/** @vitest-environment jsdom */
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import en from '../../../../../locales/en.json';
import { useGrowthTypeLabel } from '../useGrowthTypeLabel';

const growthTypes: Record<string, string> = en.growthDashboard.growthTypes;

// Approval action types for drafts (skill growth queries) and EvolutionType values for evolution reviews.
const EMITTED_GROWTH_TYPES = [
  'skill_draft',
  'skill_patch',
  'semantic_memory',
  'fix',
  'derived',
  'captured',
  'slice_extraction',
  'optimize_description',
];

vi.mock('next-intl', async () => {
  const messages: Record<string, string> = (await import('../../../../../locales/en.json')).default.growthDashboard
    .growthTypes;
  const t = Object.assign((key: string) => messages[key] ?? `MISSING:${key}`, {
    has: (key: string) => key in messages,
  });
  return { useTranslations: () => t };
});

describe('useGrowthTypeLabel', () => {
  it.each(EMITTED_GROWTH_TYPES)('names the %s growth type for users', (growthType) => {
    const { result } = renderHook(() => useGrowthTypeLabel());

    expect(result.current(growthType)).toBe(growthTypes[growthType]);
    expect(result.current(growthType)).not.toBe(growthTypes.other);
  });

  it('falls back to the generic name instead of exposing an unknown identifier', () => {
    const { result } = renderHook(() => useGrowthTypeLabel());

    expect(result.current('brand_new_type')).toBe(growthTypes.other);
    expect(result.current('')).toBe(growthTypes.other);
  });
});
