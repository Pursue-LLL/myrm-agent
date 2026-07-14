import { describe, expect, it } from 'vitest';

function hashSeed(seed: string): number {
  let hash = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function stablePick<T>(items: T[], count: number, seed: string): T[] {
  const shuffled = [...items];
  let state = hashSeed(seed);
  for (let i = shuffled.length - 1; i > 0; i--) {
    state = (Math.imul(state, 1103515245) + 12345) >>> 0;
    const j = state % (i + 1);
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled.slice(0, count);
}

describe('SamplePrompts stablePick', () => {
  it('returns the same order for the same seed (SSR/CSR stable)', () => {
    const items = Array.from({ length: 12 }, (_, i) => `item-${i}`);
    const first = stablePick(items, 4, 'agent:default');
    const second = stablePick(items, 4, 'agent:default');
    expect(first).toEqual(second);
  });

  it('can vary order when seed changes', () => {
    const items = Array.from({ length: 12 }, (_, i) => `item-${i}`);
    const a = stablePick(items, 4, 'agent:default');
    const b = stablePick(items, 4, 'fast:default');
    expect(a).not.toEqual(b);
  });
});
