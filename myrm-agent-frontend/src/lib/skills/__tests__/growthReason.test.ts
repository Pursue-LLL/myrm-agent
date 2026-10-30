import { describe, expect, it } from 'vitest';

import { parseApplyFailure, parseHeldReason } from '@/lib/skills/growthReason';

describe('parseHeldReason', () => {
  it('reads the skills a draft was found similar to', () => {
    expect(parseHeldReason('similar:deploy-flow,release_notes')).toEqual({
      kind: 'similar',
      names: ['deploy-flow', 'release_notes'],
    });
  });

  it.each([
    ['scan_failed', { kind: 'scanFailed' }],
    ['evolution_locked', { kind: 'evolutionLocked' }],
  ])('maps %s to its kind', (code, expected) => {
    expect(parseHeldReason(code)).toEqual(expected);
  });

  it.each([
    ['empty similar list', 'similar:'],
    ['separators only', 'similar:,,'],
    ['risk signals (handled by scanRiskText)', 'risk:scan_unavailable'],
    ['apply failure (handled by applyError)', 'apply_failed'],
    ['an unknown code', 'manual_review'],
    ['an object prototype member', 'constructor'],
    ['empty', ''],
    ['null', null],
    ['undefined', undefined],
  ])('returns null for %s', (_label, code) => {
    expect(parseHeldReason(code)).toBeNull();
  });

  it.each(['stale_base', 'skill_md_unloadable'])('leaves apply failure code %s to parseApplyFailure', (code) => {
    expect(parseHeldReason(code)).toBeNull();
  });
});

describe('parseApplyFailure', () => {
  it.each([
    ['stale_base', 'staleBase'],
    ['skill_md_unloadable', 'unloadable'],
  ])('maps %s to its kind', (code, expected) => {
    expect(parseApplyFailure(code)).toBe(expected);
  });

  it.each([
    ['the generic apply failure', 'apply_failed'],
    ['an unknown code', 'something_new'],
    ['an object prototype member', 'constructor'],
    ['empty', ''],
    ['null', null],
    ['undefined', undefined],
  ])('falls back to generic for %s', (_label, code) => {
    expect(parseApplyFailure(code)).toBe('generic');
  });
});
