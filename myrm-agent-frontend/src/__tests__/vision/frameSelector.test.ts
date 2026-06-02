import { describe, it, expect } from 'vitest';
import { selectFrames, type VisualFrame } from '@/lib/vision/frameSelector';

const makeFrame = (id: string, ts: number): VisualFrame => ({
  id,
  base64: `data:image/jpeg;base64,fake_${id}`,
  width: 320,
  height: 240,
  timestamp: ts,
});

describe('selectFrames', () => {
  it('returns empty result for empty input', () => {
    const result = selectFrames([]);
    expect(result.frames).toHaveLength(0);
    expect(result.reason).toBe('full');
  });

  it('returns single frame as-is', () => {
    const result = selectFrames([makeFrame('a', 1000)]);
    expect(result.frames).toHaveLength(1);
    expect(result.frames[0].id).toBe('a');
    expect(result.reason).toBe('full');
  });

  it('returns 2 frames when input has 2 and maxFrames >= 2', () => {
    const frames = [makeFrame('a', 1000), makeFrame('b', 2000)];
    const result = selectFrames(frames, { maxFrames: 3, preserveFirstLast: true });
    expect(result.frames).toHaveLength(2);
    expect(result.frames[0].id).toBe('a');
    expect(result.frames[1].id).toBe('b');
    expect(result.reason).toBe('full');
  });

  it('preserves first and last frames when sampling', () => {
    const frames = Array.from({ length: 10 }, (_, i) => makeFrame(`f${i}`, 1000 + i * 500));
    const result = selectFrames(frames, { maxFrames: 4, preserveFirstLast: true });
    expect(result.frames[0].id).toBe('f0');
    expect(result.frames[result.frames.length - 1].id).toBe('f9');
    expect(result.frames.length).toBeLessThanOrEqual(4);
    expect(result.reason).toBe('sampled');
  });

  it('respects maxFrames limit', () => {
    const frames = Array.from({ length: 20 }, (_, i) => makeFrame(`f${i}`, 1000 + i * 200));
    const result = selectFrames(frames, { maxFrames: 5 });
    expect(result.frames.length).toBeLessThanOrEqual(5);
    expect(result.reason).toBe('sampled');
  });

  it('deduplicates frames within minGapMs', () => {
    const frames = [makeFrame('a', 1000), makeFrame('b', 1050), makeFrame('c', 2000)];
    const result = selectFrames(frames, { maxFrames: 10, minGapMs: 500 });
    const ids = result.frames.map((f) => f.id);
    expect(ids).toContain('a');
    expect(ids).not.toContain('b');
    expect(ids).toContain('c');
  });

  it('works without preserveFirstLast', () => {
    const frames = Array.from({ length: 15 }, (_, i) => makeFrame(`f${i}`, 1000 + i * 1000));
    const result = selectFrames(frames, { maxFrames: 3, preserveFirstLast: false });
    expect(result.frames.length).toBeLessThanOrEqual(3);
    expect(result.reason).toBe('sampled');
  });

  it('returns all frames when under maxFrames (reason: full)', () => {
    const frames = Array.from({ length: 3 }, (_, i) => makeFrame(`f${i}`, 1000 + i * 500));
    const result = selectFrames(frames);
    expect(result.frames.length).toBeGreaterThan(0);
    expect(result.frames.length).toBeLessThanOrEqual(3);
    expect(result.reason).toBe('full');
  });

  it('applies minGap in full mode', () => {
    const frames = [makeFrame('a', 1000), makeFrame('b', 1010), makeFrame('c', 1200)];
    const result = selectFrames(frames, { minGapMs: 120 });
    expect(result.frames).toHaveLength(2);
    expect(result.frames[0].id).toBe('a');
    expect(result.frames[1].id).toBe('c');
  });

  it('handles all frames with identical timestamps', () => {
    const frames = Array.from({ length: 5 }, (_, i) => makeFrame(`f${i}`, 1000));
    const result = selectFrames(frames, { minGapMs: 100 });
    expect(result.frames.length).toBeGreaterThan(0);
  });

  it('deduplicates frames with same ID', () => {
    const frames = [makeFrame('dup', 1000), makeFrame('dup', 2000), makeFrame('other', 3000)];
    const result = selectFrames(frames, { maxFrames: 2, preserveFirstLast: true });
    const ids = result.frames.map((f) => f.id);
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(ids.length);
  });

  it('works with maxFrames=1', () => {
    const frames = Array.from({ length: 10 }, (_, i) => makeFrame(`f${i}`, 1000 + i * 500));
    const result = selectFrames(frames, { maxFrames: 1, preserveFirstLast: true });
    expect(result.frames.length).toBeLessThanOrEqual(1);
  });

  it('only keeps first and last when maxFrames=2 + preserveFirstLast', () => {
    const frames = Array.from({ length: 10 }, (_, i) => makeFrame(`f${i}`, 1000 + i * 500));
    const result = selectFrames(frames, { maxFrames: 2, preserveFirstLast: true, minGapMs: 0 });
    expect(result.frames.length).toBe(2);
    expect(result.frames[0].id).toBe('f0');
    expect(result.frames[1].id).toBe('f9');
    expect(result.reason).toBe('sampled');
  });

  it('sorts descending timestamps correctly via applyMinGap', () => {
    const frames = [makeFrame('c', 3000), makeFrame('a', 1000), makeFrame('b', 2000)];
    const result = selectFrames(frames, { maxFrames: 10, minGapMs: 500 });
    expect(result.frames[0].id).toBe('a');
    expect(result.frames[1].id).toBe('b');
    expect(result.frames[2].id).toBe('c');
  });
});
