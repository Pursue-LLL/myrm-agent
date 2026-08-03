import { describe, expect, it } from 'vitest';
import { recommendLayoutFromAspect } from '../recommend-layout-from-aspect';

describe('recommendLayoutFromAspect', () => {
  it('recommends full-bleed for wide landscapes', () => {
    expect(recommendLayoutFromAspect(1.6)).toBe('full-bleed');
  });

  it('recommends nav-rail-focus for tall portraits', () => {
    expect(recommendLayoutFromAspect(0.7)).toBe('nav-rail-focus');
  });

  it('recommends chat-hero for near-square media', () => {
    expect(recommendLayoutFromAspect(1.1)).toBe('chat-hero');
  });

  it('falls back for invalid aspect ratio', () => {
    expect(recommendLayoutFromAspect(Number.NaN)).toBe('full-bleed');
  });
});
